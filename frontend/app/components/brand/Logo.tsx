'use client'

import { motion, useReducedMotion, EASE } from '@/components/motion/primitives'

/**
 * AutoOverlay AI brand mark.
 *
 * Concept: a flat portfolio baseline with two overlay layers stacked above it —
 * the product name rendered literally. Deliberately flat: no gradients, no glow,
 * no glassmorphism. Emerald accent on the active overlay, slate for structure.
 *
 * Motion: on mount each layer draws itself bottom-to-top via pathLength, so the
 * mark builds the way the product does — base position first, then overlays. One
 * pass only, no looping; a logo that animates forever is a distraction.
 */
export function LogoMark({
  className = 'h-8 w-8',
  animate = true,
}: {
  className?: string
  /** Set false for static contexts (favicons, print, dense tables). */
  animate?: boolean
}) {
  const reduce = useReducedMotion()
  const still = reduce || !animate

  /** Draw-on for one stroke. Static render keeps the full path visible. */
  const draw = (delay: number) =>
    still
      ? {}
      : {
          initial: { pathLength: 0, opacity: 0 },
          animate: { pathLength: 1, opacity: 1 },
          transition: { duration: 0.5, ease: EASE, delay },
        }

  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="AutoOverlay AI"
    >
      {/* enclosure */}
      <rect x="1" y="1" width="30" height="30" rx="7" fill="#0f172a" stroke="#1e293b" />

      {/* base layer — the underlying equity position, held flat */}
      <motion.path
        d="M6 23h20"
        stroke="#334155"
        strokeWidth="2"
        strokeLinecap="round"
        {...draw(0)}
      />

      {/* first overlay — premium collected, stepping up */}
      <motion.path
        d="M6 18.5h6l3-3h5l3 3h3"
        stroke="#64748b"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        {...draw(0.12)}
      />

      {/* second overlay — the active layer the agent manages */}
      <motion.path
        d="M6 12.5h4l3.5-4h5l3 4h4.5"
        stroke="#22c55e"
        strokeWidth="2.25"
        strokeLinecap="round"
        strokeLinejoin="round"
        {...draw(0.24)}
      />
    </svg>
  )
}

/** Mark plus wordmark, for headers and sidebars. */
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
  const still = reduce || !animate

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
