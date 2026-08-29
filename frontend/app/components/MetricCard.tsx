'use client'

import { AnimatePresence } from 'framer-motion'
import { motion, useReducedMotion, EASE, DURATION } from '@/components/motion/primitives'

interface MetricCardProps {
  label: string
  value: string
  accent?: boolean
}

/**
 * The value crossfades when it changes, so a portfolio refresh reads as an
 * update rather than a silent swap. Keyed on `value` so AnimatePresence sees a
 * new node each time the number moves.
 */
export default function MetricCard({ label, value, accent }: MetricCardProps) {
  const reduce = useReducedMotion()

  return (
    <div className="card">
      <p className="text-xs font-medium text-[#94a3b8] uppercase tracking-wider">{label}</p>
      <div className="mt-2 h-8 overflow-hidden">
        <AnimatePresence mode="wait" initial={false}>
          <motion.p
            key={value}
            initial={reduce ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
            transition={reduce ? { duration: 0 } : { duration: DURATION.base, ease: EASE }}
            className={`text-2xl font-semibold tabular-nums leading-8 ${
              accent ? 'text-[#22c55e]' : 'text-white'
            }`}
          >
            {value}
          </motion.p>
        </AnimatePresence>
      </div>
    </div>
  )
}
