'use client'

import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ClipboardList, Loader2, Play, ShieldAlert, Terminal as TerminalIcon } from 'lucide-react'
import { AnimatePresence } from 'framer-motion'
import { motion, useReducedMotion, EASE, DURATION, pressable } from '@/components/motion/primitives'
import {
  api,
  riskBlockFrom,
  type RiskDecision,
  type TradeRequest,
  type TradeResponse,
} from '../../../lib/api'
import { mintClientOrderId } from '../../../lib/orderMapping'
import RiskDecisionPanel from '../risk/RiskDecisionPanel'

type Side = 'buy' | 'sell'
type OrderType = 'market' | 'limit'

/**
 * Free-form order entry.
 *
 * Two things make this panel different from the agent-driven approval paths, and
 * both are why it needs its own guard rails:
 *
 *  1. Nothing here is validated by the council. The symbol, side and quantity are
 *     whatever was typed, so the pre-trade risk gate is the only thing between a
 *     typo and a real paper order.
 *  2. It previously submitted on a single click with no confirmation and no
 *     idempotency key, so a double-click could place two orders.
 *
 * The flow is now: type → preflight (POST /api/trade/preflight, runs the gate
 * without submitting) → read the verdict → confirm → submit. The submit button
 * is a UX affordance, NOT a security control: the real gate is server-side in
 * `backend/app/risk/`, and this panel must never be the way around it.
 */

