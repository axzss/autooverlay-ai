'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'

export interface ChartBar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface TradeLevels {
  entry: number | null
  stopLoss: number | null
  takeProfit: number | null
  size: number | null
}

function PricePanel({ data }: { data: ChartBar[] }) {
  const yDomain = useMemo(() => {
    if (!data.length) return [0, 0]
    const lows = data.map((d) => d.low)
    const highs = data.map((d) => d.high)
    const min = Math.min(...lows)
    const max = Math.max(...highs)
    const pad = Math.max((max - min) * 0.05, 0.01)
    return [Number((min - pad).toFixed(2)), Number((max + pad).toFixed(2))]
  }, [data])

  return (
    <ResponsiveContainer width="100%" height={360}>
      <AreaChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis
          dataKey="time"
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          axisLine={{ stroke: '#1e293b' }}
          tickLine={false}
          minTickGap={40}
        />
        <YAxis
          domain={yDomain}
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          axisLine={false}
          tickLine={false}
          width={65}
        />
        <Tooltip
          contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
          labelStyle={{ color: '#f8fafc' }}
          itemStyle={{ color: '#22c55e' }}
        />
        <Area type="monotone" dataKey="close" stroke="#22c55e" fill="url(#priceGrad)" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export default function LiveTradingChartPage() {
  const [symbol, setSymbol] = useState('NVDA')
  const [tf, setTf] = useState('15Min')
  const [bars, setBars] = useState<ChartBar[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [levels, setLevels] = useState<TradeLevels>({ entry: null, stopLoss: null, takeProfit: null, size: null })
  const [overlays, setOverlays] = useState({
    volume: true,
    stopLoss: false,
    takeProfit: false,
    signals: true,
  })

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      fetch(`/api/alpaca/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}&limit=500`).then((r) => r.json()),
      fetch(`/api/indicators?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}&limit=500`).then((r) => r.json()),
      fetch(`/api/market-regime?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}`).then((r) => r.json()),
      fetch(`/api/ai-signals?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}&limit=500`).then((r) => r.json()),
    ])
      .then(([barsJson]) => {
        if (cancelled) return
        if (!Array.isArray(barsJson.bars)) throw new Error('invalid bars')
        setBars(
          (barsJson.bars || []).map((b: any) => ({
            time: String(b.t).slice(5, 16),
            open: Number(b.o),
            high: Number(b.h),
            low: Number(b.l),
            close: Number(b.c),
            volume: Number(b.v),
          })),
        )
      })
      .catch((e) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol, tf])

  const timeframes = ['1Min', '5Min', '15Min', '1Hour', '1Day']

  const updateLevel = (key: keyof TradeLevels, value: number | null) => setLevels((l) => ({ ...l, [key]: value }))

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#020617]">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-2">
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-24 rounded border border-[#1e293b] bg-[#0f172a] px-2 py-1 text-sm text-white"
          />
          <div className="flex gap-1">
            {timeframes.map((item) => (
              <button
                key={item}
                onClick={() => setTf(item)}
                className={`rounded px-2 py-1 text-xs ${
                  tf === item
                    ? 'bg-[#22c55e]/20 text-[#22c55e] border border-[#22c55e]/40'
                    : 'text-[#94a3b8] hover:text-white'
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 px-4 py-2">
        {Object.entries(overlays).map(([key, val]) => (
          <button
            key={key}
            onClick={() => setOverlays((o) => ({ ...o, [key]: !val }))}
            className={`rounded border px-2 py-1 text-xs ${
              val ? 'border-[#22c55e]/40 text-[#22c55e]' : 'border-[#1e293b] text-[#94a3b8]'
            }`}
          >
            {key.toUpperCase()}
          </button>
        ))}
      </div>

      <PricePanel data={bars} />

      {overlays.volume && (
        <div className="px-2">
          <ResponsiveContainer width="100%" height={100}>
            <BarChart data={bars} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
              <XAxis dataKey="time" hide />
              <YAxis hide />
              <Bar dataKey="volume" barSize={4} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 px-4 py-3 md:grid-cols-4">
        <div className="rounded border border-[#1e293b] bg-[#0f172a] p-3">
          <div className="text-xs text-[#94a3b8]">Entry</div>
          <input
            type="number"
            value={levels.entry ?? ''}
            onChange={(e) => updateLevel('entry', e.target.value ? Number(e.target.value) : null)}
            className="mt-1 w-full rounded border border-[#1e293b] bg-[#020617] px-2 py-1 text-xs text-white"
            placeholder="—"
          />
        </div>
        <div className="rounded border border-[#1e293b] bg-[#0f172a] p-3">
          <div className="text-xs text-[#94a3b8]">Stop Loss</div>
          <input
            type="number"
            value={levels.stopLoss ?? ''}
            onChange={(e) => updateLevel('stopLoss', e.target.value ? Number(e.target.value) : null)}
            className="mt-1 w-full rounded border border-[#1e293b] bg-[#020617] px-2 py-1 text-xs text-white"
            placeholder="—"
          />
        </div>
        <div className="rounded border border-[#1e293b] bg-[#0f172a] p-3">
          <div className="text-xs text-[#94a3b8]">Take Profit</div>
          <input
            type="number"
            value={levels.takeProfit ?? ''}
            onChange={(e) => updateLevel('takeProfit', e.target.value ? Number(e.target.value) : null)}
            className="mt-1 w-full rounded border border-[#1e293b] bg-[#020617] px-2 py-1 text-xs text-white"
            placeholder="—"
          />
        </div>
        <div className="rounded border border-[#1e293b] bg-[#0f172a] p-3">
          <div className="text-xs text-[#94a3b8]">Size</div>
          <input
            type="number"
            value={levels.size ?? ''}
            onChange={(e) => updateLevel('size', e.target.value ? Number(e.target.value) : null)}
            className="mt-1 w-full rounded border border-[#1e293b] bg-[#020617] px-2 py-1 text-xs text-white"
            placeholder="shares"
          />
        </div>
      </div>

      {loading && <div className="px-4 py-2 text-xs text-[#94a3b8]">Loading chart...</div>}
      {error && <div className="px-4 py-2 text-xs text-red-400">Chart unavailable: {error}</div>}
    </div>
  )
}
