'use client'

import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import StrategyConfigCard from '@/components/StrategyConfigCard'

/**
 * Settings renders StrategyConfigCard only.
 *
 * AgentConfiguration used to sit below it: a second, unwired config panel whose
 * Save button called alert('Configuration saved successfully.') without sending
 * anything anywhere. Two config panels where only one persists is worse than one,
 * so it was removed. Every tunable it claimed to own (moneyness/delta, DTE) is
 * already editable in StrategyConfigCard against PUT /api/strategy/config.
 */
export default function SettingsPage() {
  return (
    <div className="flex h-screen bg-[#020617] text-[#f8fafc] overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col min-w-0 lg:ml-[240px]">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <div className="space-y-4 px-6 pt-6 pb-6">
            <div>
              <h1 className="text-lg font-semibold text-white">Settings</h1>
              <p className="text-sm text-[#94a3b8]">
                Live strategy parameters. Changes are persisted to the agent via
                the backend, not stored locally.
              </p>
            </div>
            <StrategyConfigCard />
          </div>
        </main>
      </div>
    </div>
  )
}
