'use client'

import { useEffect, useState } from 'react'
import { Loader2, Play, Square, AlertTriangle, CheckCircle2, Timer, ToggleLeft, ToggleRight } from 'lucide-react'
import { api, type BotStatusResponse } from '@/../lib/api'

export default function BotSchedulerCard() {
  const [status, setStatus] = useState<BotStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [autoSaving, setAutoSaving] = useState(false)

  const load = async () => {
    try {
      const data = await api.getBotStatus()
      setStatus(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load bot status')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setInterval>
    load()
    timer = setInterval(load, 15_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const run = async (action: 'start' | 'stop' | 'cycle') => {
    setActionLoading(action)
    setError(null)
    try {
      if (action === 'start') await api.startBot()
      else if (action === 'stop') await api.stopBot()
      else await api.triggerBotCycle()
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bot action failed')
    } finally {
      setActionLoading(null)
    }
  }

  const setAutoExecute = async (value: boolean) => {
    setAutoSaving(true)
    setError(null)
    try {
      await api.configureBot({ autonomous_execution: value })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update auto execute')
      await load()
    } finally {
      setAutoSaving(false)
    }
  }

  const resumeAfterCooldown = async () => {
    setError(null)
    setActionLoading('cycle')
    try {
      await api.triggerBotCycle()
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to resume cycle')
    } finally {
      setActionLoading(null)
    }
  }

  const nextIn = (() => {
    if (!status?.next_run_at) return null
    const next = new Date(status.next_run_at).getTime()
    const now = Date.now()
    const diff = Math.max(0, next - now)
    const m = Math.floor(diff / 60000)
    const s = Math.floor((diff % 60000) / 1000)
    return `${m}m ${s}s`
  })()

  return (
    <div className="rounded border border-[#1e293b] bg-[#0f172a] p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">
            Bot Scheduler
          </h2>
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-[#64748b]" />}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => run('start')}
            disabled={actionLoading === 'start' || status?.running}
            title="Start automatic scheduler"
            className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-[10px] font-semibold disabled:opacity-50 ${
              status?.running
                ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
                : 'border-[#22c55e]/50 bg-[#0f172a] text-[#22c55e] hover:bg-[#22c55e]/10'
            }`}
          >
            {actionLoading === 'start' ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
            {status?.running ? 'Scheduler ON' : 'Start Scheduler'}
          </button>
          <button
            onClick={() => run('stop')}
            disabled={actionLoading === 'stop' || !status?.running}
            title="Stop automatic scheduler"
            className="inline-flex items-center gap-1 rounded border border-[#ef4444]/50 bg-[#450a0a] px-2 py-1 text-[10px] font-semibold text-[#f87171] hover:bg-[#7f1d1d] disabled:opacity-50"
          >
            {actionLoading === 'stop' ? <Loader2 className="h-3 w-3 animate-spin" /> : <Square className="h-3 w-3" />}
            Stop
          </button>
          <button
            onClick={() => run('cycle')}
            disabled={actionLoading === 'cycle'}
            title="Run one cycle now"
            className="inline-flex items-center gap-1 rounded border border-[#f59e0b]/50 bg-[#451a03] px-2 py-1 text-[10px] font-semibold text-[#fbbf24] hover:bg-[#78350f] disabled:opacity-50"
          >
            {actionLoading === 'cycle' ? <Loader2 className="h-3 w-3 animate-spin" /> : <Timer className="h-3 w-3" />}
            Run Now
          </button>
        </div>
      </div>

      <p className="text-[10px] text-[#64748b]">
        Start/Stop turns the automatic scheduler on or off. Run Now executes one immediate cycle without changing the scheduler.
      </p>

      {error && (
        <p className="flex items-center gap-2 rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 text-xs text-[#f87171]">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      )}

      {loading ? (
        <div className="space-y-1.5">
          <div className="h-3 w-40 animate-pulse rounded bg-[#1e293b]" />
          <div className="h-3 w-56 animate-pulse rounded bg-[#1e293b]" />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2 text-xs">
          <Stat label="Running" value={status?.running ? 'ON' : 'OFF'} ok={status?.running} />
          <button
            onClick={() => setAutoExecute(!(status?.autonomous_execution ?? false))}
            disabled={actionLoading === 'cycle' || autoSaving || Boolean(status?.circuit_breaker?.open)}
            className="rounded border border-[#1e293b] bg-[#020617] px-2 py-1.5 flex items-center justify-between text-left disabled:opacity-50"
          >
            <span className="text-[#94a3b8]">Auto execute</span>
            <span className={`flex items-center gap-1 font-mono ${status?.autonomous_execution && !status?.circuit_breaker?.open ? 'text-[#22c55e]' : 'text-[#f87171]'}`}>
              {autoSaving ? <Loader2 className="h-3 w-3 animate-spin" /> : status?.autonomous_execution && !status?.circuit_breaker?.open ? <ToggleRight className="h-3.5 w-3.5" /> : <ToggleLeft className="h-3.5 w-3.5" />}
              {status?.circuit_breaker?.open ? 'BREAKER' : status?.autonomous_execution ? 'ON' : 'OFF'}
            </span>
          </button>
          <Stat label="Mode" value={status?.alpaca_configured ? 'Live' : 'Mock'} ok={status?.alpaca_configured} />
          <Stat label="Runs" value={String(status?.run_count ?? 0)} />
          <Stat label="Last run" value={status?.last_run_at ? new Date(status.last_run_at).toLocaleString() : '—'} />
          <Stat label="Next run" value={status?.next_run_at ? `${new Date(status.next_run_at).toLocaleTimeString()} (${nextIn ?? '—'})` : '—'} />
        </div>
      )}

      {status?.circuit_breaker?.open && (
        <p className="flex items-center gap-2 rounded border border-[#f59e0b]/40 bg-[#451a03] px-3 py-2 text-xs text-[#fbbf24]">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          Circuit breaker open: {status.circuit_breaker.last_failure_category ?? 'unknown'} — {status.circuit_breaker.last_failure_reason ?? ''}
          {status.circuit_breaker.until ? ` until ${new Date(status.circuit_breaker.until).toLocaleTimeString()}` : ''}
        </p>
      )}

      {status?.circuit_breaker?.open && status?.circuit_breaker?.until && new Date(status.circuit_breaker.until) <= new Date() && (
        <button
          onClick={() => resumeAfterCooldown()}
          disabled={actionLoading === 'cycle'}
          className="w-full rounded border border-[#22c55e]/50 bg-[#052e16] px-2 py-1.5 text-[10px] font-semibold text-[#22c55e] hover:bg-[#0a3318] disabled:opacity-50"
        >
          {actionLoading === 'cycle' ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          Resume after cooldown
        </button>
      )}

      {status?.last_alert && (
        <p className="flex items-center gap-2 rounded border border-[#f59e0b]/40 bg-[#451a03] px-3 py-2 text-[10px] text-[#fbbf24]">
          Last alert: {status.last_alert.category} | {status.last_alert.reason} | consecutive failures: {String(status.last_alert.consecutive_failures ?? 0)}
        </p>
      )}

      {status?.last_error && (
        <p className="rounded border border-[#f59e0b]/40 bg-[#451a03] px-3 py-2 text-xs text-[#fbbf24]">
          Last error: {status.last_error}
        </p>
      )}
    </div>
  )
}

function Stat({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="rounded border border-[#1e293b] bg-[#020617] px-2 py-1.5 flex items-center justify-between">
      <span className="text-[#94a3b8]">{label}</span>
      <span className={`flex items-center gap-1 font-mono ${typeof ok === 'boolean' ? (ok ? 'text-[#22c55e]' : 'text-[#f87171]') : 'text-[#e2e8f0]'}`}>
        {typeof ok === 'boolean' && (ok ? <CheckCircle2 className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />)}
        {value}
      </span>
    </div>
  )
}
