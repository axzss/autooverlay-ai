'use client'

import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import MetricCard from '@/components/MetricCard'
import UnderlyingAssets from '@/components/UnderlyingAssets'
import ActiveOverlayContracts from '@/components/ActiveOverlayContracts'
import AgentControl from '@/components/AgentControl'
import ThoughtProcess from '@/components/ThoughtProcess'
import { usePortfolio } from '../../lib/api'

const usd = (v: string | number) =>
  Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function DashboardPage() {
  const { data, error, loading, usingFallback } = usePortfolio()

  const account = data?.account_info
  const positions = data?.positions ?? []
  const lastEquity = Number(account?.last_equity ?? 0)
  const equity = Number(account?.equity ?? 0)
  const dailyPnl = equity - lastEquity
  const dailyPnlLabel =
    account && dailyPnl !== 0 ? `${dailyPnl > 0 ? '+' : '-'}$${usd(Math.abs(dailyPnl))}` : null

  return (
    <div className="flex h-screen bg-[#020617] text-[#f8fafc] overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <div className="px-4 sm:px-6 pt-6 pb-2">
            <h1 className="text-lg font-semibold text-white">Dashboard</h1>
            <p className="text-sm text-[#94a3b8]">Real-time portfolio and agent overview.</p>
            {usingFallback && (
              <p className="mt-2 inline-flex items-center rounded border border-[#b45309]/40 bg-[#451a03] px-2 py-0.5 text-xs text-[#fbbf24]">
                Backend unreachable — showing sample data{error ? ` (${error})` : ''}
              </p>
            )}
          </div>
          <div className="px-4 sm:px-6 pb-6 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <MetricCard label="TOTAL VALUE" value={account && !loading ? `$${usd(account.portfolio_value)}` : '—'} />
              <MetricCard label="DAILY P&L" value={dailyPnlLabel ?? (loading ? '—' : '$0.00')} accent={(dailyPnl ?? 0) >= 0} />
              <MetricCard label="BUYING POWER" value={account && !loading ? `$${usd(account.cash)}` : '—'} />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 space-y-4">
                <UnderlyingAssets positions={positions} />
                <ActiveOverlayContracts />
              </div>
              <div className="space-y-4">
                <AgentControl />
                <ThoughtProcess />
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
