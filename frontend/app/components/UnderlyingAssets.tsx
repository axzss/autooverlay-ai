'use client'

import { FileText } from 'lucide-react'
import type { Position } from '@/types/portfolio'

interface UnderlyingAssetsProps {
  positions: Position[]
}

const fmt = (n: number) =>
  n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function UnderlyingAssets({ positions }: UnderlyingAssetsProps) {
  const equities = positions.filter((p) => p.asset_class !== 'option')

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e293b] flex items-center gap-2">
        <FileText className="h-4 w-4 text-[#22c55e]" />
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Underlying Assets</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1e293b] text-[#94a3b8]">
              <th className="text-left px-4 py-2.5 font-medium">ASSET</th>
              <th className="text-right px-4 py-2.5 font-medium">SHARES</th>
              <th className="text-right px-4 py-2.5 font-medium">AVG PRICE</th>
              <th className="text-right px-4 py-2.5 font-medium">CURRENT</th>
            </tr>
          </thead>
          <tbody>
            {equities.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-[#94a3b8]">
                  No underlying equity positions.
                </td>
              </tr>
            )}
            {equities.map((p) => {
              const qty = Number(p.qty)
              const avg = Number(p.avg_entry_price)
              const current = qty === 0 ? 0 : Number(p.market_value) / Math.abs(qty)
              const up = current >= avg
              return (
                <tr key={p.asset_id} className="border-b border-[#1e293b] last:border-0 hover:bg-[#1e293b]/40 transition-colors">
                  <td className="px-4 py-3 text-white font-medium">{p.symbol}</td>
                  <td className="px-4 py-3 text-right text-[#f8fafc] tabular-nums">{qty}</td>
                  <td className="px-4 py-3 text-right text-[#f8fafc] tabular-nums">${fmt(avg)}</td>
                  <td className={`px-4 py-3 text-right tabular-nums ${up ? 'text-[#22c55e]' : 'text-[#ef4444]'}`}>${fmt(current)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
