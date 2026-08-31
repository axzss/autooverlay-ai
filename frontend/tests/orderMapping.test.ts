import { describe, it, expect } from 'vitest'
import {
  intentToTradeRequest,
  feedEntryToTradeRequest,
  type MappingResult,
} from '../lib/orderMapping'
import type { FeedEntry, OrderIntent } from '../lib/api'

/**
 * P0 regression suite.
 *
 * Two call sites used to send the UNDERLYING equity ticker where an OCC option
 * symbol belongs:
 *   - AgentRunProvider.tsx:60  symbol: intent.symbol
 *   - AgentFeedCard.tsx:46     symbol: entry.optionSymbol ?? entry.symbol
 *
 * backend/app/routes/trade.py:22 documents `symbol` as "Equity ticker or OCC
 * option symbol" and forwards it to Alpaca verbatim, so approving a 1-contract
 * covered call on AAPL submitted `sell AAPL qty 1 market` — selling one share of
 * the underlying instead of writing a call, and selling the very collateral that
 * makes the position covered.
 *
 * The rule these tests pin: when no contract is resolved, refuse to build a
 * request. The underlying is never a substitute.
 */

const OCC = 'AAPL260918C00250000'

const intent: OrderIntent = {
  action: 'INITIATE_POSITION',
  strategy: 'covered_call',
  symbol: 'AAPL',
  option_symbol: OCC,
  contracts: 2,
  qty: 2,
  side: 'sell',
  type: 'limit',
  time_in_force: 'day',
  limit_price: 3.15,
  requires_approval: true,
  submitted: false,
}

const entry: FeedEntry = {
  key: 'AAPL-0',
  symbol: 'AAPL',
  strategyType: 'covered_call',
  action: 'Initiate Position',
  rawAction: 'INITIATE_POSITION',
  riskScore: 35,
  riskDerived: false,
  premiumYieldPct: 12,
  optionSymbol: OCC,
  strike: 250,
  expiration: '2026-09-18',
  contracts: 2,
  reasoningSteps: [],
}

/** Asserts a blocked result carries no submittable payload at all. */
function expectBlocked(result: MappingResult, pattern: RegExp) {
  expect(result.request).toBeNull()
  expect(result.blocked).not.toBeNull()
  expect(result.blocked as string).toMatch(pattern)
}

describe('intentToTradeRequest', () => {
  it('sends the OCC option symbol, never the underlying', () => {
    expect(intentToTradeRequest(intent).request?.symbol).toBe(OCC)
  })

  it('refuses to build a request when option_symbol is null', () => {
    expectBlocked(intentToTradeRequest({ ...intent, option_symbol: null }), /contract/i)
  })

  it('refuses to build a request when option_symbol is an empty string', () => {
    expectBlocked(intentToTradeRequest({ ...intent, option_symbol: '' }), /contract/i)
  })

  it('never substitutes the underlying for a missing contract', () => {
    const result = intentToTradeRequest({ ...intent, option_symbol: null })
    expect(JSON.stringify(result.request)).not.toContain('AAPL')
  })

  it('names the underlying in the block reason so the operator knows what was skipped', () => {
    const result = intentToTradeRequest({ ...intent, option_symbol: null })
    expect(result.blocked as string).toContain('AAPL')
  })

  it('carries contracts as qty for an option order', () => {
    expect(intentToTradeRequest(intent).request?.qty).toBe(2)
  })

  it('preserves a limit price and marks the order type limit', () => {
    const req = intentToTradeRequest(intent).request
    expect(req?.type).toBe('limit')
    expect(req?.limit_price).toBe(3.15)
  })

  it('omits limit_price entirely when null rather than sending 0', () => {
    const req = intentToTradeRequest({ ...intent, type: 'market', limit_price: null }).request
    expect(req).not.toBeNull()
    expect('limit_price' in (req as object)).toBe(false)
  })

  it('falls back to a market order when no limit price is present', () => {
    expect(
      intentToTradeRequest({ ...intent, type: 'limit', limit_price: null }).request?.type,
    ).toBe('market')
  })

  it('treats a zero limit price as absent, never as a real price', () => {
    const req = intentToTradeRequest({ ...intent, limit_price: 0 }).request
    expect(req?.type).toBe('market')
    expect('limit_price' in (req as object)).toBe(false)
  })

  it('passes side sell straight through', () => {
    expect(intentToTradeRequest(intent).request?.side).toBe('sell')
  })

  it('coerces any non-sell side to buy rather than forwarding it raw', () => {
    expect(intentToTradeRequest({ ...intent, side: 'BUY' }).request?.side).toBe('buy')
  })

  it('defaults an empty time_in_force to day', () => {
    expect(intentToTradeRequest({ ...intent, time_in_force: '' }).request?.time_in_force).toBe('day')
  })

  it('refuses a non-positive contract count', () => {
    expectBlocked(intentToTradeRequest({ ...intent, contracts: 0 }), /contract count/i)
  })

  it('refuses a fractional contract count', () => {
    expectBlocked(intentToTradeRequest({ ...intent, contracts: 1.5 }), /contract count/i)
  })

  it('emits no client_order_id — the submit layer owns idempotency', () => {
    expect('client_order_id' in (intentToTradeRequest(intent).request as object)).toBe(false)
  })
})

describe('feedEntryToTradeRequest', () => {
  it('sends the OCC option symbol from the feed entry', () => {
    expect(feedEntryToTradeRequest(entry).request?.symbol).toBe(OCC)
  })

  it('refuses to build a request when the feed entry has no contract', () => {
    expectBlocked(feedEntryToTradeRequest({ ...entry, optionSymbol: null }), /contract/i)
  })

  it('never falls back to the underlying ticker — the old ?? bug', () => {
    const result = feedEntryToTradeRequest({ ...entry, optionSymbol: null })
    expect(JSON.stringify(result.request)).not.toContain('AAPL')
  })

  it('sells to open and submits at market with no limit price', () => {
    const req = feedEntryToTradeRequest(entry).request
    expect(req?.side).toBe('sell')
    expect(req?.type).toBe('market')
    expect('limit_price' in (req as object)).toBe(false)
  })

  it('carries the entry contract count as qty', () => {
    expect(feedEntryToTradeRequest(entry).request?.qty).toBe(2)
  })

  it('refuses a non-positive contract count', () => {
    expectBlocked(feedEntryToTradeRequest({ ...entry, contracts: 0 }), /contract count/i)
  })
})
