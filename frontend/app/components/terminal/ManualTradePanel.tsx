'use client'

import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ClipboardList, Loader2, Play, Terminal as TerminalIcon } from 'lucide-react'
import { AnimatePresence } from 'framer-motion'
import { motion, useReducedMotion, EASE, DURATION, pressable } from '@/components/motion/primitives'
import { api, type OrderIntent, type TradeRequest, type TradeResponse } from '../../../lib/api'

type Side = 'buy' | 'sell'
type OrderType = 'market' | 'limit'

export default function ManualTradePanel() {
  const reduce = useReducedMotion()
  const [symbol, setSymbol] = useState('AAPL')
  const [side, setSide] = useState<Side>('buy')
  const [qty, setQty] = useState('1')
  const [orderType, setOrderType] = useState<OrderType>('market')
  const [limitPrice, setLimitPrice] = useState('')
  const [tif, setTif] = useState('day')
  const [running, setRunning] = useState(false)
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
  }, [symbol, side, qty, orderType, limitPrice, tif])

  const submit = async () => {
    if (!canSubmit || running) return
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const payload: TradeRequest = {
        symbol: symbol.trim().toUpperCase(),
        qty: qtyNum,
        side,
        type: orderType,
        time_in_force: tif,
        limit_price: limitNum,
      }
      const res = await api.placeTrade(payload)
      setResult(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Trade failed')
    } finally {
      setRunning(false)
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
        <motion.button
          onClick={submit}
          disabled={!canSubmit || running}
          className="inline-flex items-center gap-2 rounded border border-[#22c55e]/60 bg-[#052e16] px-3 py-1.5 text-xs font-semibold text-[#22c55e] hover:bg-[#0a3318] disabled:opacity-50"
          {...(reduce ? {} : pressable)}
        >
          {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          {running ? 'Submitting…' : 'Submit Trade'}
        </motion.button>

        <span className="text-[10px] text-[#64748b]">
          Orders are sent to Alpaca when configured; otherwise they are validated only.
        </span>
      </div>

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
              Trade submitted — {result.status ?? 'pending'}
            </p>
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
