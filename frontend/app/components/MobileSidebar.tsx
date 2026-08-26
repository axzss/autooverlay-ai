'use client'

import { useEffect } from 'react'
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
  Scale,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const nav = [
  { name: 'Dashboard', icon: LayoutGrid, href: '/dashboard' },
  { name: 'Assets', icon: Wallet, href: '/assets' },
  { name: 'Terminal', icon: Terminal, href: '/terminal' },
  {
    name: 'Council',
    icon: Scale,
    href: '/council',
  },
  { name: 'Settings', icon: Settings, href: '/settings' },
]

interface MobileSidebarProps {
  open: boolean
  onClose: () => void
}

export default function MobileSidebar({ open, onClose }: MobileSidebarProps) {
  const pathname = usePathname()

  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  const handleNavigate = () => {
    onClose()
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed inset-y-0 left-0 w-[240px] bg-[#0f172a] border-r border-[#1e293b] flex flex-col shadow-2xl">
        <div className="flex h-14 items-center justify-between px-4 border-b border-[#1e293b]">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded bg-[#22c55e]/20">
              <Rocket className="h-5 w-5 text-[#22c55e]" />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-semibold text-[#22c55e] leading-tight">AutoOverlay</span>
              <span className="text-[10px] text-[#94a3b8] uppercase tracking-widest">AI Engine Active</span>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 text-[#94a3b8] hover:text-white hover:bg-[#1e293b] rounded-md transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
          {nav.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={handleNavigate}
                className={cn(
                  'flex items-center gap-2 px-3 py-2.5 rounded-md text-sm transition-colors',
                  isActive ? 'bg-[#2d3449] text-[#22c55e]' : 'text-[#94a3b8] hover:text-white hover:bg-[#1e293b]/50'
                )}
              >
                {isActive && (
                  <span className="w-[3px] h-5 bg-[#22c55e] rounded-full" />
                )}
                <item.icon className="h-4 w-4" />
                {item.name}
              </Link>
            )
          })}
        </nav>

        <div className="p-2 space-y-1 border-t border-[#1e293b]">
          <button className="sidebar-nav-item w-full">
            <BookOpen className="h-4 w-4" />
            Docs
          </button>
          <button className="sidebar-nav-item w-full">
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
      </div>
    </div>
  )
}
