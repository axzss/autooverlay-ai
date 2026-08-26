'use client'

import { useEffect, useState } from 'react'
import { Activity, Loader2 } from 'lucide-react'
import { api, type HealthResponse } from '../../../lib/api'

export default function AgentStatusCard() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .getHealth()
      .then((h) => {
        if (!cancelled) {
          setHealth(h)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Backend unreachable')
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="rounded border border-[#1e293b] bg-[#0f172a] p-4 space-y-2">
      <div className="flex items-center gap-2">
        <Activity className="h-4 w-4 text-[#22c55e]" />
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">Agent status</h2>
        {loading && <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin text-[#64748b]" />}
      </div>

      {error ? (
        <p className="rounded border border-[#ef4444]/40 bg-[#450a0a] px-2 py-1 text-xs text-[#f87171]">
          Backend unreachable ({error})
        </p>
      ) : loading ? (
        <div className="space-y-1.5">
          <div className="h-3 w-24 animate-pulse rounded bg-[#1e293b]" />
          <div className="h-3 w-32 animate-pulse rounded bg-[#1e293b]" />
        </div>
      ) : (
        <ul className="space-y-1.5 text-xs">
          <li className="flex items-center justify-between">
            <span className="text-[#94a3b8]">Backend</span>
            <span
              className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 ${
                health?.status === 'ok'
                  ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
                  : 'border-[#ef4444]/50 bg-[#450a0a] text-[#f87171]'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  health?.status === 'ok' ? 'bg-[#22c55e]' : 'bg-[#ef4444]'
                }`}
              />
              {(health?.status ?? 'unknown').toUpperCase()}
            </span>
          </li>
          <li className="flex items-center justify-between">
            <span className="text-[#94a3b8]">Alpaca configured</span>
            <span
              className={`rounded border px-2 py-0.5 ${
                health?.alpaca_configured
                  ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
                  : 'border-[#f59e0b]/50 bg-[#451a03] text-[#fbbf24]'
              }`}
            >
              {health?.alpaca_configured ? 'TRUE' : 'FALSE'}
            </span>
          </li>
        </ul>
      )}
    </div>
  )
}
