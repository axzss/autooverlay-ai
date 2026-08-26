'use client'

import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import TerminalClient from '@/components/terminal/TerminalClient'

export default function TerminalPage() {
  return (
    <div className="flex h-screen bg-[#020617] text-[#f8fafc] overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-hidden">
          <TerminalClient />
        </main>
      </div>
    </div>
  )
}
