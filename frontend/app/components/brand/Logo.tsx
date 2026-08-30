'use client'

import Image from 'next/image'
import { motion, useReducedMotion, useEntranceReady, EASE } from '@/components/motion/primitives'

export function LogoMark({
  className = 'h-8 w-8',
  animate = true,
}: {
  className?: string
  animate?: boolean
}) {
  const reduce = useReducedMotion()
  const ready = useEntranceReady()
  const still = reduce || !animate || !ready

  return (
    <span className={`relative inline-block overflow-hidden rounded-xl border border-[#1e293b] bg-[#0f172a] p-0.5 ${className}`}>
      <Image
        src="/logo.png"
        alt="AutoOverlay AI"
        fill
        priority
        className="object-cover w-full h-full"
      />
    </span>
  )
}

export function LogoLockup({
  subtitle,
  className = '',
  animate = true,
}: {
  subtitle?: string
  className?: string
  animate?: boolean
}) {
  const reduce = useReducedMotion()
  const ready = useEntranceReady()
  const still = reduce || !animate || !ready

  return (
    <span className={`flex items-center gap-2 ${className}`}>
      <LogoMark className="h-8 w-8 shrink-0" animate={animate} />
      <motion.span
        className="flex flex-col leading-tight"
        initial={still ? false : { opacity: 0, x: -4 }}
        animate={{ opacity: 1, x: 0 }}
        transition={still ? { duration: 0 } : { duration: 0.22, ease: EASE, delay: 0.3 }}
      >
        <span className="text-sm font-semibold text-[#22c55e]">AutoOverlay</span>
        {subtitle && (
          <span className="text-[10px] uppercase tracking-widest text-[#94a3b8]">{subtitle}</span>
        )}
      </motion.span>
    </span>
  )
}
