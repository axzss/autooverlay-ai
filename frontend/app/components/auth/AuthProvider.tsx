'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useRouter, usePathname } from 'next/navigation'

interface User {
  username: string
}

interface AuthContextValue {
  user: User | null
  loading: boolean
  csrfToken: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [csrfToken, setCsrfToken] = useState<string | null>(null)
  const router = useRouter()
  const pathname = usePathname()

  const checkAuth = async () => {
    try {
      const res = await fetch('/api/auth/me', { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        setUser({ username: data.user })
        // Also fetch CSRF token
        const csrfRes = await fetch('/api/auth/csrf', { credentials: 'include' })
        if (csrfRes.ok) {
          const csrfData = await csrfRes.json()
          setCsrfToken(csrfData.csrf_token)
        }
      } else {
        setUser(null)
        setCsrfToken(null)
      }
    } catch {
      setUser(null)
      setCsrfToken(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    checkAuth()
  }, [])

  // Protect routes: redirect to login if accessing protected pages without auth
  useEffect(() => {
    if (!loading) {
      const protectedPaths = ['/terminal', '/settings', '/risk', '/blotter', '/lab']
      const isProtected = protectedPaths.some((p) => pathname.startsWith(p))
      if (isProtected && !user) {
        router.push('/login')
      }
      // If logged in and on login page, go to dashboard
      if (user && pathname === '/login') {
        router.push('/dashboard')
      }
    }
  }, [user, loading, pathname, router])

  const login = async (username: string, password: string) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(err.detail || 'Login failed')
    }
    const data = await res.json()
    setUser({ username: data.user })
    setCsrfToken(data.csrf_token)
    router.push('/dashboard')
    router.refresh()
  }

  const logout = async () => {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    })
    setUser(null)
    setCsrfToken(null)
    router.push('/login')
    router.refresh()
  }

  return (
    <AuthContext.Provider value={{ user, loading, csrfToken, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}