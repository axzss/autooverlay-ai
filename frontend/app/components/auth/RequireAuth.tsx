'use client'

/**
 * RequireAuth — redirect unauthenticated users to `/login`.
 *
 * Wraps protected pages/routes. While `AuthProvider` is still loading it shows
 * a minimal skeleton so the user never sees a flash of protected content.
 * After auth resolves, if `user` is null it pushes to `/login?next=<pathname>`.
 *
 * Usage in a protected page:
 *   export default function TerminalPage() {
 *     return (
 *       <RequireAuth>
 *         <TerminalClient />
 *       </RequireAuth>
 *     )
 *   }
 */
import { useRouter, usePathname } from 'next/navigation'
import { useEffect } from 'react'
import { useAuth } from '@/components/auth/AuthProvider'

const PROTECTED_PATHS = ['/terminal', '/settings', '/risk', '/blotter', '/lab']

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading, checkAuth } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (!loading && !user) {
      const next = encodeURIComponent(pathname)
      router.replace(`/login?next=${next}`)
    }
  }, [loading, user, router, pathname])

  if (loading || !user) {
    // Minimal skeleton — nothing flashes to an unauthenticated viewer.
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#020617]">
        <div className="text-[#94a3b8]">Loading…</div>
      </div>
    )
  }

  return <>{children}</>
}

/** Hook version for pages that want to render their own loading state. */
export function useRequireAuth() {
  const { user, loading, checkAuth } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (!loading && !user) {
      const next = encodeURIComponent(pathname)
      router.replace(`/login?next=${next}`)
    }
  }, [loading, user, router, pathname])

  return { user, loading, checkAuth, isProtected: PROTECTED_PATHS.some((p) => pathname?.startsWith(p)) }
}