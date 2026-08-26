'use client'

import { useCallback, useEffect, useState } from 'react'
import { Loader2, RefreshCw, Zap, AlertTriangle } from 'lucide-react'
import {
  api,
  normalizeScreenings,
  toFeedEntry,
  type AgentRecommendation,
  type FeedEntry,
  type PortfolioContext,
} from '../../../lib/api'
import AgentFeedCard from './AgentFeedCard'

function Skeleton() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="animate-pulse rounded border border-[#1e293b] bg-[#0f172a] p-4 space-y-2">
          <div className="h-4 w-40 rounded bg-[#1e293b]" />
          <div className="h-3 w-64 rounded bg-[#1e293b]" />
        </div>
      ))}
    </div>
  )
}

export default function TerminalClient() {
  const [entries, setEntries] = useState<FeedEntry[]>([])
  const [portfolioContext, setPortfolioContext] = useState<PortfolioContext | null>(null)
  const [mode, setMode] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastRun, setLastRun] = useState<string | null>(null)

  const runCycle = useCallback(async (isInitial: boolean) => {
    if (isInitial) setLoading(true)
    else setRunning(true)
    setError(null)
    try {
      const res = await api.screenStrategies()
      const norm = normalizeScreenings(res)
      setEntries(norm.entries.map(toFeedEntry))
      if (norm.portfolioContext) setPortfolioContext(norm.portfolioContext)
      setMode(norm.mode)
      setLastRun(new Date().toLocaleTimeString())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent cycle failed')
      setEntries([])
    } finally {
      setLoading(false)
      setRunning(false)
    }
  }, [])

  useEffect(() => {
    runCycle(true)
  }, [runCycle])

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 sm:px-6 py-4 border-b border-[#1e293b]">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-white">AI Agent Terminal</h1>
          {mode === 'mock' && (
            <span className="inline-flex items-center rounded border border-[#b45309]/40 bg-[#451a03] px-2 py-0.5 text-xs text-[#fbbf24]">
              Mock data — backend not configured
            </span>
          )}
          {lastRun && !loading && (
            <span className="text-xs text-[#64748b]">Last cycle: {lastRun}</span>
          )}
        </div>
        <button
          onClick={() => runCycle(false)}
          disabled={running || loading}
          className="inline-flex items-center gap-2 rounded border border-[#22c55e]/50 bg-[#0f172a] px-3 py-1.5 text-xs font-medium text-[#22c55e] hover:bg-[#22c55e]/10 transition-colors disabled:opacity-50"
        >
          {running ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Zap className="h-4 w-4" />
          )}
          {running ? 'Running agent cycle…' : 'Run agent cycle'}
        </button>
      </div>

      <main className="flex-1 overflow-y-auto px-4 sm:px-6 pb-6 pt-4 space-y-4">
        {error && (
          <p className="flex items-center gap-2 rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 text-sm text-[#f87171]">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error} — press “Run agent cycle” to retry.
          </p>
        )}

        {loading ? (
          <Skeleton />
        ) : entries.length === 0 && !error ? (
          <div className="rounded border border-[#1e293b] bg-[#0f172a] p-8 text-center">
            <RefreshCw className="mx-auto mb-2 h-6 w-6 text-[#334155]" />
            <p className="text-sm text-[#94a3b8]">No overlay recommendations right now.</p>
          </div>
        ) : (
          entries.map((entry) => <AgentFeedCard key={entry.key} entry={entry} />)
        )}

        {portfolioContext && (
          <div className="rounded border border-[#1e293b] bg-[#0f172a] p-4">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">
              Portfolio context
            </h2>
            <div className="flex flex-wrap gap-2 text-xs">
              {typeof portfolioContext.concentration_ok === 'boolean' && (
                <span
                  className={`rounded border px-2 py-0.5 ${
                    portfolioContext.concentration_ok
                      ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
                      : 'border-[#f59e0b]/50 bg-[#451a03] text-[#fbbf24]'
                  }`}
                >
                  Concentration {portfolioContext.concentration_ok ? 'OK' : 'ELEVATED'}
                </span>
              )}
              {typeof portfolioContext.cash_reserve_ok === 'boolean' && (
                <span
                  className={`rounded border px-2 py-0.5 ${
                    portfolioContext.cash_reserve_ok
                      ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
                      : 'border-[#f59e0b]/50 bg-[#451a03] text-[#fbbf24]'
                  }`}
                >
                  Cash reserve {portfolioContext.cash_reserve_ok ? 'OK' : 'LOW'}
                </span>
              )}
              {typeof portfolioContext.largest_position_pct === 'number' && (
                <span className="rounded border border-[#334155] bg-[#020617] px-2 py-0.5 text-[#94a3b8]">
                  Largest position {portfolioContext.largest_position_pct}
                </span>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
