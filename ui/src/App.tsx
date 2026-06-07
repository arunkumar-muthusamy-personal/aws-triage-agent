import { useRef, useEffect, useState, KeyboardEvent } from 'react'
import { useUserId } from './hooks/useUserId'
import { useSSEChat } from './hooks/useSSEChat'
import { useSessions } from './hooks/useSessions'
import { ChatMessage } from './components/ChatMessage'
import { SessionSidebar } from './components/SessionSidebar'

export default function App() {
  const userId = useUserId()
  const { messages, currentSessionId, isStreaming, sendMessage, clearMessages, loadSession } =
    useSSEChat(userId)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const { sessions, refresh: refreshSessions } = useSessions(userId, refreshTrigger)
  const [input, setInput] = useState('')
  const [showSidebar, setShowSidebar] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Refresh sessions when a new session is created
  useEffect(() => {
    if (currentSessionId) {
      void refreshSessions()
    }
  }, [currentSessionId, refreshSessions])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || isStreaming) return
    setInput('')
    await sendMessage(text)
    setRefreshTrigger((t) => t + 1)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const handleSelectSession = async (sessionId: string) => {
    await loadSession(sessionId)
  }

  const handleNewSession = () => {
    clearMessages()
    setInput('')
  }

  const currentSession = sessions.find((s) => s.session_id === currentSessionId)
  const sessionTitle = currentSession?.title || (messages.length > 0 ? 'Triage Session' : 'New Triage Session')

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 overflow-hidden">
      {/* Mobile hamburger */}
      <button
        className="md:hidden fixed top-3 left-3 z-20 p-2 bg-gray-800 rounded text-gray-300 hover:text-white"
        onClick={() => setShowSidebar((v) => !v)}
        aria-label="Toggle sidebar"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Sidebar */}
      <div
        className={`
          fixed md:relative z-10 h-full transition-transform duration-200
          ${showSidebar ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
          w-[250px] shrink-0
        `}
      >
        <SessionSidebar
          sessions={sessions}
          currentSessionId={currentSessionId}
          onSelect={(id) => {
            void handleSelectSession(id)
            // On mobile, close sidebar after selecting
            if (window.innerWidth < 768) setShowSidebar(false)
          }}
          onNew={() => {
            handleNewSession()
            if (window.innerWidth < 768) setShowSidebar(false)
          }}
          userId={userId}
        />
      </div>

      {/* Mobile overlay */}
      {showSidebar && (
        <div
          className="md:hidden fixed inset-0 z-0 bg-black/50"
          onClick={() => setShowSidebar(false)}
        />
      )}

      {/* Main chat area */}
      <div className="flex flex-col flex-1 min-w-0 md:ml-0">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800 bg-gray-900 shrink-0">
          <div className="md:hidden w-8" /> {/* spacer for hamburger button */}
          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold text-gray-100 truncate">{sessionTitle}</h1>
            {currentSessionId && (
              <p className="text-xs text-gray-500 truncate">
                Session: {currentSessionId.slice(0, 8)}...
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {isStreaming && (
              <span className="flex items-center gap-1 text-xs text-blue-400">
                <span className="inline-block w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
                Thinking...
              </span>
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="text-4xl mb-4">🔍</div>
              <h2 className="text-lg font-semibold text-gray-300 mb-2">AWS Triage Agent</h2>
              <p className="text-sm text-gray-500 max-w-md">
                Describe an AWS issue and I'll help diagnose it using CloudWatch, X-Ray, and other
                AWS tools.
              </p>
            </div>
          ) : (
            messages.map((msg) => <ChatMessage key={msg.id} message={msg} />)
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="shrink-0 border-t border-gray-800 bg-gray-900 px-4 py-3">
          <div className="flex gap-3 items-end max-w-4xl mx-auto">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe an AWS issue to triage... (Enter to send, Shift+Enter for newline)"
              rows={1}
              disabled={isStreaming}
              className="flex-1 bg-gray-800 text-gray-100 placeholder-gray-500 rounded-lg px-4 py-3 text-sm resize-none outline-none border border-gray-700 focus:border-blue-500 transition-colors disabled:opacity-50 scrollbar-thin"
              style={{
                minHeight: '48px',
                maxHeight: '160px',
                overflowY: input.split('\n').length > 4 ? 'auto' : 'hidden',
              }}
              onInput={(e) => {
                const el = e.currentTarget
                el.style.height = 'auto'
                el.style.height = Math.min(el.scrollHeight, 160) + 'px'
              }}
            />
            <button
              onClick={() => void handleSend()}
              disabled={isStreaming || !input.trim()}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white font-medium px-4 py-3 rounded-lg text-sm transition-colors shrink-0"
            >
              {isStreaming ? (
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              )}
            </button>
          </div>
          <p className="text-xs text-gray-600 text-center mt-2">
            Enter to send · Shift+Enter for newline
          </p>
        </div>
      </div>
    </div>
  )
}
