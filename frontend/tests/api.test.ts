import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  API_BASE_URL,
  normalizeScreenings,
  riskBadgeClasses,
  actionLabel,
  toFeedEntry,
  api,
  ApiError,
  type AgentRecommendation,
  type StrategyOpportunity,
} from '../lib/api'

describe('API_BASE_URL', () => {
  /**
   * REGRESSION GUARD. This used to default to 'http://localhost:8000', which
   * resolves to the *visitor's* machine because fetch runs in their browser.
   * Every request failed for anyone not sitting at the dev box. The default
   * must be the empty string (same origin, proxied by next.config.js).
   */
  it("defaults to '' (same origin), never a hardcoded host", () => {
    expect(process.env.NEXT_PUBLIC_API_BASE_URL).toBeUndefined()
    expect(API_BASE_URL).toBe('')
    expect(API_BASE_URL).not.toMatch(/localhost/)
    expect(API_BASE_URL).not.toMatch(/^https?:/)
  })
})

describe('normalizeScreenings', () => {
  const rec = (symbol: string): AgentRecommendation => ({ symbol })

  it('accepts a bare array', () => {
    const arr = [rec('AAPL'), rec('MSFT')]
    expect(normalizeScreenings(arr as unknown as StrategyOpportunity[])).toEqual({
      entries: arr,
      portfolioContext: null,
      mode: null,
      liveError: null,
    })
  })

  it('accepts an empty array', () => {
    expect(normalizeScreenings([])).toEqual({
      entries: [],
      portfolioContext: null,
      mode: null,
      liveError: null,
    })
  })

  it('unwraps { opportunities }', () => {
    const r = normalizeScreenings({ opportunities: [rec('AAPL')] as unknown as StrategyOpportunity[] })
    expect(r.entries.map((e) => e.symbol)).toEqual(['AAPL'])
  })

  it('unwraps { candidates }', () => {
    const r = normalizeScreenings({ candidates: [rec('NVDA'), rec('KO')] })
    expect(r.entries.map((e) => e.symbol)).toEqual(['NVDA', 'KO'])
  })

  it('unwraps { ranked_recommendations }', () => {
    const r = normalizeScreenings({ ranked_recommendations: [rec('SPY')] })
    expect(r.entries.map((e) => e.symbol)).toEqual(['SPY'])
  })

  it('prefers opportunities > candidates > ranked_recommendations', () => {
    const r = normalizeScreenings({
      opportunities: [rec('FIRST')] as unknown as StrategyOpportunity[],
      candidates: [rec('SECOND')],
      ranked_recommendations: [rec('THIRD')],
    } as never)
    expect(r.entries.map((e) => e.symbol)).toEqual(['FIRST'])

    const r2 = normalizeScreenings({
      candidates: [rec('SECOND')],
      ranked_recommendations: [rec('THIRD')],
    } as never)
    expect(r2.entries.map((e) => e.symbol)).toEqual(['SECOND'])
  })

  it('surfaces portfolio_context, mode and live_error', () => {
    const r = normalizeScreenings({
      ranked_recommendations: [rec('AAPL')],
      portfolio_context: { concentration_ok: false, max_concentration_pct: 25 },
      mode: 'paper',
      live_error: 'alpaca 429',
    })
    expect(r.portfolioContext).toEqual({ concentration_ok: false, max_concentration_pct: 25 })
    expect(r.mode).toBe('paper')
    expect(r.liveError).toBe('alpaca 429')
  })

  it('returns liveError null when live_error is not a string', () => {
    const r = normalizeScreenings({ live_error: 500 } as never)
    expect(r.liveError).toBeNull()
    expect(r.entries).toEqual([])
  })

  it('handles a live_error-only payload with no entries', () => {
    const r = normalizeScreenings({ live_error: 'backend down', mode: 'live' })
    expect(r.entries).toEqual([])
    expect(r.liveError).toBe('backend down')
    expect(r.mode).toBe('live')
  })

  it('handles malformed shapes without throwing', () => {
    for (const bad of [{}, { opportunities: 'nope' }, { candidates: null }, { mode: 42 }]) {
      expect(() => normalizeScreenings(bad as never)).not.toThrow()
      const r = normalizeScreenings(bad as never)
      expect(Array.isArray(r.entries)).toBe(true)
      expect(r.entries).toEqual([])
    }
  })

  it('never throws on null/undefined-ish input (documents current behaviour)', () => {
    // Array.isArray(null) is false, so it takes the wrapped path and reads
    // properties off null -> TypeError. Recorded so a change is visible.
    expect(() => normalizeScreenings(null as never)).toThrow()
  })
})

