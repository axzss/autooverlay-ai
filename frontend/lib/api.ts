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

export const api = {
  getPortfolio: () => request<PortfolioSnapshot>('/portfolio'),
  screenStrategies: () =>
    request<{ opportunities: StrategyOpportunity[] } | StrategyOpportunity[]>(
      '/strategy/screen',
    ),
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
  data: StrategyOpportunity[] | { opportunities: StrategyOpportunity[] },
): StrategyOpportunity[] {
  return Array.isArray(data) ? data : data.opportunities
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
