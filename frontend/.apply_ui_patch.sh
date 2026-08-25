#!/usr/bin/env bash
set -euo pipefail

F=/root/alpaca-overlay-agent-a2z/frontend/src

mkdir -p "$F/components" "$F/app" "$F/lib" "$F/styles" "$F/types" "$F/data"

cat > "$F/app/layout.tsx" <<'LAYOUT'
import { Inter } from 'next/font/google'
import { GeistSans } from 'geist/font/sans'
import Providers from '@/components/Providers'
import '@/styles/globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })
const geist = GeistSans

export const metadata = {
  title: 'Alpaca Overlay Agent',
  description: 'AI-driven income strategies on your existing portfolio',
}

const RootLayout = ({ children }: { children: React.ReactNode }) => (
  <html lang="en" className="dark">
    <body className={`${inter.variable} ${geist.variable} flex h-screen bg-[#0b1326] text-[#dae2fd] overflow-hidden font-sans`}>
      <Providers>{children}</Providers>
    </body>
  </html>
)

export default RootLayout
LAYOUT

cat > "$F/components/Sidebar.tsx" <<'SIDEBAR'
'use client'

import { useState } from 'react'
import {
  ChevronLeft,
  Menu,
  BarChart3,
  Shield,
  TrendingUp,
  Settings,
  Terminal,
  LogOut,
  Bot,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface SidebarProps {
  open: boolean
  onClose: () => void
}

export default function Sidebar({ open, onClose }: SidebarProps) {
  const [activeItem, setActiveItem] = useState('Dashboard')

  const menuItems = [
    { icon: BarChart3, label: 'Dashboard', href: '/' },
    { icon: Shield, label: 'Strategies', href: '/strategies' },
    { icon: TrendingUp, label: 'Portfolio', href: '/overlay' },
    { icon: Terminal, label: 'AI Terminal', href: '/terminal' },
    { icon: Settings, label: 'Settings', href: '/settings' },
  ]

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden" onClick={onClose} />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex h-full w-[240px] flex-col border-r bg-[#131b2e] transition-transform duration-300 ease-in-out lg:translate-x-0',
          'border-[#3c4a42]',
          open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        <div className="flex h-16 items-center justify-between px-4 border-b border-[#3c4a42]">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded bg-[#4edea3]/20">
              <Bot className="h-5 w-5 text-[#4edea3]" />
            </div>
            <span className="font-geist text-lg font-semibold text-[#dae2fd]">Overlay Agent</span>
          </div>
          <button onClick={onClose} className="rounded-sm p-1 text-[#dae2fd]/60 hover:bg-[#2d3449] lg:hidden">
            <ChevronLeft className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto py-4">
          <ul className="list-none space-y-1 px-2">
            {menuItems.map((item) => {
              const Icon = item.icon
              const isActive = activeItem === item.label
              return (
                <li key={item.label}>
                  <button
                    onClick={() => setActiveItem(item.label)}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-sm px-3 py-2 text-left text-sm transition-colors',
                      isActive ? 'bg-[#4edea3]/20 text-[#4edea3]' : 'text-[#dae2fd]/70 hover:bg-[#2d3449] hover:text-[#dae2fd]'
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    <span className="font-body">{item.label}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>

        <div className="border-t border-[#3c4a42] p-4">
          <button className="flex w-full items-center gap-3 rounded-sm px-3 py-2 text-left text-sm text-[#dae2fd]/70 hover:bg-[#2d3449] hover:text-[#dae2fd]">
            <LogOut className="h-4 w-4" />
            <span>Logout</span>
          </button>
        </div>
      </aside>
    </>
  )
}
SIDEBAR

cat > "$F/components/Header.tsx" <<'HEADER'
'use client'

import { useState } from 'react'
import { Bell, Search, Bot, Menu } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { AccountInfo } from '@/types/portfolio'

interface HeaderProps {
  onMenuClick: () => void
  portfolioData: { account_info: AccountInfo } | null
}

export default function Header({ onMenuClick, portfolioData }: HeaderProps) {
  const account = portfolioData?.account_info

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[#3c4a42] bg-[#0b1326] px-6">
      <div className="flex items-center gap-4">
        <button onClick={onMenuClick} className="rounded-sm p-2 text-[#dae2fd]/70 hover:bg-[#2d3449] lg:hidden">
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-3">
          <Bot className="h-5 w-5 text-[#4edea3]" />
          <h1 className="font-geist text-xl font-semibold text-[#dae2fd]">AI Overlay Dashboard</h1>
        </div>
      </div>

      <div className="hidden md:block flex-1 max-w-md px-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#dae2fd]/50" />
          <input
            type="text"
            placeholder="Search symbols..."
            className="w-full rounded-sm border border-[#3c4a42] bg-[#131b2e] px-4 py-2 text-sm text-[#dae2fd] placeholder:text-[#dae2fd]/40 focus:outline-none focus:ring-2 focus:ring-[#4edea3]"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button className="relative rounded-sm p-2 text-[#dae2fd]/70 hover:bg-[#2d3449]">
          <Bell className="h-5 w-5" />
          <Badge variant="destructive" className="absolute -top-1 -right-1 h-5 w-5 rounded-full p-0 text-xs">3</Badge>
        </button>

        {account && (
          <div className="hidden sm:flex items-center gap-2 rounded-sm bg-[#131b2e] px-3 py-2">
            <div className="flex flex-col items-end">
              <span className="font-mono text-sm font-medium text-[#dae2fd]">
                ${Number(account.portfolio_value).toLocaleString('en-US', { maximumFractionDigits: 2 })}
              </span>
              <span className="text-xs text-[#dae2fd]/60">Portfolio Value</span>
            </div>
            <div className="h-2 w-2 rounded-full bg-[#4edea3] animate-pulse" />
          </div>
        )}
      </div>
    </header>
  )
}
HEADER

cat > "$F/app/page.tsx" <<'PAGE'
'use client'

import { useEffect, useState } from 'react'
import { PortfolioData } from '@/types/portfolio'
import mockPortfolioData from '@/data/mock_portfolio.json'
import Dashboard from '@/components/Dashboard'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'

export default function Home() {
  const [portfolioData, setPortfolioData] = useState<PortfolioData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setTimeout(() => {
      setPortfolioData(mockPortfolioData as PortfolioData)
      setLoading(false)
    }, 500)
  }, [])

  const [sidebarOpen, setSidebarOpen] = useState(false)

  if (loading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#0b1326]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 animate-spin rounded-sm border-4 border-[#4edea3] border-t-transparent" />
          <p className="text-sm text-[#dae2fd]/70">Loading portfolio...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden bg-[#0b1326]">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex flex-1 flex-col min-w-0">
        <Header onMenuClick={() => setSidebarOpen(true)} portfolioData={portfolioData} />
        <main className="flex-1 overflow-y-auto">
          {portfolioData && <Dashboard data={portfolioData} />}
        </main>
      </div>
    </div>
  )
}
PAGE

echo '--- verification ---'
grep -n "flex h-screen bg-\[#0b1326\] text-\[#dae2fd\] overflow-hidden" "$F/app/layout.tsx" || true
grep -n "list-none\|w-\[240px\]\|h-full\|bg-\[#131b2e\]\|border-r border-\[#3c4a42\]\|hover:bg-\[#2d3449\]" "$F/components/Sidebar.tsx" || true
grep -n "h-16\|bg-\[#0b1326\]\|border-b border-\[#3c4a42\]" "$F/components/Header.tsx" || true
grep -n "flex-1 flex flex-col min-w-0\|overflow-y-auto" "$F/app/page.tsx" || true
