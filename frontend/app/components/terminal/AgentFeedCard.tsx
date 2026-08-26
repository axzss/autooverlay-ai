'use client'

import { useState } from 'react'
import { ChevronDown, ChevronRight, Play, CheckCircle2, XCircle } from 'lucide-react'
import {
  api,
  riskBadgeClasses,
  type FeedEntry,
  type TradeResponse,
} from '../../../lib/api'

type ExecuteState =
  | { phase: 'idle' }
  | { phase: 'confirm' }
  | { phase: 'submitting' }
  | { phase: 'done'; ok: boolean; message: string }

function ActionPill({ action }: { action: string }) {
  const cls =
    action === 'Initiate Position'
      ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
      : action === 'Take Profit'
        ? 'border-[#2dd4bf]/50 bg-[#042f2e] text-[#2dd4bf]'
        : action === 'Stop Loss'
          ? 'border-[#ef4444]/50 bg-[#450a0a] text-[#f87171]'
          : action === 'Roll Position'
            ? 'border-[#818cf8]/50 bg-[#1e1b4b] text-[#a5b4fc]'
            : 'border-[#334155] bg-[#0f172a] text-[#94a3b8]'
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${cls}`}>
      {action}
    </span>
  )
}

export default function AgentFeedCard({ entry }: { entry: FeedEntry }) {
  const [thinkingOpen, setThinkingOpen] = useState(false)
  const [exec, setExec] = useState<ExecuteState>({ phase: 'idle' })

  const canExecute = entry.rawAction === 'INITIATE_POSITION'

  async function handleExecute() {
    setExec({ phase: 'submitting' })
    try {
      const res: TradeResponse = await api.placeTrade({
        symbol: entry.optionSymbol ?? entry.symbol,
        qty: entry.contracts,
        side: 'sell',
        type: 'market',
        time_in_force: 'day',
      })
      setExec({
        phase: 'done',
        ok: true,
        message:
          res.mode === 'mock' || res.submitted === false
            ? `Mock mode — order validated but not submitted (${String(res.reason ?? 'backend not configured')})`
            : `Order submitted: ${res.order?.symbol ?? entry.symbol} x${res.order?.qty ?? entry.contracts} — status ${res.order?.status ?? 'accepted'}`,
      })
    } catch (err) {
      setExec({
        phase: 'done',
        ok: false,
        message: err instanceof Error ? err.message : 'Trade failed',
      })
    }
  }

  return (
    <div className="rounded border border-[#1e293b] bg-[#0f172a] p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-semibold text-white">{entry.symbol}</span>
        <span className="inline-flex items-center rounded border border-[#334155] bg-[#020617] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[#94a3b8]">
          {entry.strategyType.replace(/_/g, ' ')}
        </span>
        <ActionPill action={entry.action} />
        <span
          className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium ${riskBadgeClasses(entry.riskScore)}`}
          title={entry.riskDerived ? 'Risk score estimated client-side (backend omitted it)' : undefined}
        >
          Risk {entry.riskScore}/100{entry.riskDerived ? '*' : ''}
        </span>
        {entry.premiumYieldPct !== null && (
          <span className="text-xs text-[#2dd4bf]">
            {(entry.premiumYieldPct).toFixed(1)}% annualized premium yield
          </span>
        )}
        <div className="ml-auto">
          {!canExecute ? null : exec.phase === 'confirm' ? (
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-[#94a3b8]">
                Sell to open {entry.contracts} {entry.optionSymbol ?? entry.symbol}?
              </span>
              <button
                onClick={handleExecute}
                className="inline-flex items-center gap-1 rounded border border-[#22c55e]/60 bg-[#052e16] px-2 py-1 text-xs font-medium text-[#22c55e] hover:bg-[#22c55e]/10"
              >
                <Play className="h-3 w-3" />
                Confirm
              </button>
              <button
                onClick={() => setExec({ phase: 'idle' })}
                className="rounded border border-[#334155] px-2 py-1 text-xs text-[#94a3b8] hover:text-white"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setExec({ phase: 'confirm' })}
              className="inline-flex items-center gap-1 rounded border border-[#22c55e]/50 bg-transparent px-2 py-1 text-xs font-medium text-[#22c55e] hover:bg-[#22c55e]/10"
            >
              <Play className="h-3 w-3" />
              Execute
            </button>
          )}
        </div>
      </div>

      {(entry.optionSymbol || entry.strike !== null || entry.expiration) && (
        <p className="font-mono text-[11px] text-[#64748b]">
          {[entry.optionSymbol, entry.strike !== null ? `$${entry.strike}` : null, entry.expiration]
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}

      <button
        onClick={() => setThinkingOpen((o) => !o)}
        className="flex items-center gap-1 text-xs text-[#94a3b8] hover:text-white transition-colors"
      >
        {thinkingOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        Agent thinking ({entry.reasoningSteps.length} steps)
      </button>
      {thinkingOpen && (
        <ol className="space-y-1 border-l border-[#1e293b] pl-3">
          {entry.reasoningSteps.map((step, i) => (
            <li key={i} className="flex gap-2 text-xs text-[#cbd5e1]">
              <span className="shrink-0 font-mono text-[#64748b]">{i + 1}.</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      )}

      {exec.phase === 'done' && (
        <p
          className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 text-xs ${
            exec.ok
              ? 'border-[#22c55e]/40 bg-[#052e16] text-[#22c55e]'
              : 'border-[#ef4444]/40 bg-[#450a0a] text-[#f87171]'
          }`}
        >
          {exec.ok ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
          {exec.message}
        </p>
      )}
    </div>
  )
}
