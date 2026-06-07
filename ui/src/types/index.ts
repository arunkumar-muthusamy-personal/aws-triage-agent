export interface ToolEvent {
  type: 'tool_start' | 'tool_end'
  tool: string
  input?: Record<string, unknown>
  output?: Record<string, unknown>
  duration_ms?: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'error'
  content: string
  toolEvents: ToolEvent[]
  isStreaming: boolean
  createdAt: Date
}

export interface Session {
  session_id: string
  title: string
  created_at: string
  updated_at: string
  status: string
}
