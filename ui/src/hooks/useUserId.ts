import { useState } from 'react'

const USER_ID_KEY = 'triage_user_id'

export function useUserId(): string {
  const [userId] = useState<string>(() => {
    const existing = localStorage.getItem(USER_ID_KEY)
    if (existing) return existing
    const newId = crypto.randomUUID()
    localStorage.setItem(USER_ID_KEY, newId)
    return newId
  })

  return userId
}
