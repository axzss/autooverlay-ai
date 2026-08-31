'use client'

/**
 * Renders the pre-trade risk gate's verdict.
 *
 * Why this component exists: `POST /api/trade` answers **409** with
 * `{message, risk}` when the gate refuses an order, and the backend chose 409
 * over 422 deliberately so the UI can tell "you sent nonsense" from "this trade
 * is unsafe right now" (`backend/app/routes/trade.py:186-195`). Before this
 * component the frontend stringified that body and sliced it to 200 characters,
 * so the single most important sentence in the whole app — *why the gate refused
 * your trade* — reached the operator as a truncated JSON blob.
 *
 * Every check carries the numbers it was decided on, because
 * `backend/app/risk/models.py` says so in its own header: "a rejection a human
 * cannot diagnose in seconds is a rejection that will be overridden blind".
 * Rendering only the boolean would throw that away.
 */

import { ShieldAlert, ShieldCheck, TriangleAlert } from 'lucide-react'
import type { RiskCheck, RiskDecision } from '../../../lib/api'

const SEVERITY_STYLE: Record<RiskCheck['severity'], string> = {
  BLOCK: 'border-[#ef4444]/50 bg-[#450a0a] text-[#f87171]',
  WARN: 'border-[#f59e0b]/50 bg-[#451a03] text-[#fbbf24]',
  INFO: 'border-[#334155] bg-[#0f172a] text-[#94a3b8]',
}

/** Severity is stated in text as well as colour — colour alone fails a projector. */
function SeverityBadge({ severity }: { severity: RiskCheck['severity'] }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${SEVERITY_STYLE[severity]}`}
    >
      {severity}
    </span>
  )
}

/** Formats one check's `values` map without inventing precision it does not have. */
function formatValues(values: Record<string, unknown> | undefined): string | null {
  if (!values) return null
  const parts = Object.entries(values)
    .filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object')
    .map(([k, v]) => `${k}=${typeof v === 'number' ? Number(v.toFixed(4)) : String(v)}`)
  return parts.length > 0 ? parts.join('  ') : null
}

function CheckRow({ check }: { check: RiskCheck }) {
  const values = formatValues(check.values)
  return (
    <li className="flex items-start gap-2 border-t border-[#1e293b] py-1.5 first:border-t-0">
      <SeverityBadge severity={check.severity} />
      <div className="min-w-0 flex-1">
        <p className="text-[11px] text-[#f8fafc]">
          <span className="font-mono text-[#94a3b8]">{check.name}</span>
          {check.passed ? ' — passed' : ''}
        </p>
        <p className="text-[11px] leading-snug text-[#94a3b8]">{check.detail}</p>
        {values && <p className="mt-0.5 font-mono text-[10px] text-[#64748b]">{values}</p>}
      </div>
    </li>
  )
}

export default function RiskDecisionPanel({
  decision,
  /** When true, only the failing checks are listed. Passing checks stay counted. */
  failuresOnly = true,
}: {
  decision: RiskDecision
  failuresOnly?: boolean
}) {
  const checks = Array.isArray(decision.checks) ? decision.checks : []
  const failing = checks.filter((c) => !c.passed)
  const shown = failuresOnly ? failing : checks
  const blocked = decision.allowed === false

  return (
    <div
      className={`space-y-2 rounded border p-3 ${
        blocked ? 'border-[#ef4444]/40 bg-[#1a0a0a]' : 'border-[#1e293b] bg-[#0a0f1a]'
      }`}
    >
      <div className="flex items-center gap-2">
        {blocked ? (
          <ShieldAlert className="h-4 w-4 shrink-0 text-[#f87171]" />
        ) : failing.length > 0 ? (
          <TriangleAlert className="h-4 w-4 shrink-0 text-[#fbbf24]" />
        ) : (
          <ShieldCheck className="h-4 w-4 shrink-0 text-[#22c55e]" />
        )}
        <p className="text-[11px] font-semibold uppercase tracking-wider text-[#f8fafc]">
          {blocked ? 'Blocked by pre-trade risk gate' : 'Pre-trade risk gate: allowed'}
        </p>
        {decision.override_applied && (
          <span className="ml-auto inline-flex items-center rounded border border-[#f59e0b]/50 bg-[#451a03] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#fbbf24]">
            override applied
          </span>
        )}
      </div>

      {/* The gate's own summary lines come first: they are the reasons, already
          written for a human by the layer that made the decision. */}
      {decision.hard_failures?.length > 0 && (
        <ul className="space-y-1">
          {decision.hard_failures.map((reason, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[11px] leading-snug text-[#f87171]">
              <span aria-hidden className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[#f87171]" />
              {reason}
            </li>
          ))}
        </ul>
      )}

      {decision.warnings?.length > 0 && (
        <ul className="space-y-1">
          {decision.warnings.map((reason, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[11px] leading-snug text-[#fbbf24]">
              <span aria-hidden className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[#fbbf24]" />
              {reason}
            </li>
          ))}
        </ul>
      )}

      {shown.length > 0 && (
        <ul>
          {shown.map((check, i) => (
            <CheckRow key={`${check.name}-${i}`} check={check} />
          ))}
        </ul>
      )}

      {/* Provenance of the decision itself. `mode` matters: a verdict computed
          from a mock snapshot is not evidence about the live account. */}
      <p className="font-mono text-[10px] text-[#64748b]">
        {checks.length} check{checks.length === 1 ? '' : 's'} evaluated
        {failing.length > 0 ? `, ${failing.length} failing` : ''}
        {decision.mode ? ` · snapshot ${decision.mode}` : ''}
        {decision.snapshot_hash ? ` · ${decision.snapshot_hash.slice(0, 10)}` : ''}
      </p>
    </div>
  )
}
