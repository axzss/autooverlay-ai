'use client'

import { useEffect, useState } from 'react'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import MetricCard from '@/components/MetricCard'
import UnderlyingAssets from '@/components/UnderlyingAssets'
import ActiveOverlayContracts from '@/components/ActiveOverlayContracts'
import AgentControl from '@/components/AgentControl'
import ThoughtProcess from '@/components/ThoughtProcess'
import AgentStatusCard from '@/components/dashboard/AgentStatusCard'
import {
  api,
  normalizeScreenings,
  type PortfolioContext,
} from '../../lib/api'
import { usePortfolio } from '../../lib/api'

const usd = (v: string | number) =>
  Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

function ContextChips({ ctx }: { ctx: PortfolioContext }) {
  const chips: { label: string; ok: boolean | null }[] = []
  if (typeof ctx.concentration_ok === 'boolean') {
    chips.push({ label: `Concentration ${ctx.concentration_ok ? 'OK' : 'ELEVATED'}`, ok: ctx.concentration_ok })
  }
  if (typeof ctx.cash_reserve_ok === 'boolean') {
    chips.push({ label: `Cash reserve ${ctx.cash_reserve_ok ? 'OK' : 'LOW'}`, ok: ctx.cash_reserve_ok })
  }
  if (chips.length === 0) return null
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {chips.map((chip) => (
        <span
          key={chip.label}
          className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs ${
            chip.ok
              ? 'border-[#22c55e]/50 bg-[#052e16] text-[#22c55e]'
              : 'border-[#f59e0b]/50 bg-[#451a03] text-[#fbbf24]'
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${chip.ok ? 'bg-[#22c55e]' : 'bg-[#f59e0b]'}`} />
          {chip.label}
        </span>
      ))}
    </div>
  )
}

export default function DashboardPage() {
  const { data, error, loading, usingFallback } = usePortfolio()
  const [portfolioContext, setPortfolioContext] = useState<PortfolioContext | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .screenStrategies()
      .then((res) => {
        if (!cancelled) setPortfolioContext(normalizeScreenings(res).portfolioContext)
      })
      .catch(() => {
        /* portfolio context is optional — ignore screen failures here */
      })
    return () => {
      cancelled = true
    }
  }, [])

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
            {portfolioContext && <ContextChips ctx={portfolioContext} />}
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
                <AgentStatusCard />
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
