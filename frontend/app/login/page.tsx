'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Lock, AlertCircle, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'
import { useAuth } from '@/components/auth/AuthProvider'

export default function LoginPage() {
  const router = useRouter()
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(username, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#020617] px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="w-full max-w-md"
      >
        <div className="rounded-xl border border-[#1e293b] bg-[#0f172a] p-8 space-y-6">
          <div className="text-center">
            <h1 className="text-2xl font-semibold text-white">AutoOverlay AI</h1>
            <p className="mt-1 text-sm text-[#94a3b8]">Sign in to access the terminal</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="flex items-center gap-2 rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 text-sm text-[#f87171]"
              >
                <AlertCircle className="h-4 w-4 shrink-0" />
                {error}
              </motion.div>
            )}

            <div className="space-y-1.5">
              <label htmlFor="username" className="block text-sm text-[#94a3b8]">
                Username
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#64748b]" />
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full rounded border border-[#1e293b] bg-[#020617] pl-10 pr-4 py-2.5 text-sm text-white outline-none focus:border-[#22c55e]/50 placeholder:text-[#64748b]"
                  placeholder="Enter username"
                  required
                  autoComplete="username"
                  disabled={submitting}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="password" className="block text-sm text-[#94a3b8]">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#64748b]" />
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded border border-[#1e293b] bg-[#020617] pl-10 pr-4 py-2.5 text-sm text-white outline-none focus:border-[#22c55e]/50 placeholder:text-[#64748b]"
                  placeholder="Enter your password"
                  required
                  autoComplete="current-password"
                  disabled={submitting}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded border border-[#22c55e]/60 bg-[#052e16] px-4 py-2.5 text-sm font-semibold text-[#22c55e] hover:bg-[#0a3318] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Signing in…
                </>
              ) : (
                'Sign In'
              )}
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  )
}
