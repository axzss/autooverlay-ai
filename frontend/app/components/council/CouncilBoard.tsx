'use client'

import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, ChevronDown, Gavel, RefreshCw, Users } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  api,
  type CouncilAssessResponse,
  type CouncilAssessment,
  type CouncilVerdict as PersonaVerdict,
} from '../../../lib/api'

type CouncilResponse = CouncilAssessResponse

const TIER_STYLES: Record<string, string> = {
  LOW: 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]',
  MID: 'border-[#f59e0b]/50 bg-[#451a03] text-[#fbbf24]',
  HIGH: 'border-[#ef4444]/50 bg-[#450a0a] text-[#f87171]',
}

function tierStyle(tier: string) {
  return TIER_STYLES[tier.toUpperCase()] ?? 'border-[#334155] bg-[#1e293b] text-[#94a3b8]'
}

function scoreColor(score: number) {
  if (score >= 60) return 'text-[#22c55e]'
  if (score >= 40) return 'text-[#fbbf24]'
  return 'text-[#f87171]'
}

function scoreRing(score: number) {
  if (score >= 60) return 'border-[#22c55e]/50'
  if (score >= 40) return 'border-[#f59e0b]/50'
  return 'border-[#ef4444]/50'
}

function stanceChip(stance: string) {
  const s = stance.toUpperCase()
  if (s === 'STRONG_BUY' || s === 'ACCUMULATE')
    return 'border-[#22c55e]/40 bg-[#052e16] text-[#22c55e]'
  if (s === 'HOLD') return 'border-[#f59e0b]/40 bg-[#451a03] text-[#fbbf24]'
  return 'border-[#ef4444]/40 bg-[#450a0a] text-[#f87171]'
}

const MOCK_SNAPSHOT: CouncilResponse = { mode: 'mock', count: 0, assessments: [] }

export default function CouncilBoard() {
  const [data, setData] = useState<CouncilResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  const runSession = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const json = await api.assessCouncil()
      setData(json)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Backend unavailable')
      setData(MOCK_SNAPSHOT)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    runSession()
  }, [runSession])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Users className="h-5 w-5 text-[#22c55e]" /> Investment Council
          </h2>
          <p className="text-xs text-[#94a3b8]">
            Six-persona weighted consensus over the overlay universe
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <span
              className={cn(
                'rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider',
                data.mode === 'live'
                  ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
                  : 'border-[#f59e0b]/50 bg-[#451a03] text-[#fbbf24]',
              )}
            >
              {data.mode === 'live' ? 'LIVE DATA' : 'MOCK DATA'}
            </span>
          )}
          <button
            onClick={runSession}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded border border-[#22c55e]/50 bg-[#052e16] px-3 py-1.5 text-sm font-medium text-[#22c55e] hover:bg-[#064e3b] disabled:opacity-50"
          >
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            Run council session
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded border border-[#f59e0b]/50 bg-[#451a03] px-3 py-2 text-sm text-[#fbbf24]">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error} — showing bundled fallback.
        </div>
      )}

      {loading && !data ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-44 animate-pulse rounded-lg border border-[#1e293b] bg-[#0f172a]"
            />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {(data?.assessments ?? []).map((a) => {
            const isOpen = expanded === a.symbol
            return (
              <div
                key={a.symbol}
                className="rounded-lg border border-[#1e293b] bg-[#0f172a] p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-base font-semibold">{a.symbol}</span>
                      <span
                        className={cn(
                          'rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider',
                          tierStyle(a.tier),
                        )}
                      >
                        {a.tier} VOL
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-[#94a3b8]">{a.tier_policy_summary}</p>
                  </div>
                  <div
                    className={cn(
                      'flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-full border-2 bg-[#020617]',
                      scoreRing(a.consensus_score),
                    )}
                  >
                    <span className={cn('text-sm font-bold', scoreColor(a.consensus_score))}>
                      {Math.round(a.consensus_score)}
                    </span>
                    <span className="text-[9px] uppercase tracking-wider text-[#64748b]">cons.</span>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      'rounded border px-2 py-0.5 text-xs font-semibold',
                      stanceChip(a.recommendation),
                    )}
                  >
                    {a.recommendation.replace('_', ' ')}
                  </span>
                  {a.is_split && (
                    <span className="rounded border border-[#94a3b8]/40 bg-[#1e293b] px-2 py-0.5 text-xs text-[#94a3b8]">
                      SPLIT COUNCIL
                    </span>
                  )}
                </div>

                {a.dissent.length > 0 && (
                  <div className="mt-3 space-y-1.5">
                    {a.dissent.map((d, i) => (
                      <div
                        key={i}
                        className="rounded border border-[#f59e0b]/50 bg-[#451a03] px-2 py-1.5 text-xs text-[#fbbf24]"
                      >
                        <span className="font-semibold">⚠ {d.persona}</span>{' '}
                        <span className="opacity-80">
                          {d.direction} ({Math.round(d.score ?? 0)} vs cons.{' '}
                          {Math.round(d.consensus ?? 0)})
                        </span>
                        <ul className="mt-1 list-disc pl-4 opacity-90">
                          {(d.why ?? []).slice(0, 2).map((w, j) => (
                            <li key={j}>{w}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}

                <button
                  onClick={() => setExpanded(isOpen ? null : a.symbol)}
                  className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-[#22c55e] hover:underline"
                >
                  <Gavel className="h-3.5 w-3.5" />
                  {isOpen ? 'Hide' : 'Show'} persona verdicts ({a.verdicts.length})
                  <ChevronDown
                    className={cn('h-3.5 w-3.5 transition-transform', isOpen && 'rotate-180')}
                  />
                </button>

                {isOpen && (
                  <ul className="mt-2 space-y-2 border-t border-[#1e293b] pt-2">
                    {a.verdicts.map((v, i) => (
                      <li key={i} className="text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-[#e2e8f0]">{v.persona}</span>
                            <span
                              className={cn(
                                'rounded border px-1.5 py-px text-[10px] font-semibold',
                                stanceChip(v.stance),
                              )}
                            >
                              {v.stance.replace('_', ' ')}
                            </span>
                          </div>
                          <span className={cn('font-mono font-bold', scoreColor(v.score))}>
                            {Math.round(v.score)}
                          </span>
                        </div>
                        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[#94a3b8]">
                          {(v.bullets ?? []).map((b, j) => (
                            <li key={j}>{b}</li>
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
