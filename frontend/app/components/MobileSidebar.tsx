'use client'

import { useEffect } from 'react'
import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { AnimatePresence } from 'framer-motion'
import {
  LayoutGrid,
  Wallet,
  Terminal,
  Settings,
  Scale,
  X,
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

interface MobileSidebarProps {
  open: boolean
  onClose: () => void
}

export default function MobileSidebar({ open, onClose }: MobileSidebarProps) {
  const pathname = usePathname()
  const reduce = useReducedMotion()

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

  // AnimatePresence needs to own the mount/unmount, so the early `if (!open)
  // return null` is gone — the drawer now animates out instead of vanishing.
  const panelTransition = reduce
    ? { duration: 0 }
    : { duration: DURATION.base, ease: EASE }

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <motion.div
            className="fixed inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduce ? 0 : DURATION.fast }}
          />
          <motion.div
            className="fixed inset-y-0 left-0 w-[240px] bg-[#0f172a] border-r border-[#1e293b] flex flex-col shadow-2xl"
            initial={{ x: reduce ? 0 : '-100%', opacity: reduce ? 0 : 1 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: reduce ? 0 : '-100%', opacity: reduce ? 0 : 1 }}
            transition={panelTransition}
          >
            <div className="flex h-14 items-center justify-between px-4 border-b border-[#1e293b]">
              <LogoLockup subtitle="AI Engine Active" />
              <button onClick={onClose} aria-label="Close navigation menu" className="p-1.5 text-[#94a3b8] hover:text-white hover:bg-[#1e293b] rounded-md transition-colors">
                <X className="h-5 w-5" />
              </button>
            </div>

            <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
              {nav.map((item, idx) => {
                const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
                return (
                  <motion.div
                    key={item.href}
                    initial={reduce ? false : { opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={
                      reduce
                        ? { duration: 0 }
                        : { duration: DURATION.base, ease: EASE, delay: 0.05 + idx * 0.035 }
                    }
                  >
                    <Link
                      href={item.href}
                      onClick={handleNavigate}
                      className={cn(
                        'flex items-center gap-2 px-3 py-2.5 rounded-md text-sm transition-colors',
                        isActive ? 'bg-[#2d3449] text-[#22c55e]' : 'text-[#94a3b8] hover:text-white hover:bg-[#1e293b]/50'
                      )}
                    >
                      {isActive && (
                        <motion.span
                          layoutId="mobile-nav-active"
                          className="w-[3px] h-5 bg-[#22c55e] rounded-full"
                        />
                      )}
                      <item.icon className="h-4 w-4" />
                      {item.name}
                    </Link>
                  </motion.div>
                )
              })}
            </nav>

            <div className="p-4 border-t border-[#1e293b]">
              <p className="text-[10px] text-[#64748b]">© 2024 AutoOverlay AI. Algorithmic Precision.</p>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
