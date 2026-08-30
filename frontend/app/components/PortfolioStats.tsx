'use client'

interface PortfolioStatsProps {
  accountInfo: {
    portfolio_value: string
    equity: string
    last_equity: string
    cash: string
    long_market_value?: string
    short_market_value?: string
  }
  positions?: Array<{ symbol: string; asset_class?: string; market_value?: string }>
}

const usd = (v: string | number) =>
  Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function PortfolioStats({ accountInfo, positions = [] }: PortfolioStatsProps) {
  const total = Number(accountInfo.portfolio_value)
  const longVal = Number(accountInfo.long_market_value ?? 0)
  const shortVal = Number(accountInfo.short_market_value ?? 0)
  const netLong = longVal - shortVal

  const equityPositions = positions.filter((p) => (p.asset_class ?? '').toLowerCase() !== 'option')
  const equityNames = equityPositions.map((p) => p.symbol).filter(Boolean)
  const topName = equityNames[0] ?? '—'

  const concentrationPct = total > 0 ? (netLong / total) * 100 : 0
  const concentrationLabel =
    equityNames.length <= 1 ? 'Concentrated'
    : concentrationPct > 40 ? 'Elevated'
    : 'High'

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-4">Portfolio Allocation</h3>
      <div className="flex items-center justify-center mb-4">
        <div className="relative h-32 w-32">
          <div className="absolute inset-0 border-2 border-[#1e293b] bg-[#0f172a]" />
          <div className="absolute inset-2 border-2 border-[#22c55e] rotate-12 bg-[#22c55e]/10" />
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-3xl font-bold text-white tabular-nums">
              {equityNames.length > 0 ? `${Math.round(concentrationPct)}%` : '—'}
            </span>
            <span className="text-sm text-[#22c55e] font-medium">{topName}</span>
          </div>
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-[#94a3b8]">Total Assets</span>
          <span className="text-lg font-semibold text-white tabular-nums">
            {Number.isFinite(total) && total > 0 ? `$${usd(total)}` : '—'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-[#94a3b8]">Diversification Score</span>
          <span
            className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${
              concentrationLabel === 'High'
                ? 'bg-[#052e16] text-[#22c55e]'
                : concentrationLabel === 'Elevated'
                  ? 'bg-[#451a03] text-[#fbbf24]'
                  : 'bg-[#1e293b] text-[#94a3b8]'
            }`}
          >
            {equityNames.length > 0 ? concentrationLabel : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}
