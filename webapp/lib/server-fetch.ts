import { cookies } from 'next/headers'

const DJANGO_ORIGIN = (process.env.DJANGO_ORIGIN ?? 'http://localhost:8000').replace(/\/$/, '')

export async function serverFetch<T>(path: string): Promise<T> {
  const cookieStore = await cookies()
  const session = cookieStore.get('sessionid')
  const res = await fetch(`${DJANGO_ORIGIN}${path}`, {
    headers: session ? { Cookie: `sessionid=${session.value}` } : {},
    cache: 'no-store',
    signal: AbortSignal.timeout(5000),
  })
  if (!res.ok) throw new Error(`${path} responded ${res.status}`)
  return res.json() as Promise<T>
}
