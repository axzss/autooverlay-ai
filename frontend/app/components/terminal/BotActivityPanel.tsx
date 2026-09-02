'use client'

import { useEffect, useRef, useState } from 'react'
import { Loader2, AlertTriangle } from 'lucide-react'
import { api } from '../../../lib/api'

type BotHistoryItem = Record<string, unknown>

function parseLog(line: string) {
  const m = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s*\|\s*(INFO|DEBUG|WARNING|ERROR|CRITICAL)\s*\|\s*([^|]+?)\s*\|\s*(.*)$/)
  if (!m) return { time: '', level: '', component: '', message: line, raw: line }
  const [, time, level, component, message] = m
  const statusMatch = message.match(/(HTTP\/[\d.]+)\s+(\d{3})/)
  const status = statusMatch ? statusMatch[2] : null
  return { time, level: level.toUpperCase(), component: component.trim(), message, status, raw: line }
}

const levelColor: Record<string, string> = {
  INFO: 'text-[#94a3b8]',
  DEBUG: 'text-[#64748b]',
  WARNING: 'text-[#fbbf24]',
  ERROR: 'text-[#f87171]',
  CRITICAL: 'text-[#f87171]',
}

const statusColor = (code: string | null) => {
  if (!code) return 'text-[#94a3b8]'
  if (code.startsWith('2')) return 'text-[#22c55e]'
  if (code.startsWith('3')) return 'text-[#60a5fa]'
  if (code.startsWith('4')) return 'text-[#fbbf24]'
  if (code.startsWith('5')) return 'text-[#f87171]'
  return 'text-[#94a3b8]'
}

export default function BotActivityPanel() {
  const [history, setHistory] = useState<BotHistoryItem[]>([])
  const [logs, setLogs] = useState<{ line: string }[]>([])
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [loadingLogs, setLoadingLogs] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<Record<string, any> | null>(null)
  const logScrollRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const el = logScrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [logs])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [h, l, s] = await Promise.all([
          api.getBotHistory(20),
          api.getBotLogs(80, 'INFO'),
          api.getBotStatus().catch(() => null),
        ])
        if (!cancelled) {
          setHistory(h.history ?? [])
          setLogs(l.entries ?? [])
          setStatus(s)
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load bot activity')
      } finally {
        if (!cancelled) {
          setLoadingHistory(false)
          setLoadingLogs(false)
        }
      }
    }
    load()
    const timer = setInterval(load, 20_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  return (
    <div className="rounded border border-[#1e293b] bg-[#0f172a] p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">
          Bot Activity
        </h2>
        <span className="text-[10px] text-[#64748b]">Auto-refresh every 20s</span>
      </div>

      {error && (
        <p className="flex items-center gap-2 rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 text-xs text-[#f87171]">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="space-y-2">
          <p className="text-[10px] uppercase tracking-wider text-[#64748b]">Recent Runs</p>
          {loadingHistory ? (
            <div className="space-y-2">
              <div className="h-3 w-full animate-pulse rounded bg-[#1e293b]" />
              <div className="h-3 w-5/6 animate-pulse rounded bg-[#1e293b]" />
            </div>
          ) : history.length === 0 ? (
            <p className="text-xs text-[#64748b]">No autonomous runs yet.</p>
          ) : (
            <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
              {history.map((item, idx) => (
                <RunRow key={idx} item={item} />
              ))}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-[10px] uppercase tracking-wider text-[#64748b]">Live Logs</p>
          {loadingLogs ? (
            <div className="space-y-2">
              <div className="h-3 w-full animate-pulse rounded bg-[#1e293b]" />
              <div className="h-3 w-4/6 animate-pulse rounded bg-[#1e293b]" />
            </div>
          ) : logs.length === 0 ? (
            <p className="text-xs text-[#64748b]">No logs found. Set LOG_DIR or BOT_LOG_PATH.</p>
          ) : (
            <div ref={logScrollRef} className="space-y-1 max-h-48 overflow-y-auto pr-1 font-mono text-[11px] leading-snug log-scroll">
              {logs.map((entry, idx) => {
                const parsed = parseLog(entry.line)
                return (
                  <div key={idx} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[#cbd5e1]">
                    <span className="text-[#64748b] shrink-0">{parsed.time}</span>
                    {parsed.status && (
                      <span className={`shrink-0 ${statusColor(parsed.status)}`}>{parsed.status}</span>
                    )}
                    <span className={`shrink-0 ${levelColor[parsed.level] || 'text-[#94a3b8]'}`}>{parsed.level}</span>
                    <span className="text-[#94a3b8]">{parsed.component}</span>
                    <span className="break-all text-[#e2e8f0]">{parsed.message}</span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function RunRow({ item }: { item: BotHistoryItem }) {
  const summaryStatus = String(item.summary?.status ?? '')
  const errorText = String(item.error ?? '')
  const halted = Boolean(item.halted)
  const skipReason = String(item.reason ?? '')
  const mode = String(item.mode ?? 'unknown')

  let status = 'unknown'
  if (errorText || summaryStatus === 'error') status = 'error'
  else if (halted || summaryStatus === 'halted') status = 'halted'
  else if (skipReason || summaryStatus === 'skipped') status = 'skipped'
  else if (summaryStatus === 'completed') status = 'completed'

  const reason = [errorText, skipReason].filter(Boolean).join(' | ') || summaryStatus
  const started = item.started_at ? new Date(String(item.started_at)).toLocaleTimeString() : '—'
  const submitted = Number(item.orders_submitted ?? 0)
  const blocked = Number(item.orders_blocked ?? 0)
  const evaluated = Number(item.orders_evaluated ?? 0)

  let border = 'border-[#1e293b] bg-[#0a0f1a]'
  let statusColor = 'text-[#94a3b8]'
  if (status === 'completed' || status === 'submitted') {
    border = 'border-[#22c55e]/40 bg-[#052e16]'
    statusColor = 'text-[#22c55e]'
  } else if (status === 'skipped' || status === 'halted') {
    border = 'border-[#f59e0b]/40 bg-[#451a03]'
    statusColor = 'text-[#fbbf24]'
  } else if (status === 'error') {
    border = 'border-[#ef4444]/40 bg-[#450a0a]'
    statusColor = 'text-[#f87171]'
  }

  return (
    <div className={`rounded border ${border} px-2.5 py-2 space-y-1`}>
      <div className="flex items-center justify-between">
        <span className={`text-[10px] font-semibold uppercase ${statusColor}`}>{status}</span>
        <span className="text-[10px] text-[#64748b]">{started}</span>
      </div>
      <div className="flex flex-wrap gap-2 text-[10px] text-[#94a3b8]">
        <span>mode: {mode}</span>
        <span>evaluated: {evaluated}</span>
        <span>submitted: {submitted}</span>
        <span>blocked: {blocked}</span>
      </div>
      {reason && (
        <p className="text-[10px] text-[#fbbf24]">{reason}</p>
      )}
    </div>
  )
}