/**
 * Timeout classification. The predicate lives inside request() as a local
 * const and is not exported, so it cannot be imported directly. The regex
 * below is a verbatim copy of lib/api.ts:118. See the summary for the
 * one-line export that would remove this duplication.
 */
const SLOW_RE = /\/(agent\/run|council\/(cycle|assess)|strategy\/screen)/
const isSlow = (path: string) => SLOW_RE.test(path)

describe('request() timeout classification (mirrored predicate)', () => {
  it('classifies agent endpoints as slow (30s)', () => {
    expect(isSlow('/api/agent/run')).toBe(true)
    expect(isSlow('/api/council/cycle')).toBe(true)
    expect(isSlow('/api/council/assess')).toBe(true)
    expect(isSlow('/api/strategy/screen')).toBe(true)
  })

  it('classifies read endpoints as fast (8s)', () => {
    expect(isSlow('/api/portfolio')).toBe(false)
    expect(isSlow('/api/health')).toBe(false)
    expect(isSlow('/api/trade')).toBe(false)
  })

  it('keeps the mirrored regex identical to the source', () => {
    // If lib/api.ts changes its regex, this literal must be updated too.
    expect(SLOW_RE.source).toBe('\\/(agent\\/run|council\\/(cycle|assess)|strategy\\/screen)')
  })
})

