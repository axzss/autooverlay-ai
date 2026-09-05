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

function sma(data: number[], length = 20): (number | null)[] {
  const out: (number | null)[] = []
  for (let i = 0; i < data.length; i++) {
    if (i < length - 1) { out.push(null); continue }
    const slice = data.slice(i - length + 1, i + 1)
    out.push(slice.reduce((a, b) => a + b, 0) / length)
  }
  return out
}

function ema(data: number[], length = 50): (number | null)[] {
  const out: (number | null)[] = []
  const k = 2 / (length + 1)
  let prev: number | null = null
  for (let i = 0; i < data.length; i++) {
    if (i < length - 1) { out.push(null); continue }
    const start = i - length + 1
    const slice = data.slice(start, i + 1)
    const sma0 = slice.reduce((a, b) => a + b, 0) / length
    prev = prev == null ? sma0 : (data[i] - prev!) * k + prev!
    out.push(prev)
  }
  return out
}

function generateMockBars(symbol: string, timeframe: string, count: number): Bar[] {
  const out: Bar[] = []
  let price = symbol === 'AAPL' ? 320 : symbol === 'NVDA' ? 220 : symbol === 'MSFT' ? 420 : 90
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

function AnalysisChart({ data, entryPrice, sma20, ema50 }: {
  data: Bar[]
  entryPrice?: number | null
  sma20?: (number | null)[]
  ema50?: (number | null)[]
}) {
  if (!data.length) return <div className="flex h-full items-center justify-center text-xs text-[#64748b]">No chart data</div>

  const pad = { top: 24, right: 64, bottom: 24, left: 8 }
  const width = 1200
  const height = 520
  const chartW = width - pad.left - pad.right
  const chartH = height - pad.top - pad.bottom

  const highs = data.map(d => d.high)
  const lows = data.map(d => d.low)
  const volumes = data.map(d => d.volume)

  const priceMin = Math.min(...lows)
  const priceMax = Math.max(...highs)
  const priceRange = priceMax - priceMin || 1

  const maxVol = Math.max(...volumes) || 1
  const volH = 70
  const x = (i: number) => pad.left + (i / (data.length - 1 || 1)) * chartW
  const y = (price: number) => pad.top + chartH - ((price - priceMin) / priceRange) * chartH
  const yv = (v: number) => pad.top + chartH + 8 + (1 - v / maxVol) * volH

  const candleW = Math.max(2, Math.min(10, chartW / data.length - 1))
  const lineValues = [
    ...(sma20 || []).filter((v): v is number => v !== null),
    ...(ema50 || []).filter((v): v is number => v !== null),
    ...(entryPrice != null && Number.isFinite(entryPrice) ? [entryPrice] : []),
  ]
  const minLine = Math.min(priceMin, ...(lineValues.length ? lineValues : [priceMin]))
  const maxLine = Math.max(priceMax, ...(lineValues.length ? lineValues : [priceMax]))
  const lineRange = maxLine - minLine || priceRange
  const yLine = (price: number) => pad.top + chartH - ((price - minLine) / lineRange) * chartH

  const labelEvery = Math.max(1, Math.floor(data.length / 6))

  return (
    <svg width="100%" height={height + 90} viewBox={`0 0 ${width} ${height + 90}`} preserveAspectRatio="none" className="h-full w-full" style={{ minHeight: 380 }}>
      <defs>
        <linearGradient id="volGrad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#22c55e" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#22c55e" stopOpacity="0.05" />
        </linearGradient>
      </defs>

      <line x1={pad.left} y1={pad.top} x2={width - pad.right} y2={pad.top} stroke="#1e293b" />
      <line x1={pad.left} y1={pad.top + chartH} x2={width - pad.right} y2={pad.top + chartH} stroke="#1e293b" />
      {[0.25, 0.5, 0.75].map((p) => (
        <g key={p}>
          <line x1={pad.left} y1={pad.top + chartH * p} x2={width - pad.right} y2={pad.top + chartH * p} stroke="#1e293b" strokeDasharray="3 3" />
          <text x={width - pad.right + 4} y={pad.top + chartH * p + 3} fill="#64748b" fontSize="10">{(priceMax - priceRange * p).toFixed(2)}</text>
        </g>
      ))}
      <text x={pad.left} y={pad.top - 8} fill="#94a3b8" fontSize="10" fontWeight="600">Candlestick + Indicators</text>

      {data.map((d, i) => {
        const xv = x(i)
        const yvb = yv(d.volume)
        const color = d.close >= d.open ? '#22c55e' : '#ef4444'
        return <rect key={'v'+i} x={xv - candleW/2} y={yvb} width={candleW} height={pad.top + chartH + 8 - yvb} fill={color} opacity={0.35} />
      })}
      <text x={pad.left} y={pad.top + chartH + 18} fill="#64748b" fontSize="9">VOL</text>

      {data.map((d, i) => {
        const xi = x(i)
        const yOpen = y(d.open)
        const yClose = y(d.close)
        const yHigh = y(d.high)
        const yLow = y(d.low)
        const color = d.close >= d.open ? '#22c55e' : '#ef4444'
        return (
          <g key={'c'+i}>
            <line x1={xi} y1={yHigh} x2={xi} y2={yLow} stroke={color} strokeWidth={1} />
            <rect x={xi - candleW/2} y={Math.min(yOpen, yClose)} width={candleW} height={Math.max(Math.abs(yClose - yOpen), 1)} fill={color} />
          </g>
        )
      })}

      {sma20 && sma20.map((v, i) => {
        if (v == null) return null
        return <circle key={'sma'+i} cx={x(i)} cy={yLine(v)} r="1.2" fill="#f59e0b" />
      })}

      {ema50 && ema50.map((v, i) => {
        if (v == null) return null
        return <circle key={'ema'+i} cx={x(i)} cy={yLine(v)} r="1.2" fill="#3b82f6" />
      })}

      {entryPrice != null && Number.isFinite(entryPrice) && (
        <g>
          <line x1={pad.left} y1={yLine(entryPrice)} x2={width - pad.right} y2={yLine(entryPrice)} stroke="#fbbf24" strokeDasharray="4 3" />
          <text x={width - pad.right + 4} y={yLine(entryPrice) + 3} fill="#fbbf24" fontSize="10">ENTRY {entryPrice.toFixed(2)}</text>
        </g>
      )}

      {data.map((d, i) => {
        if (i % labelEvery !== 0 && i !== data.length - 1) return null
        return <text key={'x'+i} x={x(i)} y={pad.top + chartH + 14} fill="#64748b" fontSize="9" textAnchor="middle">{d.time}</text>
      })}
    </svg>
  )
}

export default function TradingViewChart({ positions = [], defaultSymbol = 'NVDA' }: TradingViewChartProps) {
  const [symbol, setSymbol] = useState(defaultSymbol)
  const [tf, setTf] = useState('15Min')
  const [bars, setBars] = useState<Bar[]>(() => generateMockBars(defaultSymbol, '15Min', 200))
  const [indicators, setIndicators] = useState({ showSMA: true, showEMA: true, showEntry: true })

  const availableSymbols = useMemo(() => {
    const syms = positions.map((p) => p.symbol).filter(Boolean)
    return syms.length > 0 ? syms : [defaultSymbol]
  }, [positions, defaultSymbol])

  const activePosition = useMemo(() => positions.find((p) => p.symbol === symbol), [positions, symbol])
  const entryPrice = activePosition ? Number(activePosition.avg_entry_price) : null

  useEffect(() => {
    let cancelled = false
    fetch(`/api/bars?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(tf)}&limit=200`)
      .then((r) => r.json())
      .then((json) => {
        if (cancelled) return
        const list = Array.isArray(json.bars) ? json.bars : []
        if (list.length === 0) {
          setBars(generateMockBars(symbol, tf, 200))
          return
        }
        setBars(list.map((b: any) => ({
          time: String(b.t).slice(5, 16),
          open: Number(b.o),
          high: Number(b.h),
          low: Number(b.l),
          close: Number(b.c),
          volume: Number(b.v),
        })))
      })
      .catch(() => {
        if (!cancelled) setBars(generateMockBars(symbol, tf, 200))
      })
    return () => { cancelled = true }
  }, [symbol, tf])

  const closes = useMemo(() => bars.map(d => d.close), [bars])
  const sma20 = useMemo(() => sma(closes, 20), [closes])
  const ema50 = useMemo(() => ema(closes, 50), [closes])

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
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1 text-[11px] text-[#94a3b8]">
            <input type="checkbox" checked={indicators.showSMA} onChange={(e) => setIndicators({ ...indicators, showSMA: e.target.checked })} />
            <span className="text-[#f59e0b]">SMA 20</span>
          </label>
          <label className="flex items-center gap-1 text-[11px] text-[#94a3b8]">
            <input type="checkbox" checked={indicators.showEMA} onChange={(e) => setIndicators({ ...indicators, showEMA: e.target.checked })} />
            <span className="text-[#3b82f6]">EMA 50</span>
          </label>
          <div className="text-xs text-[#94a3b8]">
            {activePosition ? `${activePosition.symbol}  qty=${activePosition.qty}` : symbol}
          </div>
        </div>
      </div>

      <div className="w-full overflow-x-auto">
        <AnalysisChart
          data={bars}
          entryPrice={indicators.showEntry ? entryPrice : null}
          sma20={indicators.showSMA ? sma20 : undefined}
          ema50={indicators.showEMA ? ema50 : undefined}
        />
      </div>

      <div className="px-4 py-2 flex flex-wrap gap-3 text-[11px] text-[#94a3b8]">
        <span className="text-[#f59e0b]">● SMA 20</span>
        <span className="text-[#3b82f6]">● EMA 50</span>
        <span className="text-[#fbbf24]">— Entry</span>
        <span className="text-[#22c55e]">▲ Bull candle</span>
        <span className="text-[#ef4444]">▼ Bear candle</span>
        <span>Vol: teal bars</span>
      </div>
    </div>
  )
}
