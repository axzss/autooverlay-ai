'use client'

import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api, type HealthResponse } from '../../../lib/api'

export default function AgentStatusCard() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setInterval>

    const load = async () => {
      try {
        const h = await api.getHealth()
        if (!cancelled) {
          setHealth(h)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Backend unreachable')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    timer = setInterval(load, 30_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const backendOk = health?.status === 'ok'
  const alpacaOk = health?.alpaca_configured === true
  const modeText = alpacaOk ? 'Paper trading live' : 'Mock mode'

  return (
    <div className="rounded border border-[#1e293b] bg-[#0f172a] p-4 space-y-2">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-[#22c55e]" />
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
                backendOk
                  ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
                  : 'border-[#ef4444]/50 bg-[#450a0a] text-[#f87171]'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  backendOk ? 'bg-[#22c55e]' : 'bg-[#ef4444]'
                }`}
              />
              {(health?.status ?? 'unknown').toUpperCase()}
            </span>
          </li>
          <li className="flex items-center justify-between">
            <span className="text-[#94a3b8]">Alpaca</span>
            <span
              className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 ${
                alpacaOk
                  ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
                  : 'border-[#f59e0b]/50 bg-[#451a03] text-[#fbbf24]'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  alpacaOk ? 'bg-[#22c55e]' : 'bg-[#f59e0b]'
                }`}
              />
              {modeText}
            </span>
          </li>
        </ul>
      )}
    </div>
  )
}
