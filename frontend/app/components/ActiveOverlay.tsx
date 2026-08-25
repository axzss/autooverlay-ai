'use client'

import { Zap } from 'lucide-react'

export default function ActiveOverlay() {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e293b] flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Active Overlay</h3>
        <span className="text-[10px] font-medium uppercase tracking-wider text-[#22c55e] bg-[#22c55e]/15 border border-[#22c55e]/30 px-2 py-0.5 rounded-sm">
          Yield Harvesting
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1e293b] text-[#94a3b8]">
              <th className="text-left px-4 py-2.5 font-medium">Contract</th>
              <th className="text-right px-4 py-2.5 font-medium">Qty</th>
              <th className="text-right px-4 py-2.5 font-medium">Unrealized P&L</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-[#1e293b] last:border-0 hover:bg-[#1e293b]/40 transition-colors">
              <td className="px-4 py-3">
                <span className="font-mono text-white">SPY 56.5C 9/4</span>
              </td>
              <td className="px-4 py-3 text-right font-mono text-[#f8fafc] tabular-nums">-1</td>
              <td className="px-4 py-3 text-right">
                <span className="font-mono text-[#22c55e] tabular-nums">+$120.00</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
