'use client'

import { useCallback, useEffect, useState } from 'react'
import { Loader2, RefreshCw, Zap, AlertTriangle, ClipboardList } from 'lucide-react'
import {
  api,
  normalizeScreenings,
  toFeedEntry,
  type AgentRecommendation,
  type AgentRunResponse,
  type CycleResponse,
  type DailyDirective,
  type FeedEntry,
  type OrderIntent,
  type PortfolioContext,
} from '../../../lib/api'
import AgentFeedCard from './AgentFeedCard'
import YieldBars, { type YieldBar } from '@/components/charts/YieldBars'
import { ChevronDown, ChevronRight } from 'lucide-react'

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
  const [liveError, setLiveError] = useState<string | null>(null)
  const [lastRun, setLastRun] = useState<string | null>(null)

  // Daily Cycle state
  const [directives, setDirectives] = useState<DailyDirective[]>([])
  const [cycleRunning, setCycleRunning] = useState(false)
  const [cycleError, setCycleError] = useState<string | null>(null)
  const [lastCycleRun, setLastCycleRun] = useState<string | null>(null)
  const [halted, setHalted] = useState(false)
  const [expandedDirectives, setExpandedDirectives] = useState<Set<number>>(new Set())

  // Agent Run (order intent preview) state
  const [agentRun, setAgentRun] = useState<AgentRunResponse | null>(null)
  const [agentRunning, setAgentRunning] = useState(false)
  const [agentError, setAgentError] = useState<string | null>(null)

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
      setLiveError(norm.liveError)
      setLastRun(new Date().toLocaleTimeString())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent cycle failed')
      setEntries([])
      setLiveError(null)
    } finally {
      setLoading(false)
      setRunning(false)
    }
  }, [])

  const runDailyCycle = useCallback(async () => {
    setCycleRunning(true)
    setCycleError(null)
    try {
      const res = await api.runDailyCycle()
      setDirectives(res.directives ?? [])
      setHalted(res.halted ?? false)
      setLastCycleRun(new Date().toLocaleTimeString())
    } catch (err) {
      setCycleError(err instanceof Error ? err.message : 'Daily cycle failed')
      setDirectives([])
    } finally {
      setCycleRunning(false)
    }
  }, [])

  const toggleDirective = useCallback((idx: number) => {
    setExpandedDirectives(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }, [])

  const runAgent = useCallback(async () => {
    setAgentRunning(true)
    setAgentError(null)
    try {
      const res = await api.runAgent()
      setAgentRun(res)
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : 'Agent run failed')
      setAgentRun(null)
    } finally {
      setAgentRunning(false)
    }
  }, [])

  useEffect(() => {
    runCycle(true)
  }, [runCycle])

  // Only candidates that actually reported a yield — a bar at 0% for a missing
  // value would read as "no premium" rather than "not provided".
  const yieldBars: YieldBar[] = entries
    .filter((e) => typeof e.premiumYieldPct === 'number')
    .map((e) => ({
      label: e.symbol,
      value: e.premiumYieldPct as number,
      flagged: e.riskScore >= 60,
    }))

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

        {liveError && (
          <div className="flex items-start gap-2 rounded border border-[#b45309]/40 bg-[#451a03] px-3 py-2 text-sm text-[#fbbf24]">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Live market data failed — showing fallback data.{' '}
              <span className="font-mono text-xs text-[#fcd34d] break-words">{liveError}</span>
            </span>
          </div>
        )}

        {loading ? (
          <Skeleton />
        ) : entries.length === 0 && !error ? (
          <div className="rounded border border-[#1e293b] bg-[#0f172a] p-8 text-center">
            <RefreshCw className="mx-auto mb-2 h-6 w-6 text-[#334155]" />
            <p className="text-sm text-[#94a3b8]">No overlay recommendations right now.</p>
          </div>
        ) : (
          <>
            {/* Relative premium yield across candidates — comparison at a glance
                before reading the individual cards. Amber marks risk >= 60. */}
            {yieldBars.length > 1 && (
              <div className="rounded border border-[#1e293b] bg-[#0f172a] p-4">
                <div className="mb-3 flex items-baseline justify-between">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">
                    Annualised premium yield
                  </h2>
                  <span className="text-[10px] text-[#64748b]">amber = risk score ≥ 60</span>
                </div>
                <YieldBars bars={yieldBars} />
              </div>
            )}
            {entries.map((entry) => (
              <AgentFeedCard key={entry.key} entry={entry} />
            ))}
          </>
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

        {/* ── Daily Cycle panel ─────────────────────────────────────── */}
        <div className="rounded border border-[#1e293b] bg-[#0f172a] p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">
              Daily Cycle
            </h2>
            <div className="flex items-center gap-2">
              {lastCycleRun && (
                <span className="text-[10px] text-[#64748b]">
                  Last run: {lastCycleRun}
                </span>
              )}
              <button
                onClick={runDailyCycle}
                disabled={cycleRunning}
                className="inline-flex items-center gap-2 rounded border border-[#22c55e]/50 bg-[#0f172a] px-3 py-1.5 text-xs font-medium text-[#22c55e] hover:bg-[#22c55e]/10 transition-colors disabled:opacity-50"
              >
                {cycleRunning ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Zap className="h-3.5 w-3.5" />
                )}
                {cycleRunning ? 'Running…' : 'Run Daily Cycle'}
              </button>
            </div>
          </div>

          {halted && (
            <p className="flex items-center gap-2 rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 text-xs text-[#f87171]">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              Kill-switch HALT — all trading suspended
            </p>
          )}

          {cycleError && (
            <p className="flex items-center gap-2 rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 text-xs text-[#f87171]">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              {cycleError}
            </p>
          )}

          {directives.length === 0 && !cycleError && !halted && (
            <p className="text-xs text-[#64748b] text-center py-3">
              No directives yet — run the daily cycle to generate a directive list.
            </p>
          )}

          <div className="space-y-2">
            {directives.map((d, idx) => {
              const expanded = expandedDirectives.has(idx)
              const actionColor: Record<string, string> = {
                INITIATE: 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]',
                HOLD: 'border-[#64748b]/50 bg-[#1e293b] text-[#94a3b8]',
                MONITOR: 'border-[#f59e0b]/50 bg-[#451a03] text-[#fbbf24]',
                EXIT: 'border-[#ef4444]/50 bg-[#450a0a] text-[#f87171]',
                ROLL: 'border-[#3b82f6]/50 bg-[#172554] text-[#60a5fa]',
              }
              const badge = actionColor[d.action] ?? actionColor.HOLD
              const traceLines = Array.isArray(d.reasoning_trace) ? d.reasoning_trace : []
              const provChips = Array.isArray(d.provenance) ? d.provenance : []

              return (
                <div
                  key={`${d.symbol}-${d.action}-${idx}`}
                  className="rounded border border-[#1e293b] bg-[#0a0f1a] p-3 space-y-1.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`rounded border px-2 py-0.5 text-[10px] font-semibold ${badge}`}>
                        {d.action}
                      </span>
                      <span className="text-sm font-medium text-white">{d.symbol}</span>
                      <span className="text-[10px] text-[#64748b]">
                        P{d.priority}
                      </span>
                    </div>
                    <button
                      onClick={() => toggleDirective(idx)}
                      className="text-[#64748b] hover:text-[#94a3b8] transition-colors"
                      aria-label={expanded ? 'Collapse' : 'Expand'}
                    >
                      {expanded
                        ? <ChevronDown className="h-4 w-4" />
                        : <ChevronRight className="h-4 w-4" />}
                    </button>
                  </div>

                  {provChips.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {provChips.map((p, pi) => (
                        <span
                          key={pi}
                          className="rounded border border-[#334155] bg-[#020617] px-1.5 py-0.5 text-[9px] text-[#94a3b8]"
                        >
                          {p.source}
                          {p.detail ? `: ${p.detail.slice(0, 48)}` : ''}
                        </span>
                      ))}
                    </div>
                  )}

                  {expanded && traceLines.length > 0 && (
                    <div className="rounded border border-[#1e293b] bg-[#020617] p-2 space-y-0.5">
                      {traceLines.map((line, li) => (
                        <p key={li} className="text-[11px] text-[#94a3b8] font-mono leading-snug">
                          {line}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
        {/* ── end Daily Cycle panel ─────────────────────────────────── */}

        {/* ── Agent Run — order intent preview ──────────────────────── */}
        <div className="rounded border border-[#1e293b] bg-[#0f172a] p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">
                Agent Run — order preview
              </h2>
              {agentRun && (
                <span className="rounded border border-[#334155] bg-[#020617] px-1.5 py-0.5 text-[9px] uppercase text-[#94a3b8]">
                  {agentRun.mode}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {agentRun?.completed_at && (
                <span className="text-[10px] text-[#64748b]">
                  {new Date(agentRun.completed_at).toLocaleTimeString()}
                </span>
              )}
              <button
                onClick={runAgent}
                disabled={agentRunning}
                className="inline-flex items-center gap-2 rounded border border-[#22c55e]/50 bg-[#0f172a] px-3 py-1.5 text-xs font-medium text-[#22c55e] hover:bg-[#22c55e]/10 transition-colors disabled:opacity-50"
              >
                {agentRunning ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ClipboardList className="h-3.5 w-3.5" />
                )}
                {agentRunning ? 'Running…' : 'Run agent (preview)'}
              </button>
            </div>
          </div>

          <p className="text-[11px] text-[#64748b]">
            Preview only — nothing is sent to the broker. Every intent needs explicit approval
            before it becomes an order.
          </p>

          {agentError && (
            <p className="flex items-center gap-2 rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 text-xs text-[#f87171]">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              {agentError}
            </p>
          )}

          {agentRun?.risk_summary?.halted && (
            <p className="flex items-center gap-2 rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 text-xs text-[#f87171]">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              Kill-switch HALT — no order intents generated
              {agentRun.risk_summary.kill_switch?.reasons?.length
                ? `: ${agentRun.risk_summary.kill_switch.reasons.join('; ')}`
                : ''}
            </p>
          )}

          {agentRun && !agentRunning && (
            <div className="flex flex-wrap gap-2 text-[10px]">
              <span className="rounded border border-[#334155] bg-[#020617] px-2 py-0.5 text-[#94a3b8]">
                {agentRun.recommendations?.length ?? 0} directives
              </span>
              <span className="rounded border border-[#334155] bg-[#020617] px-2 py-0.5 text-[#94a3b8]">
                {agentRun.order_intents?.length ?? 0} intents
              </span>
              <span
                className={`rounded border px-2 py-0.5 ${
                  agentRun.orders_ready
                    ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
                    : 'border-[#64748b]/50 bg-[#1e293b] text-[#94a3b8]'
                }`}
              >
                {agentRun.orders_ready ? 'orders ready' : 'not submitted'}
              </span>
              {typeof agentRun.risk_summary?.blocked_entries === 'number' &&
                agentRun.risk_summary.blocked_entries > 0 && (
                  <span className="rounded border border-[#f59e0b]/50 bg-[#451a03] px-2 py-0.5 text-[#fbbf24]">
                    {agentRun.risk_summary.blocked_entries} blocked
                  </span>
                )}
            </div>
          )}

          {agentRun && (agentRun.order_intents?.length ?? 0) === 0 && !agentError && (
            <p className="text-xs text-[#64748b] text-center py-3">
              No order intents — the cycle produced no INITIATE directives.
            </p>
          )}

          {!agentRun && !agentError && !agentRunning && (
            <p className="text-xs text-[#64748b] text-center py-3">
              Run the agent to preview the orders it would place.
            </p>
          )}

          {(agentRun?.order_intents?.length ?? 0) > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-xs">
                <thead>
                  <tr className="border-b border-[#1e293b] text-[10px] uppercase tracking-wider text-[#64748b]">
                    <th className="px-2 py-1.5 font-medium">Symbol</th>
                    <th className="px-2 py-1.5 font-medium">Action</th>
                    <th className="px-2 py-1.5 font-medium">Strategy</th>
                    <th className="px-2 py-1.5 font-medium">Contract</th>
                    <th className="px-2 py-1.5 font-medium text-right">Qty</th>
                    <th className="px-2 py-1.5 font-medium">Type</th>
                    <th className="px-2 py-1.5 font-medium text-right">Limit</th>
                    <th className="px-2 py-1.5 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(agentRun?.order_intents ?? []).map((intent: OrderIntent, ii: number) => (
                    <tr
                      key={`${intent.symbol}-${intent.option_symbol ?? ii}-${ii}`}
                      className="border-b border-[#1e293b]/60 last:border-0"
                    >
                      <td className="px-2 py-2 font-medium text-white">{intent.symbol}</td>
                      <td className="px-2 py-2">
                        <span className="rounded border border-[#22c55e]/50 bg-[#052e16] px-1.5 py-0.5 text-[10px] font-semibold text-[#22c55e]">
                          {intent.action}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-[#94a3b8]">{intent.strategy}</td>
                      <td className="px-2 py-2 font-mono text-[10px] text-[#94a3b8]">
                        {intent.option_symbol ?? '—'}
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums text-[#e2e8f0]">
                        {intent.contracts}
                      </td>
                      <td className="px-2 py-2 uppercase text-[#94a3b8]">{intent.type}</td>
                      <td className="px-2 py-2 text-right tabular-nums text-[#e2e8f0]">
                        {typeof intent.limit_price === 'number'
                          ? intent.limit_price.toFixed(2)
                          : '—'}
                      </td>
                      <td className="px-2 py-2">
                        <span className="rounded border border-[#f59e0b]/50 bg-[#451a03] px-1.5 py-0.5 text-[10px] text-[#fbbf24]">
                          {intent.submitted
                            ? 'submitted'
                            : intent.requires_approval
                              ? 'needs approval'
                              : 'pending'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        {/* ── end Agent Run panel ───────────────────────────────────── */}
      </main>
    </div>
  )
}
