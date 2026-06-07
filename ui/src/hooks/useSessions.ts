import { useState, useEffect, useCallback } from 'react'
import { Session } from '../types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export function useSessions(userId: string, refreshTrigger?: number) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!userId) return
    setLoading(true)
    try {
      const res = await fetch(`${API_URL}/sessions?user_id=${encodeURIComponent(userId)}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json() as Session[] | { sessions: Session[] }
      if (Array.isArray(data)) {
        setSessions(data)
      } else if (data.sessions) {
        setSessions(data.sessions)
      }
    } catch (err) {
      console.error('Failed to fetch sessions:', err)
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    void refresh()
  }, [refresh, refreshTrigger])

  return { sessions, loading, refresh }
}
