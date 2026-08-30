'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import {
  LayoutGrid,
  Wallet,
  Terminal,
  Settings,
  Scale,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { LogoLockup } from '@/components/brand/Logo'
import { motion, useReducedMotion, EASE, DURATION } from '@/components/motion/primitives'

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

export default function Sidebar() {
  const pathname = usePathname()
  const reduce = useReducedMotion()

  return (
    <aside
      className="fixed inset-y-0 left-0 z-50 hidden lg:flex w-[240px] bg-[#0f172a] border-r border-[#1e293b] flex-col"
    >
      <div className="flex h-14 items-center gap-2 px-4 border-b border-[#1e293b]">
        <LogoLockup subtitle="AI Engine Active" />
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
                <motion.span
                  layoutId="sidebar-active-marker"
                  className="absolute left-0 top-1/2 w-[3px] h-5 bg-[#22c55e] rounded-full"
                  style={{ translateY: '-50%' }}
                  transition={reduce ? { duration: 0 } : { duration: DURATION.base, ease: EASE }}
                />
              )}
              <item.icon className="h-4 w-4" />
              {item.name}
            </Link>
          )
        })}
      </nav>

      <div className="p-4 border-t border-[#1e293b]">
        <p className="text-[10px] text-[#64748b]">© 2024 AutoOverlay AI. Algorithmic Precision.</p>
      </div>
    </aside>
  )
}
