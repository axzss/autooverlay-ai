'use client'

import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import PortfolioStats from '@/components/PortfolioStats'
import AssetHoldings from '@/components/AssetHoldings'
import RecentHistory from '@/components/RecentHistory'
import { Reveal, RevealGroup, RevealItem } from '@/components/motion/primitives'
import { usePortfolio } from '../../lib/api'
import type { Position } from '@/types/portfolio'

const FALLBACK_ACCOUNT = {
  portfolio_value: '105250.00',
  equity: '105250.00',
  last_equity: '105250.00',
  cash: '105250.00',
}

const FALLBACK_POSITIONS: Position[] = [
  {
    asset_id: '1',
    symbol: 'SPY',
    name: 'SPDR S&P 500 ETF',
    qty: '100',
    avg_entry_price: '500.00',
    market_value: '51245.00',
    cost_basis: '50000.00',
    unrealized_pl: '1245.00',
    unrealized_plpc: '0.02490',
    change_today: '0.00512',
    asset_class: 'equity',
    exchange: 'NYSE ARCA',
    id: '1',
    },
  {
    asset_id: '2',
    symbol: 'QQQ',
    name: 'Invesco QQQ Trust',
    qty: '50',
    avg_entry_price: '420.50',
    market_value: '21755.00',
    cost_basis: '21025.00',
    unrealized_pl: '730.00',
    unrealized_plpc: '0.03470',
    change_today: '0.00980',
    asset_class: 'equity',
    exchange: 'NASDAQ',
    id: '2',
    },
    ]

export default function AssetsPage() {
  const { data, error, usingFallback } = usePortfolio()

  const accountInfo = data?.account_info ?? FALLBACK_ACCOUNT
  const positions = data?.positions ?? FALLBACK_POSITIONS
  const history = (data?.orders ?? []).slice(0, 10).map((o) => ({
    date: (o.filled_at || o.submitted_at || o.created_at || '').slice(0, 10),
    action: o.side === 'buy' ? 'Buy' : 'Sell to Open',
    ticker: `${o.symbol} ${o.type === 'limit' ? `@ ${o.limit_price}` : 'MKT'}`,
    status: o.status,
    pnl: '',
    pnlColor: 'text-[#94a3b8]',
  }))

  return (
    <div className="flex h-screen bg-[#020617] text-[#f8fafc] overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col min-w-0 lg:ml-[240px]">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <div className="px-4 sm:px-6 pt-6 pb-2">
            <h1 className="text-lg font-semibold text-white">Portfolio Assets &amp; History</h1>
            <p className="text-sm text-[#94a3b8]">Detailed view of your holdings and past options overlays.</p>
            {usingFallback && (
              <p className="mt-2 inline-flex items-center rounded border border-[#b45309]/40 bg-[#451a03] px-2 py-0.5 text-xs text-[#fbbf24]">
                Backend unreachable — showing sample data{error ? ` (${error})` : ''}
              </p>
            )}
          </div>
          <div className="px-4 sm:px-6 pb-6 space-y-4">
            <RevealGroup className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <RevealItem>
                <PortfolioStats accountInfo={accountInfo} positions={positions} />
              </RevealItem>
              <RevealItem>
                <AssetHoldings positions={positions} />
              </RevealItem>
            </RevealGroup>
            <Reveal delay={0.1}>
              <RecentHistory rows={history} />
            </Reveal>
          </div>
        </main>
      </div>
    </div>
  )
}
