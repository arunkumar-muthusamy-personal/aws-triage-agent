import { Session } from '../types'

interface Props {
  sessions: Session[]
  currentSessionId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  userId: string
}

function groupSessionsByDate(sessions: Session[]): {
  today: Session[]
  yesterday: Session[]
  older: Session[]
} {
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterdayStart = new Date(todayStart)
  yesterdayStart.setDate(yesterdayStart.getDate() - 1)

  const today: Session[] = []
  const yesterday: Session[] = []
  const older: Session[] = []

  for (const session of sessions) {
    const date = new Date(session.updated_at || session.created_at)
    if (date >= todayStart) {
      today.push(session)
    } else if (date >= yesterdayStart) {
      yesterday.push(session)
    } else {
      older.push(session)
    }
  }

  return { today, yesterday, older }
}

function truncateTitle(title: string, max = 30): string {
  return title.length > max ? title.slice(0, max) + '…' : title
}

interface GroupProps {
  label: string
  sessions: Session[]
  currentSessionId: string | null
  onSelect: (id: string) => void
}

function SessionGroup({ label, sessions, currentSessionId, onSelect }: GroupProps) {
  if (sessions.length === 0) return null
  return (
    <div className="mb-4">
      <div className="text-xs text-gray-500 uppercase tracking-wider px-3 mb-1">{label}</div>
      {sessions.map((s) => (
        <button
          key={s.session_id}
          onClick={() => onSelect(s.session_id)}
          className={`w-full text-left px-3 py-2 rounded text-sm transition-colors truncate ${
            currentSessionId === s.session_id
              ? 'border-l-2 border-blue-500 bg-gray-800 text-gray-100'
              : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
          }`}
          title={s.title}
        >
          {truncateTitle(s.title || 'Untitled Session')}
        </button>
      ))}
    </div>
  )
}

export function SessionSidebar({ sessions, currentSessionId, onSelect, onNew }: Props) {
  const { today, yesterday, older } = groupSessionsByDate(sessions)

  return (
    <div className="flex flex-col h-full bg-gray-900 border-r border-gray-800">
      <div className="p-3 border-b border-gray-800">
        <button
          onClick={onNew}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 px-4 rounded transition-colors"
        >
          + New Session
        </button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-2 pt-3">
        <SessionGroup
          label="Today"
          sessions={today}
          currentSessionId={currentSessionId}
          onSelect={onSelect}
        />
        <SessionGroup
          label="Yesterday"
          sessions={yesterday}
          currentSessionId={currentSessionId}
          onSelect={onSelect}
        />
        <SessionGroup
          label="Older"
          sessions={older}
          currentSessionId={currentSessionId}
          onSelect={onSelect}
        />

        {sessions.length === 0 && (
          <div className="text-xs text-gray-600 text-center mt-8 px-4">
            No sessions yet. Start a new triage session.
          </div>
        )}
      </div>
    </div>
  )
}
