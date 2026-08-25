'use client'

import { useEffect, useRef } from 'react'
import { usePathname } from 'next/navigation'
import Link from 'next/link'
import {
  LayoutGrid,
  Wallet,
  Terminal,
  Settings,
  Rocket,
  BookOpen,
  LifeBuoy,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const nav = [
  { name: 'Dashboard', icon: LayoutGrid, href: '/dashboard' },
  { name: 'Assets', icon: Wallet, href: '/assets' },
  { name: 'Terminal', icon: Terminal, href: '/terminal' },
  { name: 'Settings', icon: Settings, href: '/settings' },
]

export default function Sidebar() {
  const pathname = usePathname()
  const drawerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') document.body.click()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [])

  const handleLinkClick = () => {
    document.body.click()
  }

  return (
    <aside
      ref={drawerRef}
      className="fixed inset-y-0 left-0 z-50 hidden lg:flex w-[240px] bg-[#0f172a] border-r border-[#1e293b] flex-col"
    >
      <div className="flex h-14 items-center gap-2 px-4 border-b border-[#1e293b]">
        <div className="flex h-8 w-8 items-center justify-center rounded bg-[#22c55e]/20">
          <Rocket className="h-5 w-5 text-[#22c55e]" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-[#22c55e] leading-tight">AutoOverlay</span>
          <span className="text-[10px] text-[#94a3b8] uppercase tracking-widest">AI Engine Active</span>
        </div>
      </div>

      <nav className="flex-1 p-2 space-y-1">
        {nav.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'sidebar-nav-item relative flex items-center gap-2',
                isActive && 'bg-[#2d3449] text-[#22c55e]'
              )}
              aria-current={isActive ? 'page' : undefined}
            >
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-[#22c55e] rounded-full" />
              )}
              <item.icon className="h-4 w-4" />
              {item.name}
            </Link>
          )
        })}
      </nav>

      <div className="p-2 space-y-1 border-t border-[#1e293b]">
        <button className="sidebar-nav-item">
          <BookOpen className="h-4 w-4" />
          Docs
        </button>
        <button className="sidebar-nav-item">
          <LifeBuoy className="h-4 w-4" />
          Support
        </button>
        <button className="btn-primary w-full flex items-center justify-center gap-2 mt-2">
          <Rocket className="h-4 w-4" />
          Deploy Logic
        </button>
      </div>

      <div className="p-4 border-t border-[#1e293b]">
        <p className="text-[10px] text-[#64748b]">© 2024 AutoOverlay AI. Algorithmic Precision.</p>
      </div>
    </aside>
  )
}