export default function ManualTradePanel() {
  const reduce = useReducedMotion()
  const [symbol, setSymbol] = useState('AAPL')
  const [side, setSide] = useState<Side>('buy')
  const [qty, setQty] = useState('1')
  const [orderType, setOrderType] = useState<OrderType>('market')
  const [limitPrice, setLimitPrice] = useState('')
  const [tif, setTif] = useState('day')
  /**
   * idle → confirm → done. The confirm step exists so a single click cannot place
   * an order, and `pendingKey` carries the idempotency key across it.
   */
  const [phase, setPhase] = useState<'idle' | 'confirm' | 'done'>('idle')
  const [pendingKey, setPendingKey] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [risk, setRisk] = useState<RiskDecision | null>(null)
  const [result, setResult] = useState<TradeResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const limitEnabled = orderType === 'limit'

  const qtyNum = useMemo(() => {
    const parsed = Number(qty)
    return Number.isFinite(parsed) ? parsed : NaN
  }, [qty])

  const limitNum = useMemo(() => {
    if (!limitEnabled) return null
    const parsed = Number(limitPrice)
    return Number.isFinite(parsed) ? parsed : null
  }, [limitEnabled, limitPrice])

  const canSubmit = Boolean(symbol.trim()) && Number.isFinite(qtyNum) && qtyNum > 0 && (!limitEnabled || (limitNum !== null && limitNum > 0))

  useEffect(() => {
    setResult(null)
    setError(null)
    // Any edit invalidates the verdict: a gate decision belongs to the exact
    // order it was computed for, not to the form.
    setPhase('idle')
    setRisk(null)
    setPendingKey(null)
  }, [symbol, side, qty, orderType, limitPrice, tif])

  /**
   * Builds the request. `limit_price` is OMITTED rather than sent as null so the
   * backend applies its own market default instead of receiving a field it must
   * interpret — and `trade.py:27` rejects `limit_price: 0` outright (gt=0).
   */
  const buildPayload = (clientOrderId: string): TradeRequest => {
    const payload: TradeRequest = {
      symbol: symbol.trim().toUpperCase(),
      qty: qtyNum,
      side,
      type: orderType,
      time_in_force: tif,
      client_order_id: clientOrderId,
    }
    if (limitEnabled && limitNum != null && limitNum > 0) payload.limit_price = limitNum
    return payload
  }

  /** Runs the gate without submitting, so the verdict is visible BEFORE the click. */
  const preflight = async () => {
    if (!canSubmit || busy) return
    setBusy(true)
    setError(null)
    setResult(null)
    setRisk(null)
    // Minted once here and reused on submit and on every retry of THIS order, so
    // the backend's idempotency store (trade.py:201) recognises a repeat instead
    // of placing a second order.
    const key = mintClientOrderId()
    try {
      const res = await api.preflightTrade(buildPayload(key))
      setRisk(res.risk ?? null)
      setPendingKey(key)
      setPhase('confirm')
    } catch (err) {
      const blocked = riskBlockFrom(err)
      setRisk(blocked)
      setError(
        blocked
          ? 'Blocked by the pre-trade risk gate'
          : err instanceof Error
            ? err.message
            : 'Preflight failed',
      )
      setPhase('idle')
    } finally {
      setBusy(false)
    }
  }

  const submit = async () => {
    // `busy` alone is not enough: React state settles after the event, so two
    // fast clicks can both observe busy=false. The phase guard closes that
    // window by requiring an explicit confirm step first.
    if (phase !== 'confirm' || !pendingKey || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.placeTrade(buildPayload(pendingKey))
      setResult(res)
      setRisk(res.risk ?? risk)
      setPhase('done')
    } catch (err) {
      const blocked = riskBlockFrom(err)
      setRisk(blocked ?? risk)
      setError(
        blocked
          ? 'Blocked by the pre-trade risk gate'
          : err instanceof Error
            ? err.message
            : 'Trade failed',
      )
      // Stay in `confirm` so a retry reuses the SAME idempotency key. A fresh
      // key on retry would defeat the store and could double the position.
      setPhase('confirm')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded border border-[#1e293b] bg-[#0f172a] p-4 space-y-3">
      <div className="flex items-center gap-2">
        <TerminalIcon className="h-4 w-4 text-[#22c55e]" />
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[#94a3b8]">Manual Trade</h2>
        <span className="text-[10px] text-[#64748b]">submit to /api/trade</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <label className="space-y-1">
          <span className="text-[11px] text-[#94a3b8]">Symbol</span>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-full rounded border border-[#1e293b] bg-[#020617] px-2 py-1.5 text-xs text-white outline-none focus:border-[#22c55e]/50"
            placeholder="AAPL"
          />
        </label>

        <label className="space-y-1">
          <span className="text-[11px] text-[#94a3b8]">Side</span>
          <select
            value={side}
            onChange={(e) => setSide(e.target.value as Side)}
            className="w-full rounded border border-[#1e293b] bg-[#020617] px-2 py-1.5 text-xs text-white outline-none focus:border-[#22c55e]/50"
          >
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
          </select>
        </label>

        <label className="space-y-1">
          <span className="text-[11px] text-[#94a3b8]">Quantity</span>
          <input
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            inputMode="numeric"
            className="w-full rounded border border-[#1e293b] bg-[#020617] px-2 py-1.5 text-xs text-white outline-none focus:border-[#22c55e]/50"
            placeholder="1"
          />
        </label>

        <label className="space-y-1">
          <span className="text-[11px] text-[#94a3b8]">Order type</span>
          <select
            value={orderType}
            onChange={(e) => setOrderType(e.target.value as OrderType)}
            className="w-full rounded border border-[#1e293b] bg-[#020617] px-2 py-1.5 text-xs text-white outline-none focus:border-[#22c55e]/50"
          >
            <option value="market">Market</option>
            <option value="limit">Limit</option>
          </select>
        </label>

        <label className="space-y-1">
          <span className="text-[11px] text-[#94a3b8]">Time in force</span>
          <select
            value={tif}
            onChange={(e) => setTif(e.target.value)}
            className="w-full rounded border border-[#1e293b] bg-[#020617] px-2 py-1.5 text-xs text-white outline-none focus:border-[#22c55e]/50"
          >
            <option value="day">Day</option>
            <option value="gtc">GTC</option>
            <option value="opg">OPG</option>
            <option value="cls">CLS</option>
            <option value="ioc">IOC</option>
            <option value="fok">FOK</option>
          </select>
        </label>

        <label className="space-y-1">
          <span className="text-[11px] text-[#94a3b8]">Limit price</span>
          <input
            value={limitPrice}
            onChange={(e) => setLimitPrice(e.target.value)}
            disabled={!limitEnabled}
            inputMode="decimal"
            className={`w-full rounded border bg-[#020617] px-2 py-1.5 text-xs text-white outline-none focus:border-[#22c55e]/50 disabled:opacity-50 ${
              limitEnabled ? 'border-[#1e293b]' : 'border-transparent'
            }`}
            placeholder={limitEnabled ? '0.00' : 'market only'}
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {phase === 'confirm' ? (
          <>
            {/* Restate the order in words before it is placed. The gate's verdict
                sits directly below, so the decision is made with it in view. */}
            <span className="inline-flex items-center gap-1.5 rounded border border-[#f59e0b]/50 bg-[#451a03] px-2 py-1.5 text-[11px] text-[#fbbf24]">
              <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
              {side.toUpperCase()} {qtyNum} {symbol.trim().toUpperCase()} ·{' '}
              {limitEnabled && limitNum != null ? (
                `limit ${limitNum.toFixed(2)}`
              ) : (
                <span className="font-semibold text-[#f87171]">MARKET</span>
              )}{' '}
              · {tif.toUpperCase()}
            </span>
            <motion.button
              onClick={submit}
              disabled={busy}
              className="inline-flex items-center gap-2 rounded border border-[#22c55e]/60 bg-[#052e16] px-3 py-1.5 text-xs font-semibold text-[#22c55e] hover:bg-[#0a3318] disabled:opacity-50"
              {...(reduce ? {} : pressable)}
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              {busy ? 'Submitting…' : 'Confirm & Submit'}
            </motion.button>
            <button
              onClick={() => {
                setPhase('idle')
                setPendingKey(null)
              }}
              disabled={busy}
              className="rounded border border-[#334155] px-2 py-1.5 text-xs text-[#94a3b8] hover:text-white disabled:opacity-50"
            >
              Cancel
            </button>
          </>
        ) : (
          <motion.button
            onClick={preflight}
            disabled={!canSubmit || busy || phase === 'done'}
            className="inline-flex items-center gap-2 rounded border border-[#22c55e]/60 bg-[#052e16] px-3 py-1.5 text-xs font-semibold text-[#22c55e] hover:bg-[#0a3318] disabled:opacity-50"
            {...(reduce ? {} : pressable)}
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ClipboardList className="h-3.5 w-3.5" />}
            {busy ? 'Checking…' : 'Check Risk & Review'}
          </motion.button>
        )}

        <span className="text-[10px] text-[#64748b]">
          Every order runs the server-side risk gate first. Orders reach Alpaca only
          when credentials are configured; otherwise they are validated only.
        </span>
      </div>

      {/* Shown for a preflight verdict, a block and an accepted order alike — the
          reasons are equally worth reading when the answer is yes. */}
      {risk && <RiskDecisionPanel decision={risk} />}

      <AnimatePresence initial={false}>
        {error && (
          <motion.p
            key="trade-error"
            initial={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, height: 'auto' }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
            transition={reduce ? { duration: 0 } : { duration: DURATION.base, ease: EASE }}
            className="flex items-start gap-2 overflow-hidden rounded border border-[#ef4444]/40 bg-[#450a0a] px-3 py-2 text-xs text-[#f87171]"
          >
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {error}
          </motion.p>
        )}

        {result && (
          <motion.div
            key="trade-result"
            initial={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, height: 'auto' }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
            transition={reduce ? { duration: 0 } : { duration: DURATION.base, ease: EASE }}
            className="overflow-hidden rounded border border-[#1e293b] bg-[#0a0f1a] p-3 space-y-1"
          >
            <p className="text-[11px] font-semibold text-[#22c55e]">
              {result.duplicate
                ? 'Duplicate detected — original order returned'
                : result.submitted === false
                  ? `Validated, not submitted — ${String(result.reason ?? 'Alpaca not configured')}`
                  : `Trade submitted — ${result.status ?? 'pending'}`}
            </p>
            {/* The store recognised this payload and did NOT call the broker
                again. Presenting that as a fresh submission would tell the
                operator a second order exists when none does. */}
            {result.duplicate && (
              <p className="text-[11px] text-[#fbbf24]">
                Nothing was resubmitted
                {result.original_submitted_at ? ` — first sent ${result.original_submitted_at}` : ''}.
              </p>
            )}
            <p className="text-[11px] text-[#94a3b8]">
              {String(result.symbol)} · {String(result.side)} · {String(result.qty)} · {String(result.type)} · {String(result.time_in_force)}
            </p>
            {typeof result.limit_price === 'number' && (
              <p className="text-[11px] text-[#94a3b8]">limit {result.limit_price.toFixed(2)}</p>
            )}
            {result.id && (
              <p className="text-[10px] text-[#64748b]">order id: {result.id}</p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