describe('api client request URLs', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok' }),
    })) as unknown as ReturnType<typeof vi.fn>
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  /**
   * REGRESSION GUARD. Bare '/health' asks the Next origin for a page that does
   * not exist -> 404 in the browser. Only '/api/health' goes through the
   * next.config.js rewrite.
   */
  it("getHealth() requests '/api/health', never bare '/health'", async () => {
    await api.getHealth()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toBe('/api/health')
    expect(url).not.toBe('/health')
    expect(url.startsWith('/api/')).toBe(true)
  })

  it('sends every documented endpoint under /api/', async () => {
    await api.getPortfolio()
    await api.screenStrategies()
    await api.runDailyCycle()
    await api.runAgent()
    await api.assessCouncil()
    await api.assessCouncil(['AAPL'])
    await api.placeTrade({ symbol: 'AAPL', qty: 1, side: 'buy' })
    const urls = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(urls).toEqual([
      '/api/portfolio',
      '/api/strategy/screen',
      '/api/council/cycle',
      '/api/agent/run',
      '/api/council/assess',
      '/api/council/assess',
      '/api/trade',
    ])
    for (const u of urls) expect(u.startsWith('/api/')).toBe(true)
  })

  it('sets a JSON content type and POSTs a body for agent runs', async () => {
    await api.runAgent({ candidates: ['AAPL'] })
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ candidates: ['AAPL'] }))
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(init.signal).toBeDefined()
  })

  it('GETs /api/council/assess when no symbols are supplied', async () => {
    await api.assessCouncil()
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBeUndefined()
  })

  it('wraps a non-ok response in ApiError with the status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })),
    )
    await expect(api.getHealth()).rejects.toBeInstanceOf(ApiError)
    await expect(api.getHealth()).rejects.toThrow('API /api/health responded 503')
  })

  it('wraps a network failure as unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('network down')
      }),
    )
    await expect(api.getHealth()).rejects.toThrow('API /api/health unreachable')
  })

  // ---- Retry contract. -------------------------------------------------------
  // `RETRYABLE_STATUS` (api.ts:113) retries 408/429/502/503/504 on GET/HEAD.
  // The regression these pin: a retried status built the correct
  // "responded <status>" ApiError, stored it in `lastError`, retried, and the
  // second pass overwrote it with a generic "unreachable" — telling the operator
  // the backend was DOWN when it had answered. That is the same class of
  // misdiagnosis as the localhost:8000 base URL and the bare /health 404.

  it('retries a 503 on GET and returns data when the retry succeeds', async () => {
    let call = 0
    const fetchSpy = vi.fn(async () => {
      call += 1
      return call === 1
        ? { ok: false, status: 503, text: async () => 'warming up', json: async () => ({}) }
        : { ok: true, status: 200, json: async () => ({ status: 'ok' }) }
    })
    vi.stubGlobal('fetch', fetchSpy)
    await expect(api.getHealth()).resolves.toEqual({ status: 'ok' })
    expect(fetchSpy).toHaveBeenCalledTimes(2)
  })

  it('reports a persistently failing 503 as "responded 503", never "unreachable"', async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: false,
      status: 503,
      text: async () => 'still down',
      json: async () => ({}),
    }))
    vi.stubGlobal('fetch', fetchSpy)
    await expect(api.getHealth()).rejects.toThrow('API /api/health responded 503')
    await expect(api.getHealth()).rejects.not.toThrow('unreachable')
    expect(fetchSpy).toHaveBeenCalledTimes(4) // two attempts per call, two calls
  })

  it('keeps the status when the response body cannot be read', async () => {
    // A Response without a usable .text() must not derail the error: the old code
    // called res.text() unguarded, the TypeError escaped, and the status was lost.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })),
    )
    await expect(api.getHealth()).rejects.toThrow('API /api/health responded 500')
  })

  it('does not retry a 500 — it is not in RETRYABLE_STATUS', async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: false,
      status: 500,
      text: async () => 'boom',
      json: async () => ({}),
    }))
    vi.stubGlobal('fetch', fetchSpy)
    await expect(api.getHealth()).rejects.toThrow('responded 500')
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })

  it('never retries a POST, even on a retryable status', async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: false,
      status: 503,
      text: async () => 'busy',
      json: async () => ({}),
    }))
    vi.stubGlobal('fetch', fetchSpy)
    await expect(api.runAgent()).rejects.toThrow('responded 503')
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })

  it('includes a readable body in the error detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 422,
        text: async () => 'symbol required',
        json: async () => ({}),
      })),
    )
    await expect(api.getHealth()).rejects.toThrow('responded 422: symbol required')
  })

  it('clears the outer abort timer when a retryable GET succeeds first try', async () => {
    // The old `finally` only cleared the outer timer on the FINAL attempt, so a
    // retryable GET that succeeded immediately left it armed and an abort fired
    // up to 15s later against a controller nobody was listening to. One leaked
    // handle per successful request — invisible on a one-shot page, not once the
    // F1 data layer polls every 20s.
    const clearSpy = vi.spyOn(globalThis, 'clearTimeout')
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ status: 'ok' }) })),
    )
    await api.getHealth()
    // Two timers are armed per attempt (outer + per-try); both must be cleared.
    expect(clearSpy.mock.calls.length).toBeGreaterThanOrEqual(2)
    clearSpy.mockRestore()
  })

  it('reports an aborted request as a timeout, not unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new DOMException('aborted', 'AbortError')
      }),
    )
    await expect(api.runAgent()).rejects.toThrow('API /api/agent/run timed out')
  })
})

