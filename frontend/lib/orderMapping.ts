/**
 * The single place an OrderIntent or a FeedEntry becomes a TradeRequest.
 *
 * Why this module exists
 * ----------------------
 * Two call sites used to build the request inline and both sent the UNDERLYING
 * equity ticker where an OCC option symbol belongs:
 *
 *   AgentRunProvider.tsx:60   symbol: intent.symbol
 *   AgentFeedCard.tsx:46      symbol: entry.optionSymbol ?? entry.symbol
 *
 * `backend/app/routes/trade.py:22` documents `symbol` as "Equity ticker or OCC
 * option symbol" and forwards whatever it is given straight to Alpaca. So
 * approving a 1-contract covered call on AAPL submitted
 * `sell AAPL qty 1 market` — one SHARE of the underlying, not a written call.
 * That is the wrong instrument, the wrong quantity semantics, and it sells the
 * collateral that makes the position covered. "Never naked" is the product's
 * headline safety property; that path broke it directly.
 *
 * The governing rule
 * ------------------
 * When no option contract is resolved, REFUSE to build a request. The underlying
 * is never a substitute. Per KNOWN-ISSUES #2 a null `option_symbol` is the normal
 * case today, not an edge case, so this path is exercised constantly — which is
 * exactly why it must fail loudly instead of silently degrading.
 *
 * `_pick_option_contract()` (backend/app/routes/agent.py:19) may start resolving
 * real contracts mid-sprint. Every check below keys on the null VALUE rather than
 * on the issue's status, so both worlds are handled without further edits.
 */

import type { FeedEntry, OrderIntent, TradeRequest } from './api'

export interface MappingResult {
  /** The request to submit, or null when it could not be built safely. */
  request: TradeRequest | null
  /** Operator-facing reason the request was refused. Null when `request` is set. */
  blocked: string | null
}

/**
 * Provenance carried from the agent run into the order.
 *
 * `backend/app/routes/trade.py:39-42` records `run_id` and `directive_ref` on
 * every intent and states that absent provenance is allowed "only with an
 * explicit, audited manual override". An order in the ledger with neither
 * cannot be traced back to the run that proposed it, which reduces the audit
 * trail to a list of orders.
 */
export interface OrderProvenance {
  runId?: string | null
  directiveRef?: string | null
  /** Idempotency key. Minted once per approval and REUSED on retry. */
  clientOrderId?: string | null
}

function blocked(reason: string): MappingResult {
  return { request: null, blocked: reason }
}

/**
 * A contract count must be a whole positive number: one option contract is 100
 * shares of exposure and there is no such thing as half of one.
 */
function invalidContracts(contracts: number): boolean {
  return !Number.isFinite(contracts) || contracts <= 0 || !Number.isInteger(contracts)
}

/**
 * A limit price is only real when it is finite and above zero. Zero is not a
 * price — treating it as one would submit an unfillable order, and forwarding it
 * as `limit_price: 0` is rejected by `trade.py:27` (`gt=0`) anyway.
 */
function usableLimitPrice(price: number | null | undefined): number | null {
  if (price == null) return null
  if (!Number.isFinite(price) || price <= 0) return null
  return price
}

/**
 * Builds the option-order request. `limit_price` is OMITTED rather than sent as
 * null when absent, so the backend applies its own `market` default instead of
 * receiving a field it must interpret.
 */
function buildRequest(args: {
  optionSymbol: string
  contracts: number
  side: 'buy' | 'sell'
  timeInForce: string
  limitPrice: number | null
  provenance?: OrderProvenance
}): TradeRequest {
  const request: TradeRequest = {
    symbol: args.optionSymbol,
    qty: args.contracts,
    side: args.side,
    type: args.limitPrice == null ? 'market' : 'limit',
    time_in_force: args.timeInForce || 'day',
  }
  if (args.limitPrice != null) request.limit_price = args.limitPrice
  // Provenance and idempotency are omitted rather than sent as null: the
  // backend's Optional fields default to None, and an explicit null adds a
  // field the store has to interpret.
  const p = args.provenance
  if (p?.clientOrderId) request.client_order_id = p.clientOrderId
  if (p?.runId) request.run_id = p.runId
  if (p?.directiveRef) request.directive_ref = p.directiveRef
  return request
}

/** Maps an agent order intent to a trade request, or refuses with a reason. */
export function intentToTradeRequest(
  intent: OrderIntent,
  provenance?: OrderProvenance,
): MappingResult {
  const occ = intent.option_symbol?.trim()
  if (!occ) {
    return blocked(
      `No option contract resolved for ${intent.symbol}. The underlying ticker is ` +
        `not a substitute — submitting it would trade the wrong instrument. ` +
        `Resolve the contract before approving.`,
    )
  }
  if (invalidContracts(intent.contracts)) {
    return blocked(
      `Invalid contract count (${String(intent.contracts)}) for ${occ}. ` +
        `A contract count must be a whole number greater than zero.`,
    )
  }
  return {
    request: buildRequest({
      optionSymbol: occ,
      contracts: intent.contracts,
      side: intent.side === 'sell' ? 'sell' : 'buy',
      timeInForce: intent.time_in_force,
      limitPrice: usableLimitPrice(intent.limit_price),
      provenance,
    }),
    blocked: null,
  }
}

/**
 * Maps a screening feed entry to a sell-to-open request, or refuses with a reason.
 *
 * A feed entry carries no limit price, so this is deliberately a market order —
 * and the caller must say the word MARKET in its confirmation step, because a
 * market order on an illiquid option fills at a poor price.
 */
export function feedEntryToTradeRequest(
  entry: FeedEntry,
  provenance?: OrderProvenance,
): MappingResult {
  const occ = entry.optionSymbol?.trim()
  if (!occ) {
    return blocked(
      `No option contract resolved for ${entry.symbol}. The underlying ticker is ` +
        `not a substitute — submitting it would sell the shares instead of ` +
        `writing the option.`,
    )
  }
  if (invalidContracts(entry.contracts)) {
    return blocked(
      `Invalid contract count (${String(entry.contracts)}) for ${occ}. ` +
        `A contract count must be a whole number greater than zero.`,
    )
  }
  return {
    request: buildRequest({
      optionSymbol: occ,
      contracts: entry.contracts,
      side: 'sell',
      timeInForce: 'day',
      limitPrice: null,
      provenance,
    }),
    blocked: null,
  }
}

/**
 * Mints an idempotency key for one approval.
 *
 * Reused verbatim on every retry of the SAME approval so the backend's
 * idempotency store (`trade.py:201`) recognises the payload and returns the
 * original response instead of placing a second order. A fresh key per retry
 * would defeat the entire mechanism.
 */
export function mintClientOrderId(): string {
  const rand =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : Math.random().toString(36).slice(2, 12)
  return `ao-${Date.now().toString(36)}-${rand}`.slice(0, 128)
}
