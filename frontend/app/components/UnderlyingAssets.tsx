'use client'

import { FileText } from 'lucide-react'

export default function UnderlyingAssets() {
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
            <tr className="border-b border-[#1e293b] last:border-0 hover:bg-[#1e293b]/40 transition-colors">
              <td className="px-4 py-3 text-white font-medium">SPY</td>
              <td className="px-4 py-3 text-right text-[#f8fafc] tabular-nums">100</td>
              <td className="px-4 py-3 text-right text-[#f8fafc] tabular-nums">$500.00</td>
              <td className="px-4 py-3 text-right text-[#22c55e] tabular-nums">$512.45</td>
            </tr>
            <tr className="border-b border-[#1e293b] last:border-0 hover:bg-[#1e293b]/40 transition-colors">
              <td className="px-4 py-3 text-white font-medium">QQQ</td>
              <td className="px-4 py-3 text-right text-[#f8fafc] tabular-nums">50</td>
              <td className="px-4 py-3 text-right text-[#f8fafc] tabular-nums">$420.50</td>
              <td className="px-4 py-3 text-right text-[#22c55e] tabular-nums">$435.10</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
