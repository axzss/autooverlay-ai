'use client'

import { useMemo, useState } from 'react'
import {
  Terminal as TerminalIcon,
  Loader2,
  ChevronRight,
  ShieldAlert,
  Check,
  Ban,
  Gauge,
} from 'lucide-react'
import { AnimatePresence } from 'framer-motion'
import { useAgentRun } from './AgentRunProvider'
import { motion, useReducedMotion, EASE, DURATION } from '@/components/motion/primitives'
import { parseReasoning, groupIsBlocked, type ReasoningGroup, type ReasoningGate } from '../../lib/reasoning'
import { cn } from '@/lib/utils'

/**
 * Shows the reasoning trace from the most recent agent run.
 *
 * This component previously rendered a hardcoded log that claimed an order had
 * been executed and a $120 premium harvested. None of that ever happened.
 *
 * It now renders only what the backend produced, but grouped by symbol rather
 * than as a flat list. The backend returns 41 lines for an eight-symbol run;
 * flat, that reads as a wall of text even though the structure is regular. All
 * reorganisation happens client-side in lib/reasoning.ts — no backend change,
 * no value rewritten, and a "raw" toggle shows the untouched trace.
 */

function tierChip(tier: string | null) {
  if (tier === 'low') return 'border-[#22c55e]/40 text-[#22c55e]'
  if (tier === 'mid') return 'border-[#f59e0b]/40 text-[#f59e0b]'
  if (tier === 'high') return 'border-[#ef4444]/40 text-[#ef4444]'
  return 'border-[#334155] text-[#94a3b8]'
}

function scoreColour(score: number | null) {
  if (score === null) return 'text-[#94a3b8]'
  if (score >= 60) return 'text-[#22c55e]'
  if (score >= 40) return 'text-[#f59e0b]'
  return 'text-[#ef4444]'
}

