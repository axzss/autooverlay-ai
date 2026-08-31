import { describe, it, expect } from 'vitest'
import { riskBlockFrom, ApiError, type RiskDecision } from '../lib/api'

/**
 * The 409 contract.
 *
 * `POST /api/trade` answers 409 with `{detail: {message, risk}}` when the
 * pre-trade risk gate refuses an order. The backend chose 409 over 422
 * deliberately (`backend/app/routes/trade.py:186-195`) so the UI can tell "you
 * sent nonsense" from "this trade is unsafe right now".
 *
 * Before these tests the frontend stringified that body and sliced it to 200
 * characters, so the reasons the gate refused reached the operator as truncated
 * JSON. What is pinned here: the structure survives, and only a real 409 with a
 * real decision is treated as a risk block.
 */

const decision: RiskDecision = {
  allowed: false,
  checks: [
    {
      name: 'naked_short_call',
      passed: false,
      severity: 'BLOCK',
      detail: 'Short 2 calls against 0 shares — 200 shares required.',
      values: { contracts: 2, shares_held: 0, shares_required: 200 },
    },
    {
      name: 'cash_reserve',
      passed: true,
      severity: 'INFO',
      detail: 'Cash reserve 18.4% above the 10% floor.',
      values: { reserve_pct: 18.4 },
    },
  ],
  hard_failures: ['Short 2 calls against 0 shares — 200 shares required.'],
  warnings: [],
  mode: 'live',
  snapshot_hash: 'abc123def4567890',
}

describe('riskBlockFrom', () => {
  it('extracts the decision from a 409 carrying {message, risk}', () => {
    const err = new ApiError('API /api/trade responded 409', undefined, 409, {
      message: 'order blocked by the pre-trade risk gate',
      risk: decision,
    })
    expect(riskBlockFrom(err)?.hard_failures).toEqual(decision.hard_failures)
  })

  it('preserves every check, not just the summary', () => {
    const err = new ApiError('blocked', undefined, 409, { risk: decision })
    expect(riskBlockFrom(err)?.checks).toHaveLength(2)
  })

  it('preserves the numbers each check was decided on', () => {
    const err = new ApiError('blocked', undefined, 409, { risk: decision })
    expect(riskBlockFrom(err)?.checks[0].values).toEqual({
      contracts: 2,
      shares_held: 0,
      shares_required: 200,
    })
  })

  it('returns null for a 409 with no risk payload', () => {
    const err = new ApiError('conflict', undefined, 409, { message: 'something else' })
    expect(riskBlockFrom(err)).toBeNull()
  })

  it('returns null for a non-409 ApiError even when a risk body is present', () => {
    const err = new ApiError('server error', undefined, 500, { risk: decision })
    expect(riskBlockFrom(err)).toBeNull()
  })

  it('returns null for an unreachable backend, which has no status at all', () => {
    expect(riskBlockFrom(new ApiError('API /api/trade unreachable'))).toBeNull()
  })

  it('returns null for a plain Error', () => {
    expect(riskBlockFrom(new Error('boom'))).toBeNull()
  })

  it('returns null for a string body (a non-JSON error response)', () => {
    expect(riskBlockFrom(new ApiError('bad', undefined, 409, 'plain text'))).toBeNull()
  })

  it('does not throw on null or undefined', () => {
    expect(riskBlockFrom(null)).toBeNull()
    expect(riskBlockFrom(undefined)).toBeNull()
  })
})
