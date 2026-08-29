'use client'

import { Rocket, LayoutTemplate, User, Menu } from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'
import MobileSidebar from '@/components/MobileSidebar'
import { LogoMark } from '@/components/brand/Logo'

/**
 * Top bar: brand, status indicators, and profile actions only.
 * Primary navigation lives in the left Sidebar (desktop) and MobileSidebar
 * (below lg) — the header must not duplicate it.
 */
export default function Header() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[#1e293b] bg-[#020617] px-4 sm:px-6">
      <div className="flex items-center gap-4 sm:gap-6">
        <Link href="/dashboard" className="flex items-center gap-2">
          <LogoMark className="h-8 w-8" />
          <span className="font-semibold text-[#22c55e] text-sm leading-tight">AutoOverlay AI | Track 4</span>
        </Link>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <div className="hidden sm:flex items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-1.5 rounded-full border border-[#22c55e]/50 bg-[#0f172a] px-2.5 py-1">
            <span className="h-2 w-2 rounded-full bg-[#22c55e] animate-pulse" />
            <span className="text-[11px] font-medium text-[#22c55e] uppercase tracking-wider">VPS: ONLINE</span>
          </div>
          <div className="flex items-center gap-1.5 rounded-full border border-[#f59e0b]/50 bg-[#0f172a] px-2.5 py-1">
            <span className="h-2 w-2 rounded-full bg-[#f59e0b]" />
            <span className="text-[11px] font-medium text-[#f59e0b] uppercase tracking-wider">PAPER TRADING</span>
          </div>
        </div>

        <button
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation menu"
          className="lg:hidden rounded-full p-1.5 text-[#94a3b8] hover:bg-[#1e293b] hover:text-white transition-colors"
        >
          <Menu className="h-5 w-5" />
        </button>

        <button
          aria-label="Deploy"
          className="hidden sm:flex rounded-full p-1.5 text-[#94a3b8] hover:bg-[#1e293b] hover:text-white transition-colors"
        >
          <Rocket className="h-5 w-5" />
        </button>
        <button
          aria-label="Layout options"
          className="hidden sm:flex rounded-full p-1.5 text-[#94a3b8] hover:bg-[#1e293b] hover:text-white transition-colors"
        >
          <LayoutTemplate className="h-5 w-5" />
        </button>
        <button
          aria-label="User profile"
          className="hidden sm:flex rounded-full p-1.5 text-[#94a3b8] hover:bg-[#1e293b] hover:text-white transition-colors"
        >
          <User className="h-5 w-5" />
        </button>
      </div>

      <MobileSidebar open={mobileOpen} onClose={() => setMobileOpen(false)} />
    </header>
  )
}
