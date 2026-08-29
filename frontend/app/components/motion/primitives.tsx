'use client'

/**
 * Shared motion primitives.
 *
 * House rules for animation in this app:
 *  - Short. 150-260ms. Anything longer reads as lag in a trading UI.
 *  - Small travel. 4-10px. Big slides feel like a marketing site.
 *  - Ease out, never bounce. No spring overshoot on financial data.
 *  - Opacity + tiny transform only. Never animate layout-affecting properties.
 *  - Every primitive honours prefers-reduced-motion by collapsing to a plain
 *    opacity change (or nothing at all).
 *
 * Import these instead of hand-rolling variants per component, so timing stays
 * consistent across pages.
 */

import { motion, useReducedMotion, type Variants } from 'framer-motion'
import type { ComponentProps, ReactNode } from 'react'

/** Standard ease-out curve used everywhere. */
export const EASE = [0.22, 1, 0.36, 1] as const

export const DURATION = {
  fast: 0.16,
  base: 0.22,
  slow: 0.32,
} as const

/** Fade + tiny lift. The default entrance for cards and panels. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: DURATION.base, ease: EASE } },
  exit: { opacity: 0, y: -4, transition: { duration: DURATION.fast, ease: EASE } },
}

/** Fade only — for text and inline content where movement would be noise. */
export const fade: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: DURATION.base, ease: EASE } },
  exit: { opacity: 0, transition: { duration: DURATION.fast, ease: EASE } },
}

/** Rows sliding in from the left edge — list items, log lines. */
export const slideIn: Variants = {
  hidden: { opacity: 0, x: -6 },
  show: { opacity: 1, x: 0, transition: { duration: DURATION.base, ease: EASE } },
  exit: { opacity: 0, x: -4, transition: { duration: DURATION.fast, ease: EASE } },
}

/** Expand/collapse for reasoning traces and detail panels. */
export const collapse: Variants = {
  hidden: { opacity: 0, height: 0 },
  show: { opacity: 1, height: 'auto', transition: { duration: DURATION.base, ease: EASE } },
  exit: { opacity: 0, height: 0, transition: { duration: DURATION.fast, ease: EASE } },
}

/** Parent that staggers its children. Pair with fadeUp/slideIn on each child. */
export function staggerParent(stagger = 0.05, delayChildren = 0): Variants {
  return {
    hidden: {},
    show: { transition: { staggerChildren: stagger, delayChildren } },
  }
}

type DivProps = ComponentProps<typeof motion.div>

/**
 * Entrance wrapper. Renders a plain div when the user prefers reduced motion,
 * so nothing moves and nothing flashes.
 */
export function Reveal({
  children,
  variants = fadeUp,
  delay = 0,
  ...rest
}: { children: ReactNode; variants?: Variants; delay?: number } & Omit<DivProps, 'variants'>) {
  const reduce = useReducedMotion()
  if (reduce) return <div {...(rest as ComponentProps<'div'>)}>{children}</div>
  return (
    <motion.div
      initial="hidden"
      animate="show"
      exit="exit"
      variants={variants}
      transition={delay ? { delay } : undefined}
      {...rest}
    >
      {children}
    </motion.div>
  )
}

/** Stagger container. Children should use `variants={fadeUp}` (or slideIn). */
export function RevealGroup({
  children,
  stagger = 0.05,
  delayChildren = 0,
  ...rest
}: { children: ReactNode; stagger?: number; delayChildren?: number } & DivProps) {
  const reduce = useReducedMotion()
  if (reduce) return <div {...(rest as ComponentProps<'div'>)}>{children}</div>
  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={staggerParent(stagger, delayChildren)}
      {...rest}
    >
      {children}
    </motion.div>
  )
}

/** A child of RevealGroup. */
export function RevealItem({
  children,
  variants = fadeUp,
  ...rest
}: { children: ReactNode; variants?: Variants } & Omit<DivProps, 'variants'>) {
  const reduce = useReducedMotion()
  if (reduce) return <div {...(rest as ComponentProps<'div'>)}>{children}</div>
  return (
    <motion.div variants={variants} {...rest}>
      {children}
    </motion.div>
  )
}

/**
 * Press feedback for buttons. Scale only, 0.98 — enough to feel responsive,
 * small enough not to look like a toy.
 */
export const pressable = {
  whileHover: { scale: 1.01 },
  whileTap: { scale: 0.98 },
  transition: { duration: DURATION.fast, ease: EASE },
} as const

export { motion, useReducedMotion }
