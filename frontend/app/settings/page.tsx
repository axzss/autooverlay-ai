'use client'

import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import StrategyConfigCard from '@/components/StrategyConfigCard'
import { Reveal } from '@/components/motion/primitives'
import { RequireAuth } from '@/components/auth/RequireAuth'

export default function SettingsPage() {
  return (
    <RequireAuth>
      <div className="flex h-screen bg-[#020617] text-[#f8fafc] overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col min-w-0 lg:ml-[240px]">
          <Header />
          <main className="flex-1 overflow-y-auto">
            <div className="space-y-4 px-6 pt-6 pb-6">
              <Reveal>
                <div>
                  <h1 className="text-lg font-semibold text-white">Settings</h1>
                  <p className="text-sm text-[#94a3b8]">
                    Live strategy parameters. Changes are persisted to the agent via
                    the backend, not stored locally.
                  </p>
                </div>
              </Reveal>
              <Reveal delay={0.06}>
                <StrategyConfigCard />
              </Reveal>
            </div>
          </main>
        </div>
      </div>
    </RequireAuth>
  )
}
