'use client'

export interface HistoryRow {
  date: string
  action: string
  ticker: string
  status: string
  pnl: string
  pnlColor: string
}

interface RecentHistoryProps {
  rows: HistoryRow[]
}

export default function RecentHistory({ rows }: RecentHistoryProps) {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1e293b]">
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Recent History</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1e293b] text-[#94a3b8]">
              <th className="text-left px-4 py-2.5 font-medium">Date</th>
              <th className="text-left px-4 py-2.5 font-medium">Action</th>
              <th className="text-left px-4 py-2.5 font-medium">Ticker</th>
              <th className="text-left px-4 py-2.5 font-medium">Status</th>
              <th className="text-right px-4 py-2.5 font-medium">Realized P&L</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.date + row.ticker} className="border-b border-[#1e293b] last:border-0 hover:bg-[#1e293b]/40 transition-colors">
                <td className="px-4 py-3 text-[#f8fafc]">{row.date}</td>
                <td className="px-4 py-3 text-[#f8fafc]">{row.action}</td>
                <td className="px-4 py-3 text-[#f8fafc]">{row.ticker}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center rounded border border-[#334155] px-2 py-0.5 text-xs text-[#cbd5e1]">
                    {row.status}
                  </span>
                </td>
                <td className={`px-4 py-3 text-right font-mono ${row.pnlColor}`}>
                  {row.pnl.startsWith('+') ? '+' : ''}{row.pnl}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
