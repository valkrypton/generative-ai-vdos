import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const DJANGO_SESSION_COOKIE = 'sessionid'
const PUBLIC_PATHS = ['/api/', '/login']

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const hasSession = request.cookies.has(DJANGO_SESSION_COOKIE)

  // Authenticated users visiting /login → send home
  if (pathname === '/login' && hasSession) {
    return NextResponse.redirect(new URL('/home', request.url))
  }

  // Public paths pass through
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next()
  }

  // No cookie → bounce to login before the server even renders
  if (!hasSession) {
    return NextResponse.redirect(new URL('/login', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
