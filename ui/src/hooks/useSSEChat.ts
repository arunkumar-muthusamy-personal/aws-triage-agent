import { useState, useCallback } from 'react'
import { Message, ToolEvent } from '../types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

function generateId(): string {
  return crypto.randomUUID()
}

interface MessageRecord {
  role: string
  content: string
  tool_events?: ToolEvent[]
  created_at?: string
}

function normalizeRole(role: string): Message['role'] {
  const normalized = role.toLowerCase()
  if (normalized === 'user' || normalized === 'assistant') return normalized
  return 'assistant'
}

function pairToolEvents(events: ToolEvent[] = []): ToolEvent[] {
  const paired: ToolEvent[] = []

  for (const event of events) {
    if (event.type === 'tool_start') {
      paired.push({ ...event })
      continue
    }

    const idx = [...paired]
      .reverse()
      .findIndex((e) => e.type === 'tool_start' && e.tool === event.tool && e.output === undefined)
    const realIdx = idx !== -1 ? paired.length - 1 - idx : -1

    if (realIdx !== -1) {
      paired[realIdx] = {
        ...paired[realIdx],
        output: event.output,
        duration_ms: event.duration_ms,
      }
    } else {
      paired.push({ ...event })
    }
  }

  return paired
}

export function useSSEChat(userId: string) {
  const [messages, setMessages] = useState<Message[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)

  const clearMessages = useCallback(() => {
    setMessages([])
    setCurrentSessionId(null)
  }, [])

  const loadSession = useCallback(async (sessionId: string) => {
    try {
      const res = await fetch(`${API_URL}/sessions/${sessionId}`)
      if (!res.ok) return
      const data = await res.json()
      setCurrentSessionId(sessionId)
      // API returns a flat array of MessageRecord objects
      if (Array.isArray(data)) {
        const loaded: Message[] = (data as MessageRecord[]).map((m) => ({
          id: generateId(),
          role: normalizeRole(m.role),
          content: m.content,
          toolEvents: pairToolEvents(m.tool_events),
          isStreaming: false,
          createdAt: m.created_at ? new Date(m.created_at) : new Date(),
        }))
        setMessages(loaded)
      }
    } catch (err) {  // eslint-disable-line @typescript-eslint/no-unused-vars
      console.error('Failed to load session:', err)
    }
  }, [])

  const sendMessage = useCallback(
    async (text: string) => {
      if (isStreaming || !text.trim()) return

      const userMsg: Message = {
        id: generateId(),
        role: 'user',
        content: text.trim(),
        toolEvents: [],
        isStreaming: false,
        createdAt: new Date(),
      }

      const assistantMsgId = generateId()
      const assistantMsg: Message = {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        toolEvents: [],
        isStreaming: true,
        createdAt: new Date(),
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)

      try {
        const res = await fetch(`${API_URL}/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: currentSessionId,
            user_id: userId,
            message: text.trim(),
          }),
        })

        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let currentEvent = 'message'

        const updateLastAssistant = (updater: (msg: Message) => Message) => {
          setMessages((prev) => {
            const idx = prev.findIndex((m) => m.id === assistantMsgId)
            if (idx === -1) return prev
            const next = [...prev]
            next[idx] = updater(next[idx])
            return next
          })
        }

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              const rawData = line.slice(6).trim()
              if (!rawData) continue

              let parsed: Record<string, unknown>
              try {
                parsed = JSON.parse(rawData) as Record<string, unknown>
              } catch {
                continue
              }

              if (currentEvent === 'token') {
                const token = (parsed.text ?? parsed.token ?? parsed.content ?? '') as string
                updateLastAssistant((msg) => ({
                  ...msg,
                  content: msg.content + token,
                }))
              } else if (currentEvent === 'tool_start') {
                const event: ToolEvent = {
                  type: 'tool_start',
                  tool: (parsed.tool ?? parsed.name ?? '') as string,
                  input: parsed.input as Record<string, unknown> | undefined,
                }
                updateLastAssistant((msg) => ({
                  ...msg,
                  toolEvents: [...msg.toolEvents, event],
                }))
              } else if (currentEvent === 'tool_end') {
                const toolName = (parsed.tool ?? parsed.name ?? '') as string
                updateLastAssistant((msg) => {
                  const toolEvents = [...msg.toolEvents]
                  // Find the last matching tool_start without a paired tool_end
                  const startIdx = [...toolEvents]
                    .reverse()
                    .findIndex((e) => e.type === 'tool_start' && e.tool === toolName)
                  const realIdx =
                    startIdx !== -1 ? toolEvents.length - 1 - startIdx : -1

                  const endEvent: ToolEvent = {
                    type: 'tool_end',
                    tool: toolName,
                    output: parsed.output as Record<string, unknown> | undefined,
                    duration_ms: parsed.duration_ms as number | undefined,
                  }

                  if (realIdx !== -1) {
                    // Annotate the start event with output info
                    toolEvents[realIdx] = {
                      ...toolEvents[realIdx],
                      output: endEvent.output,
                      duration_ms: endEvent.duration_ms,
                    }
                  } else {
                    toolEvents.push(endEvent)
                  }
                  return { ...msg, toolEvents }
                })
              } else if (currentEvent === 'done') {
                const sessionId = (parsed.session_id ?? parsed.sessionId ?? '') as string
                if (sessionId) setCurrentSessionId(sessionId)
                updateLastAssistant((msg) => ({ ...msg, isStreaming: false }))
                setIsStreaming(false)
              } else if (currentEvent === 'error') {
                updateLastAssistant((msg) => ({
                  ...msg,
                  role: 'error',
                  content: (parsed.message ?? parsed.error ?? 'An error occurred') as string,
                  isStreaming: false,
                }))
                setIsStreaming(false)
              }

              // Reset event type after data line
              currentEvent = 'message'
            }
          }
        }
      } catch (err) {
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.id === assistantMsgId)
          if (idx === -1) return prev
          const next = [...prev]
          next[idx] = {
            ...next[idx],
            role: 'error',
            content: err instanceof Error ? err.message : 'Stream error',
            isStreaming: false,
          }
          return next
        })
        setIsStreaming(false)
      }
    },
    [isStreaming, userId, currentSessionId],
  )

  return {
    messages,
    currentSessionId,
    isStreaming,
    sendMessage,
    clearMessages,
    loadSession,
  }
}
