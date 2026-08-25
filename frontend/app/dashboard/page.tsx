'use client'

import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import MetricCard from '@/components/MetricCard'
import UnderlyingAssets from '@/components/UnderlyingAssets'
import ActiveOverlayContracts from '@/components/ActiveOverlayContracts'
import AgentControl from '@/components/AgentControl'
import ThoughtProcess from '@/components/ThoughtProcess'

export default function DashboardPage() {
  return (
    <div className="flex h-screen bg-[#020617] text-[#f8fafc] overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <div className="px-4 sm:px-6 pt-6 pb-2">
            <h1 className="text-lg font-semibold text-white">Dashboard</h1>
            <p className="text-sm text-[#94a3b8]">Real-time portfolio and agent overview.</p>
          </div>
          <div className="px-4 sm:px-6 pb-6 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <MetricCard label="TOTAL VALUE" value="$105,250.00" />
              <MetricCard label="DAILY P&L" value="+$150.25" accent />
              <MetricCard label="BUYING POWER" value="$5,250.00" />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2 space-y-4">
                <UnderlyingAssets />
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
