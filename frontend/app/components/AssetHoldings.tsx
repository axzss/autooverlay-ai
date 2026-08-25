'use client'

import { Position } from '@/types/portfolio'

interface AssetHoldingsProps {
  positions: Position[]
}

export default function AssetHoldings({ positions }: AssetHoldingsProps) {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e293b]">
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Current Holdings</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1e293b] text-[#94a3b8]">
              <th className="text-left px-4 py-2.5 font-medium">Ticker</th>
              <th className="text-left px-4 py-2.5 font-medium">Type</th>
              <th className="text-right px-4 py-2.5 font-medium">Qty</th>
              <th className="text-right px-4 py-2.5 font-medium">Avg Price</th>
              <th className="text-right px-4 py-2.5 font-medium">Current Price</th>
              <th className="text-right px-4 py-2.5 font-medium">Unrealized P&L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((position) => {
              const qty = Number(position.qty)
              const marketValue = Number(position.market_value)
              const currentPrice = qty === 0 ? 0 : marketValue / Math.abs(qty)
              const avgCost = Number(position.avg_entry_price)
              const pl = Number(position.unrealized_pl)

              return (
                <tr key={position.asset_id} className="border-b border-[#1e293b] last:border-0 hover:bg-[#1e293b]/40 transition-colors">
                  <td className="px-4 py-3 text-white font-medium">{position.symbol}</td>
                  <td className="px-4 py-3 text-[#f8fafc]">{position.asset_class === 'option' ? 'Covered Call' : 'Equity'}</td>
                  <td className="px-4 py-3 text-right font-mono text-[#f8fafc] tabular-nums">{qty}</td>
                  <td className="px-4 py-3 text-right font-mono text-[#f8fafc] tabular-nums">${avgCost.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right font-mono text-[#f8fafc] tabular-nums">${currentPrice.toFixed(2)}</td>
                  <td className={`px-4 py-3 text-right font-mono tabular-nums ${pl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]'}`}>
                    {pl >= 0 ? '+' : ''}{pl.toFixed(2)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