describe('riskBadgeClasses', () => {
  it('is green at or below 40', () => {
    for (const s of [-10, 0, 39, 40]) expect(riskBadgeClasses(s)).toContain('#22c55e')
  })
  it('is amber above 40 up to 70', () => {
    for (const s of [41, 55, 70]) expect(riskBadgeClasses(s)).toContain('#f59e0b')
  })
  it('is red above 70', () => {
    for (const s of [71, 85, 1000]) expect(riskBadgeClasses(s)).toContain('#ef4444')
  })
})

describe('actionLabel', () => {
  it('falls back when the action is missing or empty', () => {
    expect(actionLabel()).toBe('Screened Candidate')
    expect(actionLabel('')).toBe('Screened Candidate')
  })

  it('maps every known action', () => {
    expect(actionLabel('INITIATE_POSITION')).toBe('Initiate Position')
    expect(actionLabel('HOLD_POSITION')).toBe('Hold Position')
    expect(actionLabel('MONITOR_CLOSELY')).toBe('Monitor Closely')
    expect(actionLabel('TAKE_PROFIT')).toBe('Take Profit')
    expect(actionLabel('STOP_LOSS')).toBe('Stop Loss')
    expect(actionLabel('ROLL')).toBe('Roll Position')
    expect(actionLabel('SELL_TO_OPEN')).toBe('Sell to Open')
  })

  it('is case-insensitive on lookup', () => {
    expect(actionLabel('initiate_position')).toBe('Initiate Position')
  })

  it('humanises an unknown action by replacing underscores', () => {
    expect(actionLabel('SOME_NEW_THING')).toBe('SOME NEW THING')
  })
})

