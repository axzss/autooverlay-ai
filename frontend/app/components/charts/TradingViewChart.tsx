'use client'

import { useEffect, useMemo, useState } from 'react'

export interface Bar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface Position {
  symbol: string
  qty: string
  avg_entry_price: string
}

interface TradingViewChartProps {
  positions?: Position[]
  defaultSymbol?: string
}

function SimpleCandlestickSVG({ data, height = 420, width = 800 }: { data: Bar[]; height?: number; width?: number }) {
  if (!data.length) return <div className="flex h-full items-center justify-center text-xs text-[#64748b]">No chart data</div>

  const padding = { top: 20, right: 60, bottom: 20, left: 10 }
  const chartWidth = width - padding.left - padding.right
  const chartHeight = height - padding.top - padding.bottom

  const allPrices = data.flatMap((d) => [d.high, d.low])
  const minPrice = Math.min(...allPrices)
  const maxPrice = Math.max(...allPrices)
  const priceRange = maxPrice - minPrice || 1

  const xScale = (i: number) => padding.left + (i / (data.length - 1 || 1)) * chartWidth
  const yScale = (price: number) => padding.top + chartHeight - ((price - minPrice) / priceRange) * chartHeight

  const candleWidth = Math.max(2, Math.min(12, chartWidth / data.length - 1))

  return (
    <svg width={width} height={height} className="h-full w-full" style={{ maxWidth: '100%' }}>
      {data.map((d, i) => {
        const x = xScale(i)
        const yOpen = yScale(d.open)
        const yClose = yScale(d.close)
        const yHigh = yScale(d.high)
        const yLow = yScale(d.low)
        const isUp = d.close >= d.open
        const color = isUp ? '#22c55e' : '#ef4444'
        const bodyTop = Math.min(yOpen, yClose)
        const bodyHeight = Math.max(Math.abs(yClose - yOpen), 1)

        return (
          <g key={i}>
            <line x1={x} y1={yHigh} x2={x} y2={yLow} stroke={color} strokeWidth={1} />
            <rect x={x - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} fill={color} />
          </g>
        )
      })}
      <line x1={padding.left} y1={padding.top} x2={width - padding.right} y2={padding.top} stroke="#1e293b" />
      <line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} stroke="#1e293b" />
    </svg>
  )
}

export default function TradingViewChart({ positions = [], defaultSymbol = 'NVDA' }: TradingViewChartProps) {
  const [symbol, setSymbol] = useState(defaultSymbol)
  const [tf, setTf] = useState('15Min')
  const [bars, setBars] = useState<Bar[]>(() => generateMockBars(defaultSymbol, '15Min', 120))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const availableSymbols = useMemo(() => {
    const syms = positions.map((p) => p.symbol).filter(Boolean)
    return syms.length > 0 ? syms : [defaultSymbol]
  }, [positions, defaultSymbol])

  const activePosition = useMemo(() => positions.find((p) => p.symbol === symbol), [positions, symbol])
  const entryPrice = activePosition ? Number(activePosition.avg_entry_price) : null

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetch(`/api/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}&limit=200`)
      .then((r) => r.json())
      .then((json) => {
        if (cancelled) return
        const list = Array.isArray(json.bars) ? json.bars : []
        if (list.length === 0) {
          setBars(generateMockBars(symbol, tf, 120))
          return
        }
        const mapped = list.map((b: any) => ({
          time: String(b.t).slice(5, 16),
          open: Number(b.o),
          high: Number(b.h),
          low: Number(b.l),
          close: Number(b.c),
          volume: Number(b.v),
        }))
        setBars(mapped)
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e.message)
          setBars(generateMockBars(symbol, tf, 120))
        }
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol, tf])

  const timeframes = ['1Min', '5Min', '15Min', '1Hour', '1Day']

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#020617]">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-2">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-28 rounded border border-[#1e293b] bg-[#0f172a] px-2 py-1 text-sm text-white"
          >
            {availableSymbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <div className="flex gap-1">
            {timeframes.map((item) => (
              <button
                key={item}
                onClick={() => setTf(item)}
                className={`rounded px-2 py-1 text-xs ${tf === item ? 'bg-[#22c55e]/20 text-[#22c55e] border border-[#22c55e]/40' : 'text-[#94a3b8] hover:text-white'}`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
        <div className="text-xs text-[#94a3b8]">
          {activePosition ? `${activePosition.symbol}  qty=${activePosition.qty}` : symbol}
        </div>
      </div>

      <div className="h-[420px] w-full">
        <SimpleCandlestickSVG data={bars} />
      </div>

      {entryPrice != null && Number.isFinite(entryPrice) && (
        <div className="px-4 py-2 text-xs text-[#fbbf24]">Entry: ${entryPrice.toFixed(2)}</div>
      )}

      {loading && <div className="px-4 py-2 text-xs text-[#94a3b8]">Loading chart...</div>}
      {error && <div className="px-4 py-2 text-xs text-red-400">Chart unavailable: {error}</div>}
    </div>
  )
}

function generateMockBars(symbol: string, timeframe: string, count: number): Bar[] {
  const out: Bar[] = []
  let price = symbol === 'AAPL' ? 320 : symbol === 'NVDA' ? 220 : 90
  const now = new Date()
  const tfMinutes = timeframe === '1Min' ? 1 : timeframe === '5Min' ? 5 : timeframe === '15Min' ? 15 : timeframe === '1Hour' ? 60 : 1440
  for (let i = count - 1; i >= 0; i--) {
    const t = new Date(now.getTime() - i * tfMinutes * 60 * 1000)
    const timeStr = t.toISOString().slice(5, 16)
    const change = (Math.random() - 0.5) * price * 0.02
    const open = price
    const close = price + change
    const high = Math.max(open, close) + Math.random() * price * 0.005
    const low = Math.min(open, close) - Math.random() * price * 0.005
    const volume = Math.floor(1000 + Math.random() * 5000)
    out.push({ time: timeStr, open, high, low, close, volume })
    price = close
  }
  return out
}
