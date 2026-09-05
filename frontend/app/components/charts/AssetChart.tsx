'use client'

import { useEffect, useMemo, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

interface AssetChartProps {
  symbol: string
  timeframe?: string
  initialBars?: any[]
}

export default function AssetChart({ symbol, timeframe = '1Hour', initialBars = [] }: AssetChartProps) {
  const [tf, setTf] = useState(timeframe)
  const [bars, setBars] = useState<any[]>(initialBars)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetch(`/api/alpaca/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}&limit=500`)
      .then((r) => r.json())
      .then((json) => {
        if (!Array.isArray(json.bars)) throw new Error('invalid response')
        if (cancelled) return
        setBars(
          (json.bars || []).map((b: any) => ({
            time: String(b.t).slice(5, 16),
            close: Number(b.c),
            low: Number(b.l),
            high: Number(b.h),
          })),
        )
      })
      .catch((e) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol, tf])

  const [yDomain, setYDomain] = useState<number[] | null>(null)

  useEffect(() => {
    if (!bars.length) { setYDomain(null); return }
    const lows = bars.map((b) => Number(b.low))
    const highs = bars.map((b) => Number(b.high))
    const min = Math.min(...lows)
    const max = Math.max(...highs)
    const pad = Math.max((max - min) * 0.05, 0.01)
    setYDomain([Number((min - pad).toFixed(2)), Number((max + pad).toFixed(2))])
  }, [bars])

  const timeframes = ['1Min', '5Min', '15Min', '1Hour', '1Day']

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#020617]">
      <div className="flex items-center justify-between px-4 py-2">
        <div className="text-sm text-white">
          {symbol} <span className="text-xs text-[#94a3b8]">live chart</span>
        </div>
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
      <div className="px-2">
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={bars} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="closeGrad" x1="0" y1="0" x2="0" y2="1">
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
              domain={yDomain ?? undefined}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              axisLine={false}
              tickLine={false}
              width={60}
            />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8 }}
              labelStyle={{ color: '#f8fafc' }}
              itemStyle={{ color: '#22c55e' }}
            />
            <Area type="monotone" dataKey="close" stroke="#22c55e" fill="url(#closeGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {loading && <div className="px-4 py-2 text-xs text-[#94a3b8]">Loading chart...</div>}
      {error && <div className="px-4 py-2 text-xs text-red-400">Chart unavailable: {error}</div>}
    </div>
  )
}
