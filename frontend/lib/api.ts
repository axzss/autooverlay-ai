// Typed API client for the AutoOverlay backend.
// Base URL: http://localhost:8000 — override with NEXT_PUBLIC_API_BASE_URL.

import { useCallback, useEffect, useState } from 'react'
import type {
  AccountInfo,
  Order,
  Position,
} from '../app/types/portfolio'
import mockPortfolio from '../app/data/mock_portfolio.json'

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    })
    if (!res.ok) {
      throw new ApiError(`API ${path} responded ${res.status}`)
    }
    return (await res.json()) as T
  } catch (err) {
    if (err instanceof ApiError) throw err
    throw new ApiError(`API ${path} unreachable`, err)
  } finally {
    clearTimeout(timeout)
  }
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

export const api = {
  getPortfolio: () => request<PortfolioSnapshot>('/portfolio'),
  getHealth: () => request<HealthResponse>('/health'),
  screenStrategies: () =>
    request<
      | StrategyOpportunity[]
      | { opportunities: StrategyOpportunity[] }
      | { candidates: AgentRecommendation[] }
      | { ranked_recommendations: AgentRecommendation[]; portfolio_context?: PortfolioContext; mode?: string }
    >('/strategy/screen'),
  runDailyCycle: (body?: { candidates?: string[]; cash_override?: number }) =>
    request<CycleResponse>('/council/cycle', {
      method: 'POST',
      body: JSON.stringify(body ?? {}),
    }),
  placeTrade: (body: TradeRequest) =>
    request<TradeResponse>('/trade', {
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
    | { ranked_recommendations?: AgentRecommendation[]; portfolio_context?: PortfolioContext; mode?: string },
): { entries: AgentRecommendation[]; portfolioContext: PortfolioContext | null; mode: string | null } {
  if (Array.isArray(data)) {
    return { entries: data as AgentRecommendation[], portfolioContext: null, mode: null }
  }
  const wrapped = data as Record<string, unknown>
  let entries: AgentRecommendation[] = []
  if (Array.isArray(wrapped.opportunities)) entries = wrapped.opportunities as AgentRecommendation[]
  else if (Array.isArray(wrapped.candidates)) entries = wrapped.candidates as AgentRecommendation[]
  else if (Array.isArray(wrapped.ranked_recommendations))
    entries = wrapped.ranked_recommendations as AgentRecommendation[]
  const ctx = (wrapped as { portfolio_context?: PortfolioContext }).portfolio_context ?? null
  return { entries, portfolioContext: ctx, mode: (wrapped.mode as string) ?? null }
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
