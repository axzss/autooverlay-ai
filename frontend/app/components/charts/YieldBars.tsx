'use client'

/**
 * Horizontal yield comparison. Deliberately hand-rolled divs rather than a
 * recharts BarChart: at this size a chart library adds axes, margins and tooltips
 * that make comparison harder, not easier.
 *
 * Bars are scaled to the largest value in the set, so this shows relative
 * standing — the number beside each bar carries the absolute value.
 */
export interface YieldBar {
  label: string
  value: number
  /** Marks a bar as elevated-risk; renders amber instead of emerald. */
  flagged?: boolean
}

export default function YieldBars({ bars }: { bars: YieldBar[] }) {
  const clean = bars
    .filter((b) => Number.isFinite(b.value))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8)

  if (clean.length === 0) {
    return <p className="text-xs text-[#64748b]">No yield data to compare.</p>
  }

  const max = Math.max(...clean.map((b) => Math.abs(b.value))) || 1

  return (
    <ul className="space-y-1.5">
      {clean.map((b) => {
        const pct = (Math.abs(b.value) / max) * 100
        const colour = b.flagged ? '#f59e0b' : '#22c55e'
        return (
          <li key={b.label} className="flex items-center gap-2">
            <span className="w-14 shrink-0 truncate text-xs text-[#e2e8f0]">{b.label}</span>
            <span className="h-2 flex-1 overflow-hidden rounded-sm bg-[#1e293b]">
              <span
                className="block h-full rounded-sm"
                style={{ width: `${Math.max(pct, 2)}%`, background: colour }}
              />
            </span>
            <span
              className="w-16 shrink-0 text-right text-xs tabular-nums"
              style={{ color: colour }}
            >
              {b.value.toFixed(1)}%
            </span>
          </li>
        )
      })}
    </ul>
  )
}
