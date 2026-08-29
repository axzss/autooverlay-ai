'use client'

import { Bot, Loader2, Play, AlertTriangle, ShieldAlert } from 'lucide-react'
import { AnimatePresence } from 'framer-motion'
import { useAgentRun } from './AgentRunProvider'
import type { OrderIntent } from '../../lib/api'
import {
  motion,
  useReducedMotion,
  EASE,
  DURATION,
  pressable,
} from '@/components/motion/primitives'

/**
 * Manual trigger for POST /api/agent/run.
 *
 * Recommendation-only: the backend has no auto-submit path, always returns
 * orders_ready=false, and every intent carries requires_approval=true. This card
 * must never call /api/trade.
 */
export default function AgentControl() {
  const { run, running, error, runAgent } = useAgentRun()
  const reduce = useReducedMotion()

  const halted = run?.risk_summary?.halted === true
  const haltReasons = run?.risk_summary?.kill_switch?.reasons ?? []
  const intents: OrderIntent[] = run?.order_intents ?? []
  const directiveCount = run?.recommendations?.length ?? 0
  const blocked = run?.risk_summary?.blocked_entries ?? 0

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e293b] flex items-center gap-2">
        <Bot className="h-4 w-4 text-[#22c55e]" />
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider">AI Agent Control</h3>
        {run && (
          <span className="ml-auto rounded border border-[#334155] bg-[#020617] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-[#94a3b8]">
            {run.mode}
          </span>
        )}
      </div>

      <div className="p-4 space-y-3">
        <p className="text-sm text-[#94a3b8]">
          Run the analysis pipeline now. Returns recommendations and prepared
          orders — nothing is sent to the broker.
        </p>

        <motion.button
          onClick={runAgent}
          disabled={running}
          className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50"
          {...(reduce ? {} : pressable)}
        >
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? 'Running analysis…' : 'Run Agent Now'}
        </motion.button>

        <AnimatePresence initial={false}>
          {error && (
            <motion.p
              key="err"
              initial={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
              animate={reduce ? { opacity: 1 } : { opacity: 1, height: 'auto' }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
              transition={reduce ? { duration: 0 } : { duration: DURATION.base, ease: EASE }}
              className="flex items-start gap-2 overflow-hidden rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 text-xs text-[#f87171]"
            >
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {error}
            </motion.p>
          )}
        </AnimatePresence>

        {/* Kill-switch is checked first in the cycle: when halted, no directives
            and no intents are produced at all. Show why, not an empty table. */}
        <AnimatePresence initial={false}>
          {halted && (
            <motion.div
              key="halt"
              initial={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
              animate={reduce ? { opacity: 1 } : { opacity: 1, height: 'auto' }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
              transition={reduce ? { duration: 0 } : { duration: DURATION.base, ease: EASE }}
              className="overflow-hidden rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 space-y-1"
            >
              <p className="flex items-center gap-2 text-xs font-semibold text-[#f87171]">
                <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
                Kill-switch HALT — trading suspended
              </p>
              {haltReasons.map((reason, i) => (
                <p key={i} className="pl-5 text-[11px] leading-snug text-[#fca5a5]">
                  {reason}
                </p>
              ))}
              <p className="pl-5 text-[10px] text-[#94a3b8]">
                No new entries were evaluated. Adjust thresholds in Settings or wait
                for the portfolio to recover.
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {run && !halted && (
          <motion.div
            className="space-y-2"
            initial={reduce ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={reduce ? { duration: 0 } : { duration: DURATION.base, ease: EASE }}
          >
            <div className="flex flex-wrap gap-2 text-[10px]">
              <span className="rounded border border-[#334155] bg-[#020617] px-2 py-0.5 text-[#94a3b8]">
                {directiveCount} directive{directiveCount === 1 ? '' : 's'}
              </span>
              <span className="rounded border border-[#334155] bg-[#020617] px-2 py-0.5 text-[#94a3b8]">
                {intents.length} order intent{intents.length === 1 ? '' : 's'}
              </span>
              <span className="rounded border border-[#64748b]/50 bg-[#1e293b] px-2 py-0.5 text-[#94a3b8]">
                {run.orders_ready ? 'orders ready' : 'not submitted'}
              </span>
              {blocked > 0 && (
                <span className="rounded border border-[#f59e0b]/50 bg-[#451a03] px-2 py-0.5 text-[#fbbf24]">
                  {blocked} blocked
                </span>
              )}
            </div>

            {intents.length === 0 ? (
              <p className="text-xs text-[#64748b]">
                No order intents — the cycle produced no INITIATE directives.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {intents.map((intent, i) => (
                  <li
                    key={`${intent.symbol}-${intent.option_symbol ?? i}-${i}`}
                    className="rounded border border-[#1e293b] bg-[#0a0f1a] px-2.5 py-2 space-y-1"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="rounded border border-[#22c55e]/50 bg-[#052e16] px-1.5 py-0.5 text-[10px] font-semibold text-[#22c55e]">
                        {intent.action}
                      </span>
                      <span className="text-sm font-medium text-white">{intent.symbol}</span>
                      <span className="text-[10px] text-[#94a3b8]">{intent.strategy}</span>
                      <span className="ml-auto text-[10px] tabular-nums text-[#e2e8f0]">
                        {intent.contracts}x
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2 text-[10px] text-[#64748b]">
                      <span className="font-mono">{intent.option_symbol ?? 'contract pending'}</span>
                      <span className="uppercase">{intent.type}</span>
                      <span className="tabular-nums">
                        {typeof intent.limit_price === 'number'
                          ? `limit ${intent.limit_price.toFixed(2)}`
                          : 'no limit set'}
                      </span>
                      {intent.requires_approval && !intent.submitted && (
                        <span className="rounded border border-[#f59e0b]/50 bg-[#451a03] px-1.5 text-[#fbbf24]">
                          needs approval
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </motion.div>
        )}

        {!run && !error && !running && (
          <p className="text-xs text-[#64748b]">
            Not run yet. Results appear here and in the reasoning panel below.
          </p>
        )}
      </div>
    </div>
  )
}
