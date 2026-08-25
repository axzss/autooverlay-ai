'use client'

interface PortfolioStatsProps {
  accountInfo: {
    portfolio_value: string
    equity: string
    last_equity: string
    cash: string
  }
}

export default function PortfolioStats({ accountInfo }: PortfolioStatsProps) {
  const totalValue = Number(accountInfo.portfolio_value)

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-4">Portfolio Allocation</h3>
      <div className="flex items-center justify-center mb-4">
        <div className="relative h-32 w-32">
          <div className="absolute inset-0 border-2 border-[#1e293b] bg-[#0f172a]" />
          <div className="absolute inset-2 border-2 border-[#22c55e] rotate-12 bg-[#22c55e]/10" />
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-3xl font-bold text-white tabular-nums">60%</span>
            <span className="text-sm text-[#22c55e] font-medium">SPY</span>
          </div>
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-[#94a3b8]">Total Assets</span>
          <span className="text-lg font-semibold text-white tabular-nums">
            {totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-[#94a3b8]">Diversification Score</span>
          <span className="inline-flex items-center rounded bg-[#052e16] px-2 py-0.5 text-xs font-medium text-[#22c55e]">
            High
          </span>
        </div>
      </div>
    </div>
  )
}
