'use client'

import { useEffect, useRef, useState } from 'react'

export default function TradingViewChart({ symbol = 'NVDA' }: { symbol?: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [current, setCurrent] = useState(symbol)

  useEffect(() => {
    setCurrent(symbol)
  }, [symbol])

  useEffect(() => {
    if (!containerRef.current) return

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/tv.js'
    script.async = true
    script.onload = () => {
      // @ts-ignore
      if (typeof TradingView !== 'undefined' && containerRef.current) {
        // @ts-ignore
        new TradingView.widget({
          autosize: true,
          symbol: `NASDAQ:${current}`,
          interval: '15',
          container: containerRef.current,
          library_path: 'https://s3.tradingview.com/tv.js/',
          locale: 'en',
          theme: 'dark',
          style: '1',
          toolbar_bg: '#0f172a',
          hide_side_toolbar: false,
          allow_symbol_change: true,
          save_image: false,
          studies: ['MASimple@tv-basicstudies', 'MAExp@tv-basicstudies'],
          overrides: {
            'mainSeriesProperties.candleStyle.upColor': '#22c55e',
            'mainSeriesProperties.candleStyle.downColor': '#ef4444',
            'mainSeriesProperties.candleStyle.borderUpColor': '#22c55e',
            'mainSeriesProperties.candleStyle.borderDownColor': '#ef4444',
            'paneProperties.background': '#020617',
            'paneProperties.backgroundType': 'solid',
          },
        })
      }
    }
    document.head.appendChild(script)

    return () => {
      script.remove()
      if (containerRef.current) {
        containerRef.current.innerHTML = ''
      }
    }
  }, [current])

  return (
    <div className="rounded-xl border border-[#1e293b] bg-[#020617]">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-[#94a3b8]">Symbol:</span>
          <input
            value={current}
            onChange={(e) => setCurrent(e.target.value.toUpperCase())}
            className="w-28 rounded border border-[#1e293b] bg-[#0f172a] px-2 py-1 text-sm text-white"
            placeholder="NVDA"
          />
          <span className="text-xs text-[#64748b]">TradingView chart — dark theme</span>
        </div>
      </div>
      <div className="h-[520px] w-full">
        <div ref={containerRef} className="h-full w-full" />
      </div>
    </div>
  )
}