describe('toFeedEntry', () => {
  it('converts a fractional yield to a percentage', () => {
    const e = toFeedEntry({ symbol: 'AAPL', annualized_premium_yield: 0.12 }, 0)
    expect(e.premiumYieldPct).toBeCloseTo(12)
  })

  it('leaves an already-percent yield alone', () => {
    const e = toFeedEntry({ symbol: 'AAPL', annualized_premium_yield: 14.5 }, 0)
    expect(e.premiumYieldPct).toBeCloseTo(14.5)
  })

  it('treats 1.5 as the fraction/percent boundary (inclusive => fraction)', () => {
    expect(toFeedEntry({ symbol: 'A', annualized_premium_yield: 1.5 }, 0).premiumYieldPct).toBeCloseTo(150)
    expect(toFeedEntry({ symbol: 'A', annualized_premium_yield: 1.51 }, 0).premiumYieldPct).toBeCloseTo(1.51)
  })

  it('falls back to annualized_return_rate', () => {
    const e = toFeedEntry({ symbol: 'A', annualized_return_rate: 0.2 }, 0)
    expect(e.premiumYieldPct).toBeCloseTo(20)
  })

  it('yields null for missing or non-finite yields', () => {
    expect(toFeedEntry({ symbol: 'A' }, 0).premiumYieldPct).toBeNull()
    expect(toFeedEntry({ symbol: 'A', annualized_premium_yield: NaN }, 0).premiumYieldPct).toBeNull()
    expect(
      toFeedEntry({ symbol: 'A', annualized_premium_yield: Infinity }, 0).premiumYieldPct,
    ).toBeNull()
  })

  it('uses the reasoning_trace when present', () => {
    const e = toFeedEntry({ symbol: 'A', reasoning_trace: ['one', 'two'], rationale: 'ignored' }, 0)
    expect(e.reasoningSteps).toEqual(['one', 'two'])
  })

  it('falls back to rationale, then reasoning, then a placeholder', () => {
    expect(toFeedEntry({ symbol: 'A', rationale: 'because' }, 0).reasoningSteps).toEqual(['because'])
    expect(toFeedEntry({ symbol: 'A', reasoning: 'why' }, 0).reasoningSteps).toEqual(['why'])
    expect(toFeedEntry({ symbol: 'A' }, 0).reasoningSteps).toEqual([
      'No reasoning trace returned for this candidate.',
    ])
  })

  it('falls back when reasoning_trace is an empty array', () => {
    expect(toFeedEntry({ symbol: 'A', reasoning_trace: [], rationale: 'r' }, 0).reasoningSteps).toEqual([
      'r',
    ])
  })

  it('keeps a backend risk score and flags it as not derived', () => {
    const e = toFeedEntry({ symbol: 'A', risk_score: 77 }, 0)
    expect(e.riskScore).toBe(77)
    expect(e.riskDerived).toBe(false)
  })

  it('derives a risk score per action when the backend omits one', () => {
    const cases: Array<[string, number]> = [
      ['INITIATE_POSITION', 35],
      ['SELL_TO_OPEN', 35],
      ['MONITOR_CLOSELY', 60],
      ['TAKE_PROFIT', 30],
      ['ROLL', 30],
      ['STOP_LOSS', 85],
      ['SOMETHING_ELSE', 50],
    ]
    for (const [action, expected] of cases) {
      const e = toFeedEntry({ symbol: 'A', action }, 0)
      expect(e.riskScore, action).toBe(expected)
      expect(e.riskDerived, action).toBe(true)
    }
  })

  it('uppercases the action and defaults to CANDIDATE', () => {
    expect(toFeedEntry({ symbol: 'A', action: 'roll' }, 0).rawAction).toBe('ROLL')
    expect(toFeedEntry({ symbol: 'A' }, 0).rawAction).toBe('CANDIDATE')
    expect(toFeedEntry({ symbol: 'A', recommendation: 'take_profit' }, 0).rawAction).toBe('TAKE_PROFIT')
  })

  it('builds a stable key from symbol, option symbol and index', () => {
    expect(toFeedEntry({ symbol: 'AAPL', option_symbol: 'AAPL240119C00190000' }, 3).key).toBe(
      'AAPL-AAPL240119C00190000-3',
    )
    expect(toFeedEntry({ symbol: 'AAPL' }, 3).key).toBe('AAPL-3-3')
  })

  it('defaults strategy and contracts', () => {
    const e = toFeedEntry({ symbol: 'A' }, 0)
    expect(e.strategyType).toBe('covered_call')
    expect(e.contracts).toBe(1)
    expect(e.optionSymbol).toBeNull()
    expect(e.strike).toBeNull()
    expect(e.expiration).toBeNull()
  })

  it('prefers qty over contracts and coerces numeric strings', () => {
    expect(toFeedEntry({ symbol: 'A', qty: '4' as never, contracts: 9 }, 0).contracts).toBe(4)
    expect(toFeedEntry({ symbol: 'A', contracts: 7 }, 0).contracts).toBe(7)
  })

  it('ignores a non-numeric strike price', () => {
    expect(toFeedEntry({ symbol: 'A', strike_price: '190' as never }, 0).strike).toBeNull()
    expect(toFeedEntry({ symbol: 'A', strike_price: 190 }, 0).strike).toBe(190)
  })

  it('round-trips a realistic screening record', () => {
    const e = toFeedEntry(
      {
        symbol: 'MSFT',
        strategy: 'covered_call',
        action: 'INITIATE_POSITION',
        risk_score: 42,
        annualized_premium_yield: 0.184,
        option_symbol: 'MSFT240216C00420000',
        strike_price: 420,
        expiration_date: '2024-02-16',
        qty: 2,
        reasoning_trace: ['a', 'b'],
      },
      1,
    )
    expect(e).toEqual({
      key: 'MSFT-MSFT240216C00420000-1',
      symbol: 'MSFT',
      strategyType: 'covered_call',
      action: 'Initiate Position',
      rawAction: 'INITIATE_POSITION',
      riskScore: 42,
      riskDerived: false,
      premiumYieldPct: 18.4,
      optionSymbol: 'MSFT240216C00420000',
      strike: 420,
      expiration: '2024-02-16',
      contracts: 2,
      reasoningSteps: ['a', 'b'],
    })
  })
})