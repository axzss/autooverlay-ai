// Typed API client for the AutoOverlay backend.
// Requests are same-origin by default and reach the backend through the
// next.config.js rewrite (/api/* -> :8000/api/*). Override with
// NEXT_PUBLIC_API_BASE_URL only when the backend is on a different host.

import { useCallback, useEffect, useState } from 'react'
import type {
  AccountInfo,
  Order,
  Position,
} from '../app/types/portfolio'
import mockPortfolio from '../app/data/mock_portfolio.json'

/**
 * Empty string = same origin.
 *
 * This MUST NOT default to a hardcoded host. fetch() runs in the user's
 * browser, so 'http://localhost:8000' resolves to the *visitor's* machine —
 * every request fails with "unreachable" for anyone who is not sitting at the
 * dev box. It only appeared to work locally, and broke the moment the app was
 * opened over a tunnel or from a phone.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? ''

export interface StrategyOpportunity {
  symbol: string
  underlying_price: number
  option_symbol?: string
  strike_price?: number
  expiration_date?: string
  annualized_return_rate?: number
  probability_itm?: number
  recommendation?: string
  reasoning?: string
  [key: string]: unknown
}

export interface TradeRequest {
  symbol: string
  qty: number | string
  side: 'buy' | 'sell'
  type?: 'market' | 'limit'
  limit_price?: number | string | null
  time_in_force?: string
}

export interface TradeResponse {
  id?: string
  status?: string
  symbol?: string
  qty?: string | number
  filled_avg_price?: string | null
  mode?: string
  submitted?: boolean
  reason?: string
  order?: {
    id?: string
    symbol?: string
    qty?: string | number
    side?: string
    status?: string
    [key: string]: unknown
  }
  [key: string]: unknown
}

export interface HealthResponse {
  status?: string
  alpaca_configured?: boolean
  [key: string]: unknown
}

export interface PortfolioContext {
  concentration_ok?: boolean
  max_concentration_pct?: number | null
  cash_reserve_ok?: boolean
  cash_reserve_pct?: number | null
  largest_position_pct?: number | null
  [key: string]: unknown
}

export interface AgentRecommendation {
  symbol: string
  strategy?: string
  /** INITIATE_POSITION | HOLD_POSITION | MONITOR_CLOSELY | TAKE_PROFIT | STOP_LOSS | ROLL */
  action?: string
  recommendation?: string
  risk_score?: number
  annualized_premium_yield?: number
  annualized_return_rate?: number
  option_symbol?: string | null
  strike_price?: number | null
  expiration_date?: string | null
  contracts?: number
  qty?: number
  rationale?: string
  reasoning?: string
  reasoning_trace?: string[]
  [key: string]: unknown
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly cause?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

