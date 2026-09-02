'use client'

import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import TerminalClient from '@/components/terminal/TerminalClient'
import { RequireAuth } from '@/components/auth/RequireAuth'

export default function TerminalPage() {
  return (
    <RequireAuth>
      <div className="flex h-screen bg-[#020617] text-[#f8fafc] overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col min-w-0 lg:ml-[240px]">
          <Header />
          <main className="flex-1 overflow-hidden">
            <TerminalClient />
          </main>
        </div>
      </div>
    </RequireAuth>
  )
}
