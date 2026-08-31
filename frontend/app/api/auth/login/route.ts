import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'

async function proxy(request: NextRequest, path: string, init?: RequestInit) {
  const url = `${BACKEND}/api${path}`
  const headers = new Headers(request.headers)
  // Forward cookies for session
  const cookie = request.headers.get('cookie')
  if (cookie) headers.set('cookie', cookie)
  // Forward CSRF header if present
  const csrf = request.headers.get('x-csrf-token')
  if (csrf) headers.set('x-csrf-token', csrf)

  const res = await fetch(url, {
    ...init,
    method: init?.method || request.method,
    headers,
    body: init?.body || (request.body ? await request.text() : undefined),
    credentials: 'include',
  })

  const nextRes = new NextResponse(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: res.headers,
  })

  // Forward set-cookie headers
  const setCookie = res.headers.get('set-cookie')
  if (setCookie) {
    nextRes.headers.set('set-cookie', setCookie)
  }

  return nextRes
}

export async function POST(request: NextRequest) {
  return proxy(request, '/auth/login', { method: 'POST', body: request.body })
}