const RETRYABLE_METHODS = new Set(['GET', 'HEAD'])
const RETRYABLE_STATUS = new Set([408, 429, 502, 503, 504])

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const slow = /\/(agent\/run|council\/(cycle|assess)|strategy\/screen)/.test(path)
  const baseTimeout = slow ? 45000 : 15000
  const timeout = setTimeout(() => controller.abort(), baseTimeout)

  const isRetryable =
    RETRYABLE_METHODS.has((init?.method ?? 'GET').toUpperCase()) &&
    init?.body == null

  let attempt = 0
  let lastError: unknown
  while (attempt < (isRetryable ? 2 : 1)) {
    attempt++
    const tryController = attempt > 1 ? new AbortController() : controller
    const tryTimeout = setTimeout(
      () => tryController.abort(),
      slow ? 45000 : 15000,
    )
    try {
      const res = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        signal: tryController.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(init?.headers ?? {}),
        },
      })
      clearTimeout(tryTimeout)
      if (!res.ok) {
        // Read the body defensively. `res.text()` may be absent or may itself
        // throw (a stubbed/partial Response, a stream already consumed, a body
        // that never arrives). If that happens the thrown TypeError escapes to
        // the catch below, is not an ApiError, and gets wrapped as
        // "unreachable" — reporting a backend that ANSWERED as a dead one.
        // The status is the diagnostically important part; the body is a bonus.
        let detail = ''
        try {
          const body = typeof res.text === 'function' ? await res.text() : ''
          if (body) detail = `: ${body.slice(0, 200)}`
        } catch {
          /* body unreadable — keep the status, drop the detail */
        }
        const error = new ApiError(`API ${path} responded ${res.status}${detail}`)
        if (!isRetryable || attempt === (isRetryable ? 2 : 1) || !RETRYABLE_STATUS.has(res.status)) {
          throw error
        }
        lastError = error
        continue
      }
      return (await res.json()) as T
    } catch (err) {
      clearTimeout(tryTimeout)
      if (err instanceof ApiError) throw err
      if (
        isRetryable &&
        attempt < (isRetryable ? 2 : 1) &&
        err instanceof DOMException &&
        err.name === 'AbortError'
      ) {
        lastError = err
        continue
      }
      // A typed error from an earlier attempt outranks a generic wrap from this
      // one: "responded 503" tells the operator the backend is up and failing,
      // "unreachable" sends them to look at the wrong thing.
      if (lastError instanceof ApiError) throw lastError
      const wrapped = err instanceof DOMException && err.name === 'AbortError'
        ? new ApiError(`API ${path} timed out`, err)
        : new ApiError(`API ${path} unreachable`, err)
      throw wrapped
    } finally {
      // The OUTER controller's timer must be cleared on every exit path, not
      // only on the final attempt. A retryable GET that succeeds on attempt 1
      // left this timer armed (the old condition `attempt === 2` was false), so
      // an abort fired up to 15s later against a controller nothing was
      // listening to — a leaked handle per successful request. Harmless in a
      // one-shot page, not harmless once F1 polls every 20s.
      clearTimeout(timeout)
    }
  }

  const finalError =
    lastError instanceof Error ? lastError : new ApiError(`API ${path} unreachable`)
  throw finalError
}

export interface DailyDirective {
  action: string
  symbol: string
  priority: number
  reasoning_trace: string[]
  provenance: Array<{ source: string; detail?: string }>
  params?: Record<string, unknown>
  [key: string]: unknown
}

export interface CycleResponse {
  halted?: boolean
  kill_switch?: { halted: boolean; reasons: string[] }
  mr_market?: Record<string, unknown>
  directives: DailyDirective[]
  steps_run?: string[]
  assessments?: Array<Record<string, unknown>>
  [key: string]: unknown
}

/**
 * One prepared-but-unsubmitted order from POST /api/agent/run.
 * Field names mirror backend/app/routes/agent.py::_order_intents exactly.
 */
export interface OrderIntent {
  action: string
  strategy: string
  symbol: string
  option_symbol: string | null
  contracts: number
  qty: number
  side: string
  type: string
  time_in_force: string
  limit_price: number | null
  requires_approval: boolean
  submitted: boolean
  [key: string]: unknown
}

export interface AgentRiskSummary {
  halted?: boolean
  kill_switch?: { halted?: boolean; reasons?: string[] }
  portfolio_state?: Record<string, unknown>
  blocked_entries?: number
  [key: string]: unknown
}

/**
 * POST /api/agent/run. Note: `recommendations` are council *directives*
 * (action/symbol/params/priority/reasoning_trace/provenance), not the
 * screening-shaped AgentRecommendation used by /strategy/screen.
 */
export interface AgentRunResponse {
  run_id: string
  status: string
  mode: string
  orders_ready: boolean
  order_intents: OrderIntent[]
  recommendations: DailyDirective[]
  risk_summary: AgentRiskSummary
  reasoning_trace: string[]
  cycle?: CycleResponse
  completed_at?: string
  [key: string]: unknown
}

export interface CouncilVerdict {
  persona: string
  score: number
  stance: string
  bullets: string[]
}

export interface CouncilDissent {
  persona: string
  direction?: string
  score?: number
  consensus?: number
  /** Backend emits a list of rationale lines, not a single string. */
  why?: string[]
  [key: string]: unknown
}

export interface CouncilTierPolicy {
  delta_min: number
  delta_max: number
  max_dte: number
  allowed_strategies: string[]
  size_multiplier: number
}

