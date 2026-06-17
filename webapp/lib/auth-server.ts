import { cache } from 'react'
import { cookies } from 'next/headers'

export interface UserProfile {
  id: number
  cognito_sub: string
  email: string
  name: string
  created_at: string
}

export const getUser = cache(async (): Promise<UserProfile | null> => {
  const cookieStore = await cookies()
  const session = cookieStore.get('sessionid')
  if (!session) return null

  const res = await fetch('http://localhost:8000/api/auth/me', {
    headers: { Cookie: `sessionid=${session.value}` },
    cache: 'no-store',
  })
  if (!res.ok) return null
  return res.json() as Promise<UserProfile>
})
