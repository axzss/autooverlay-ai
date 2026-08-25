'use client'

import { Layers } from 'lucide-react'

export default function ActiveOverlayContracts() {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e293b] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-[#22c55e]" />
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Active Overlay Contracts</h3>
        </div>
        <span className="text-[10px] font-medium uppercase tracking-wider text-[#22c55e] bg-[#22c55e]/15 border border-[#22c55e]/30 px-2 py-0.5 rounded-sm">
          Yield Harvesting
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1e293b] text-[#94a3b8]">
              <th className="text-left px-4 py-2.5 font-medium">CONTRACT</th>
              <th className="text-right px-4 py-2.5 font-medium">QTY</th>
              <th className="text-right px-4 py-2.5 font-medium">PREMIUM</th>
              <th className="text-right px-4 py-2.5 font-medium">DTE</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-[#1e293b] last:border-0 hover:bg-[#1e293b]/40 transition-colors">
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center rounded border border-[#334155] px-1.5 py-0.5 text-[10px] text-[#cbd5e1]">CC</span>
                  <span className="font-mono text-white">SPY 520c 15Mar24</span>
                </div>
              </td>
              <td className="px-4 py-3 text-right font-mono text-[#f8fafc] tabular-nums">-1</td>
              <td className="px-4 py-3 text-right font-mono text-[#f8fafc] tabular-nums">$125.00</td>
              <td className="px-4 py-3 text-right text-[#f8fafc] tabular-nums">3</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
