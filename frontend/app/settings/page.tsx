'use client'

import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import AgentConfiguration from '@/components/AgentConfiguration'
import StrategyConfigCard from '@/components/StrategyConfigCard'

export default function SettingsPage() {
  return (
    <div className="flex h-screen bg-[#020617] text-[#f8fafc] overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col min-w-0 lg:ml-[240px]">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <div className="space-y-4 px-6 pt-6 pb-6">
            <StrategyConfigCard />
            <AgentConfiguration />
          </div>
        </main>
      </div>
    </div>
  )
}
