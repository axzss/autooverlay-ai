/**
 * Parses the agent's flat reasoning_trace into the per-symbol structure that is
 * already implicit in it.
 *
 * The backend emits one array of strings — 41 lines for an eight-symbol run.
 * Rendered flat that reads as a wall of text, but the shape is regular: each
 * symbol contributes a consensus line, the global market mood, a tier line,
 * zero or more gate checks, an optional citation, and a verdict.
 *
 * This module only reorganises and classifies. It never rewrites a value, and
 * anything it cannot classify is preserved verbatim in `other` so no line is
 * ever silently dropped — an unparsed line is a display problem, not a licence
 * to hide agent output.
 */

export type GateStatus = 'pass' | 'blocked' | 'unknown'

export interface ReasoningGate {
  /** Short label for the check, e.g. "concentration". */
  label: string
  /** The numeric detail, e.g. "MSFT overlays $25,684 = 25.7% of $100,000 portfolio (limit 25%)". */
  detail: string
  status: GateStatus
}

export type VerdictKind = 'blocked' | 'hold' | 'permitted' | 'unknown'

export interface ReasoningGroup {
  /** Ticker, when the trace revealed one. */
  symbol: string | null
  consensusScore: number | null
  recommendation: string | null
  /** Risk tier name: low / mid / high. */
  tier: string | null
  /** 30d annualised volatility percentage. */
  volPct: number | null
  /** Tier policy tail, e.g. "delta 0.05-0.15, DTE≤30, strategies=COVERED_CALL, size x0.5". */
  policy: string | null
  gates: ReasoningGate[]
  /** Symbol-specific override note (e.g. the TSLA council §8 rule). */
  override: string | null
  /** Council rule quoted verbatim by the agent. */
  citation: string | null
  verdict: { kind: VerdictKind; text: string } | null
  /** Lines this parser could not classify. Always rendered somewhere. */
  other: string[]
  /** Every original line for this group, in order, for raw view. */
  raw: string[]
}

export interface ParsedReasoning {
  /** Market mood line, hoisted out because it repeats identically per symbol. */
  marketMood: string | null
  groups: ReasoningGroup[]
  /** Lines that appeared before any group started. */
  preamble: string[]
  /** Total lines in, for reconciliation against what is displayed. */
  totalLines: number
}

const RE_CONSENSUS = /^council consensus\s+([\d.]+)\s*→\s*(.+)$/i
const RE_MOOD = /^Mr\. Market mood:/i
const RE_TIER = /^([A-Z][A-Z0-9.]{0,9}):\s*([\d.]+)%\s*vol\s*→\s*'?([a-z]+)'?\s*tier\s*\((.+)\)$/
const RE_GATE = /^(.*?check)\s*(?:\(([^)]*)\))?\s*:\s*(.+)$/i
const RE_CITATION = /^council rule cited:\s*(.+)$/i
const RE_OVERRIDE = /^([A-Z][A-Z0-9.]{0,9})\s+OVERRIDE ACTIVE\s*\((.+)\)$/
const RE_BLOCKED = /^entry BLOCKED by portfolio gates/i
const RE_HOLD = /^new entry NOT permitted/i
const RE_PERMITTED = /^(new )?entry (permitted|allowed)/i

function emptyGroup(): ReasoningGroup {
  return {
    symbol: null,
    consensusScore: null,
    recommendation: null,
    tier: null,
    volPct: null,
    policy: null,
    gates: [],
    override: null,
    citation: null,
    verdict: null,
    other: [],
    raw: [],
  }
}

function gateStatus(detail: string): GateStatus {
  if (/✗|BLOCKED/i.test(detail)) return 'blocked'
  if (/✓/.test(detail)) return 'pass'
  return 'unknown'
}

/** Strips the trailing "; cited: <copy of earlier lines>" tail. */
function trimCitedTail(line: string): string {
  const idx = line.search(/;\s*cited:/i)
  return idx === -1 ? line : line.slice(0, idx)
}

export function parseReasoning(trace: readonly string[]): ParsedReasoning {
  const groups: ReasoningGroup[] = []
  const preamble: string[] = []
  let marketMood: string | null = null
  let current: ReasoningGroup | null = null

  const push = () => {
    if (current) groups.push(current)
  }

  for (const rawLine of trace) {
    const line = rawLine.trim()
    if (!line) continue

    // A consensus line always opens a new symbol block.
    const consensus = RE_CONSENSUS.exec(line)
    if (consensus) {
      push()
      current = emptyGroup()
      current.consensusScore = Number(consensus[1])
      current.recommendation = consensus[2].trim()
      current.raw.push(rawLine)
      continue
    }

    if (RE_MOOD.test(line)) {
      // Identical for every symbol — it is a market-wide fact. Keep one copy.
      marketMood ??= line
      // But keep the LINE somewhere regardless. `current?.raw.push()` alone
      // silently dropped any mood line that arrived before the first consensus
      // line (current === null, so the optional call no-ops), and every mood
      // variant after the first: neither `preamble` nor any group held it. That
      // broke this module's own contract that no line is ever silently dropped —
      // and a dropped line is dropped agent output, which is the one thing a
      // reasoning viewer must never do.
      if (current) current.raw.push(rawLine)
      else preamble.push(rawLine)
      continue
    }

    if (!current) {
      preamble.push(rawLine)
      continue
    }
    current.raw.push(rawLine)

    const tier = RE_TIER.exec(line)
    if (tier) {
      current.symbol = tier[1]
      current.volPct = Number(tier[2])
      current.tier = tier[3]
      current.policy = tier[4]
      continue
    }

    const override = RE_OVERRIDE.exec(line)
    if (override) {
      current.symbol ??= override[1]
      current.override = override[2]
      continue
    }

    const citation = RE_CITATION.exec(line)
    if (citation) {
      current.citation = citation[1].trim()
      continue
    }

    if (RE_BLOCKED.test(line)) {
      // The "cited:" tail restates gate lines already parsed above — dropping it
      // removes ~400 characters of duplication per blocked symbol.
      current.verdict = { kind: 'blocked', text: trimCitedTail(line) }
      continue
    }
    if (RE_HOLD.test(line)) {
      current.verdict = { kind: 'hold', text: line }
      continue
    }
    if (RE_PERMITTED.test(line)) {
      current.verdict = { kind: 'permitted', text: line }
      continue
    }

    const gate = RE_GATE.exec(line)
    if (gate) {
      const label = gate[1].replace(/\s*check$/i, '').replace(/^council\s+/i, '').trim()
      current.gates.push({
        label: label || 'check',
        detail: gate[3].trim(),
        status: gateStatus(gate[3]),
      })
      continue
    }

    current.other.push(rawLine)
  }

  push()
  return { marketMood, groups, preamble, totalLines: trace.length }
}

/** True when every gate passed and the verdict did not block. */
export function groupIsBlocked(g: ReasoningGroup): boolean {
  return g.verdict?.kind === 'blocked' || g.gates.some((x) => x.status === 'blocked')
}
