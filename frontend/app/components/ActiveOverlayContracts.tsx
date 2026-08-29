'use client'

import { Layers } from 'lucide-react'
import type { Position } from '../types/portfolio'

/**
 * Open option overlay legs, read from real portfolio positions.
 *
 * Previously this table rendered a hardcoded "SPY 520c 15Mar24 / $125.00" row
 * that existed nowhere in the account. It now filters the live position list by
 * asset class and shows an empty state when no overlay is open — which is the
 * truthful answer most of the time.
 */

/** OCC symbol: ROOT(≤6) + YYMMDD + C|P + strike(8, thousandths). */
function parseOcc(symbol: string) {
  const m = /^([A-Z]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/.exec(symbol)
  if (!m) return null
  const [, root, yy, mm, dd, cp, strikeRaw] = m
  const expiry = new Date(Date.UTC(2000 + Number(yy), Number(mm) - 1, Number(dd)))
  const strike = Number(strikeRaw) / 1000
  const dte = Math.ceil((expiry.getTime() - Date.now()) / 86_400_000)
  return { root, cp, strike, expiry, dte }
}

const fmtDate = (d: Date) =>
  d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' }).replace(/ /g, '')

export default function ActiveOverlayContracts({ positions = [] }: { positions?: Position[] }) {
  const legs = positions.filter((p) => (p.asset_class ?? '').toLowerCase().includes('option'))

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e293b] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-[#22c55e]" />
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
            Active Overlay Contracts
          </h3>
        </div>
        <span className="text-[10px] font-medium uppercase tracking-wider text-[#94a3b8] border border-[#334155] px-2 py-0.5 rounded-sm">
          {legs.length} open
        </span>
      </div>

      {legs.length === 0 ? (
        <p className="px-4 py-6 text-center text-xs text-[#64748b]">
          No option overlay legs open. Short calls and puts appear here once the
          agent&apos;s recommendations are approved and filled.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e293b] text-[#94a3b8]">
                <th className="text-left px-4 py-2.5 font-medium">CONTRACT</th>
                <th className="text-right px-4 py-2.5 font-medium">QTY</th>
                <th className="text-right px-4 py-2.5 font-medium">MARKET VALUE</th>
                <th className="text-right px-4 py-2.5 font-medium">DTE</th>
              </tr>
            </thead>
            <tbody>
              {legs.map((leg) => {
                const occ = parseOcc(leg.symbol)
                const qty = Number(leg.qty)
                const mv = Number(leg.market_value)
                return (
                  <tr
                    key={leg.symbol}
                    className="border-b border-[#1e293b] last:border-0 hover:bg-[#1e293b]/40 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center rounded border border-[#334155] px-1.5 py-0.5 text-[10px] text-[#cbd5e1]">
                          {occ ? (occ.cp === 'C' ? 'CALL' : 'PUT') : 'OPT'}
                        </span>
                        <span className="font-mono text-white">
                          {occ
                            ? `${occ.root} ${occ.strike}${occ.cp.toLowerCase()} ${fmtDate(occ.expiry)}`
                            : leg.symbol}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-[#f8fafc]">
                      {Number.isFinite(qty) ? qty : '—'}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-[#f8fafc]">
                      {Number.isFinite(mv)
                        ? `$${Math.abs(mv).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                        : '—'}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-[#f8fafc]">
                      {occ ? occ.dte : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
