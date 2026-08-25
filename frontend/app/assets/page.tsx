'use client'

import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import PortfolioStats from '@/components/PortfolioStats'
import AssetHoldings from '@/components/AssetHoldings'
import RecentHistory from '@/components/RecentHistory'

export default function AssetsPage() {
  const accountInfo = {
    portfolio_value: '105250.00',
    equity: '105250.00',
    last_equity: '105250.00',
    cash: '105250.00',
  }

  const positions = [
    {
      asset_id: '1',
      symbol: 'SPY',
      name: 'SPDR S&P 500 ETF',
      qty: '100',
      avg_entry_price: '500.00',
      market_value: '51245.00',
      cost_basis: '50000.00',
      unrealized_pl: '1245.00',
      asset_class: 'equity',
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
      asset_class: 'equity',
    },
  ]

  const history = [
    { date: '2026-08-20', action: 'Sell to Open', ticker: 'QQQ 480C', status: 'Expired OTM', pnl: '85.00', pnlColor: 'text-[#22c55e]' },
    { date: '2026-08-15', action: 'Buy to Close', ticker: 'SPY 540P', status: 'Closed', pnl: '-20.00', pnlColor: 'text-[#ef4444]' },
  ]

  return (
    <div className="flex h-screen bg-[#020617] text-[#f8fafc] overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <div className="px-4 sm:px-6 pt-6 pb-2">
            <h1 className="text-lg font-semibold text-white">Portfolio Assets & History</h1>
            <p className="text-sm text-[#94a3b8]">Detailed view of your holdings and past options overlays.</p>
          </div>
          <div className="px-4 sm:px-6 pb-6 space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <PortfolioStats accountInfo={accountInfo} />
              <AssetHoldings positions={positions} />
            </div>
            <RecentHistory rows={history} />
          </div>
        </main>
      </div>
    </div>
  )
}