export interface CouncilAssessment {
  symbol: string
  tier: string
  tier_policy_summary: string
  tier_policy: CouncilTierPolicy
  consensus_score: number
  recommendation: string
  majority_stance: string
  is_split: boolean
  verdicts: CouncilVerdict[]
  dissent: CouncilDissent[]
}

export interface CouncilAssessResponse {
  mode: string
  count: number
  assessments: CouncilAssessment[]
}

export const api = {
  getPortfolio: () => request<PortfolioSnapshot>('/api/portfolio'),
  // Backend serves health bare at /health, but the browser must go through the
  // Next rewrite, which only proxies paths under /api. next.config.js maps
  // /api/health -> :8000/health precisely for this. Requesting bare '/health'
  // asks the Next origin for a page that does not exist -> 404.
  getHealth: () => request<HealthResponse>('/api/health'),
  screenStrategies: () =>
    request<
      | StrategyOpportunity[]
      | { opportunities: StrategyOpportunity[] }
      | { candidates: AgentRecommendation[] }
      | {
          ranked_recommendations: AgentRecommendation[]
          portfolio_context?: PortfolioContext
          mode?: string
          live_error?: string
        }
    >('/api/strategy/screen'),
  runDailyCycle: (body?: { candidates?: string[]; cash_override?: number }) =>
    request<CycleResponse>('/api/council/cycle', {
      method: 'POST',
      body: JSON.stringify(body ?? {}),
    }),
  runAgent: (body?: { candidates?: string[]; cash_override?: number }) =>
    request<AgentRunResponse>('/api/agent/run', {
      method: 'POST',
      body: JSON.stringify(body ?? {}),
    }),
  assessCouncil: (symbols?: string[]) =>
    symbols && symbols.length > 0
      ? request<CouncilAssessResponse>('/api/council/assess', {
          method: 'POST',
          body: JSON.stringify({ symbols }),
        })
      : request<CouncilAssessResponse>('/api/council/assess'),
  placeTrade: (body: TradeRequest) =>
    request<TradeResponse>('/api/trade', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}

export interface PortfolioSnapshot {
  account_info: AccountInfo
  positions: Position[]
  orders: Order[]
  covered_call_opportunities?: StrategyOpportunity[]
}

/** Normalizes /strategy/screen responses that are either a bare array or wrapped. */
export function normalizeScreenings(
  data:
    | StrategyOpportunity[]
    | { opportunities: StrategyOpportunity[] }
    | { candidates?: AgentRecommendation[] }
    | {
        ranked_recommendations?: AgentRecommendation[]
        portfolio_context?: PortfolioContext
        mode?: string
        live_error?: string
      },
): {
  entries: AgentRecommendation[]
  portfolioContext: PortfolioContext | null
  mode: string | null
  liveError: string | null
} {
  if (Array.isArray(data)) {
    return { entries: data as AgentRecommendation[], portfolioContext: null, mode: null, liveError: null }
  }
  const wrapped = data as Record<string, unknown>
  let entries: AgentRecommendation[] = []
  if (Array.isArray(wrapped.opportunities)) entries = wrapped.opportunities as AgentRecommendation[]
  else if (Array.isArray(wrapped.candidates)) entries = wrapped.candidates as AgentRecommendation[]
  else if (Array.isArray(wrapped.ranked_recommendations))
    entries = wrapped.ranked_recommendations as AgentRecommendation[]
  const ctx = (wrapped as { portfolio_context?: PortfolioContext }).portfolio_context ?? null
  const liveError = typeof wrapped.live_error === 'string' ? wrapped.live_error : null
  return { entries, portfolioContext: ctx, mode: (wrapped.mode as string) ?? null, liveError }
}

/** Maps a risk score to its Tailwind badge classes: green <=40, amber <=70, red >70. */
export function riskBadgeClasses(score: number): string {
  if (score <= 40) return 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
  if (score <= 70) return 'border-[#f59e0b]/50 bg-[#451a03] text-[#fbbf24]'
  return 'border-[#ef4444]/50 bg-[#450a0a] text-[#f87171]'
}

const ACTION_LABELS: Record<string, string> = {
  INITIATE_POSITION: 'Initiate Position',
  HOLD_POSITION: 'Hold Position',
  MONITOR_CLOSELY: 'Monitor Closely',
  TAKE_PROFIT: 'Take Profit',
  STOP_LOSS: 'Stop Loss',
  ROLL: 'Roll Position',
  SELL_TO_OPEN: 'Sell to Open',
}

export function actionLabel(action?: string): string {
  if (!action) return 'Screened Candidate'
  return ACTION_LABELS[action.toUpperCase()] ?? action.replaceAll('_', ' ')
}

/** Deterministic client-side fallback when the backend omits a risk score. */
function deriveRiskScore(entry: AgentRecommendation): number {
  const action = (entry.action ?? entry.recommendation ?? '').toUpperCase()
  if (action === 'INITIATE_POSITION' || action === 'SELL_TO_OPEN') return 35
  if (action === 'MONITOR_CLOSELY') return 60
  if (action === 'TAKE_PROFIT' || action === 'ROLL') return 30
  if (action === 'STOP_LOSS') return 85
  return 50
}

export interface FeedEntry {
  key: string
  symbol: string
  strategyType: string
  action: string
  rawAction: string
  riskScore: number
  riskDerived: boolean
  premiumYieldPct: number | null
  optionSymbol: string | null
  strike: number | null
  expiration: string | null
  contracts: number
  reasoningSteps: string[]
}

/** Shapes a raw screening record into what the agent activity feed renders. */
export function toFeedEntry(raw: AgentRecommendation, index: number): FeedEntry {
  const action = String(raw.action ?? raw.recommendation ?? 'CANDIDATE').toUpperCase()
  const yieldRaw = raw.annualized_premium_yield ?? raw.annualized_return_rate
  // Backend yields are fractional (0.12); tolerate already-percent values too.
  const premiumYieldPct =
    typeof yieldRaw === 'number' && Number.isFinite(yieldRaw)
      ? Math.abs(yieldRaw) <= 1.5
        ? yieldRaw * 100
        : yieldRaw
      : null
  const steps =
    Array.isArray(raw.reasoning_trace) && raw.reasoning_trace.length > 0
      ? raw.reasoning_trace.map(String)
      : [raw.rationale ?? raw.reasoning ?? 'No reasoning trace returned for this candidate.'].filter(
          Boolean,
        )
  const score = typeof raw.risk_score === 'number' ? raw.risk_score : deriveRiskScore(raw)
  return {
    key: `${raw.symbol}-${raw.option_symbol ?? index}-${index}`,
    symbol: raw.symbol,
    strategyType: raw.strategy ?? 'covered_call',
    action: actionLabel(action),
    rawAction: action,
    riskScore: score,
    riskDerived: typeof raw.risk_score !== 'number',
    premiumYieldPct,
    optionSymbol: raw.option_symbol ?? null,
    strike: typeof raw.strike_price === 'number' ? raw.strike_price : null,
    expiration: raw.expiration_date ?? null,
    contracts: Number(raw.qty ?? raw.contracts ?? 1),
    reasoningSteps: steps,
  }
}

const FALLBACK = mockPortfolio as unknown as PortfolioSnapshot

interface ApiState<T> {
  data: T | null
  error: string | null
  loading: boolean
  /** True when we're showing mock data because the backend is unreachable. */
  usingFallback: boolean
}

/**
 * Fetches live portfolio data with graceful degradation:
 * while unreachable, falls back to bundled mock data.
 */
export function usePortfolio(): ApiState<PortfolioSnapshot> & {
  refresh: () => void
} {
  const [state, setState] = useState<ApiState<PortfolioSnapshot>>({
    data: null,
    error: null,
    loading: true,
    usingFallback: false,
  })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    setState((s) => ({ ...s, loading: true }))
    api
      .getPortfolio()
      .then((data) => {
        if (!cancelled) setState({ data, error: null, loading: false, usingFallback: false })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            data: FALLBACK,
            error: err instanceof Error ? err.message : 'Backend unavailable',
            loading: false,
            usingFallback: true,
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [tick])

  const refresh = useCallback(() => setTick((t) => t + 1), [])
  return { ...state, refresh }
}