function SymbolBlock({ group, index }: { group: ReasoningGroup; index: number }) {
  const reduce = useReducedMotion()
  const [open, setOpen] = useState(false)
  const blocked = groupIsBlocked(group)
  const detailCount =
    group.gates.length + (group.citation ? 1 : 0) + (group.override ? 1 : 0) + group.other.length

  return (
    <motion.div
      className="rounded border border-[#1e293b] bg-[#0a0f1a]"
      initial={reduce ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={
        reduce
          ? { duration: 0 }
          : { duration: DURATION.fast, ease: EASE, delay: Math.min(index * 0.04, 0.3) }
      }
    >
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={detailCount === 0}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left disabled:cursor-default"
      >
        <ChevronRight
          className={cn(
            'h-3.5 w-3.5 shrink-0 transition-transform',
            detailCount === 0 ? 'opacity-0' : 'text-[#64748b]',
            open && 'rotate-90',
          )}
        />
        <span className="w-12 shrink-0 font-mono text-xs font-semibold text-white">
          {group.symbol ?? '—'}
        </span>

        <span className={cn('shrink-0 font-mono text-xs tabular-nums', scoreColour(group.consensusScore))}>
          {group.consensusScore?.toFixed(1) ?? '—'}
        </span>
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-[#94a3b8]">
          {group.recommendation ?? ''}
        </span>

        {group.tier && (
          <span
            className={cn(
              'shrink-0 rounded border px-1.5 py-0.5 text-[10px] uppercase',
              tierChip(group.tier),
            )}
          >
            {group.tier}
          </span>
        )}
        {group.volPct !== null && (
          <span className="shrink-0 font-mono text-[10px] tabular-nums text-[#64748b]">
            {group.volPct.toFixed(1)}% vol
          </span>
        )}

        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          {group.override && <Gauge className="h-3.5 w-3.5 text-[#f59e0b]" aria-label="override active" />}
          {blocked ? (
            <span className="flex items-center gap-1 text-[10px] font-medium uppercase text-[#ef4444]">
              <Ban className="h-3 w-3" /> blocked
            </span>
          ) : group.verdict?.kind === 'hold' ? (
            <span className="text-[10px] uppercase text-[#64748b]">hold</span>
          ) : group.verdict?.kind === 'permitted' ? (
            <span className="flex items-center gap-1 text-[10px] font-medium uppercase text-[#22c55e]">
              <Check className="h-3 w-3" /> permitted
            </span>
          ) : null}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && detailCount > 0 && (
          <motion.div
            className="overflow-hidden border-t border-[#1e293b]"
            initial={reduce ? false : { height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
            transition={reduce ? { duration: 0 } : { duration: DURATION.base, ease: EASE }}
          >
            <div className="space-y-2 px-3 py-2.5">
              {group.policy && (
                <p className="font-mono text-[11px] text-[#64748b]">{group.policy}</p>
              )}

              {group.override && (
                <p className="flex gap-1.5 rounded border border-[#f59e0b]/30 bg-[#f59e0b]/5 px-2 py-1.5 text-[11px] text-[#fbbf24]">
                  <Gauge className="mt-0.5 h-3 w-3 shrink-0" />
                  <span>{group.override}</span>
                </p>
              )}

              {group.gates.length > 0 && (
                <ul className="space-y-1">
                  {group.gates.map((gate: ReasoningGate, i: number) => (
                    <li key={i} className="flex items-start gap-1.5 text-[11px]">
                      {gate.status === 'blocked' ? (
                        <Ban className="mt-0.5 h-3 w-3 shrink-0 text-[#ef4444]" />
                      ) : gate.status === 'pass' ? (
                        <Check className="mt-0.5 h-3 w-3 shrink-0 text-[#22c55e]" />
                      ) : (
                        <span className="mt-0.5 h-3 w-3 shrink-0" />
                      )}
                      <span className="w-24 shrink-0 uppercase tracking-wide text-[#64748b]">
                        {gate.label}
                      </span>
                      <span
                        className={cn(
                          'font-mono tabular-nums',
                          gate.status === 'blocked' ? 'text-[#f87171]' : 'text-[#94a3b8]',
                        )}
                      >
                        {gate.detail}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {group.citation && (
                <p className="border-l-2 border-[#334155] pl-2 text-[11px] italic text-[#64748b]">
                  {group.citation}
                </p>
              )}

              {group.verdict && (
                <p
                  className={cn(
                    'text-[11px]',
                    group.verdict.kind === 'blocked' ? 'text-[#f87171]' : 'text-[#94a3b8]',
                  )}
                >
                  {group.verdict.text}
                </p>
              )}

              {group.other.map((line, i) => (
                <p key={i} className="font-mono text-[11px] text-[#94a3b8]">
                  {line}
                </p>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

export default function ThoughtProcess() {
  const { run, running, error } = useAgentRun()
  const reduce = useReducedMotion()
  const [raw, setRaw] = useState(false)

  const trace = run?.reasoning_trace ?? []
  const parsed = useMemo(() => parseReasoning(trace), [trace])
  const blockedCount = parsed.groups.filter(groupIsBlocked).length

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center gap-2 border-b border-[#1e293b] px-4 py-3">
        <TerminalIcon className="h-4 w-4 text-[#22c55e]" />
        <h3 className="text-sm font-semibold uppercase tracking-wider text-white">
          Agent Reasoning
        </h3>
        {running && <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin text-[#64748b]" />}
        {!running && trace.length > 0 && (
          <button
            onClick={() => setRaw((v) => !v)}
            className="ml-auto rounded border border-[#1e293b] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[#64748b] hover:border-[#334155] hover:text-[#94a3b8]"
          >
            {raw ? 'grouped' : 'raw'}
          </button>
        )}
      </div>

      <div className="bg-[#060e20] p-4">
        {error && <p className="font-mono text-xs text-[#f87171]">{error}</p>}

        {!error && trace.length === 0 && (
          <p className="font-mono text-xs text-[#64748b]">
            {running
              ? 'Running analysis…'
              : 'No reasoning trace yet. Run the agent to see every check it performs.'}
          </p>
        )}

        {trace.length > 0 && !raw && (
          <div className="space-y-2">
            {parsed.marketMood && (
              <p className="flex items-center gap-1.5 rounded border border-[#1e293b] bg-[#0a0f1a] px-3 py-2 text-[11px] text-[#94a3b8]">
                <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-[#64748b]" />
                {/* Market-wide, so the backend repeats it per symbol. Shown once. */}
                {parsed.marketMood}
              </p>
            )}

            {parsed.preamble.map((line, i) => (
              <p key={i} className="font-mono text-[11px] text-[#94a3b8]">
                {line}
              </p>
            ))}

            {parsed.groups.map((g, i) => (
              <SymbolBlock key={`${g.symbol ?? 'grp'}-${i}`} group={g} index={i} />
            ))}
          </div>
        )}

        {trace.length > 0 && raw && (
          <div className="space-y-1 font-mono text-xs leading-relaxed">
            {trace.map((line, idx) => (
              <div key={idx} className="flex gap-2">
                <span className="shrink-0 select-none tabular-nums text-[#334155]">
                  {String(idx + 1).padStart(2, '0')}
                </span>
                <span className="break-words text-[#94a3b8]">{line}</span>
              </div>
            ))}
          </div>
        )}

        {trace.length > 0 && (
          <p className="mt-3 border-t border-[#1e293b] pt-2 text-[10px] text-[#64748b]">
            {parsed.groups.length} symbol{parsed.groups.length === 1 ? '' : 's'}
            {blockedCount > 0 && <> · {blockedCount} blocked</>} · {trace.length} trace line
            {trace.length === 1 ? '' : 's'} · run{' '}
            <span className="font-mono">{run?.run_id?.slice(0, 12)}</span>
          </p>
        )}
      </div>
    </div>
  )
}
