'use client'

import { Area, AreaChart, ResponsiveContainer, YAxis } from 'recharts'

/**
 * Minimal equity sparkline. No axes, no grid, no tooltip — a shape, not a chart.
 * Single colour keyed to direction: emerald when the series ends above where it
 * started, red when below.
 *
 * `series` is oldest-first. Fewer than two points renders nothing rather than a
 * misleading flat line.
 */
export default function EquitySparkline({
  series,
  height = 48,
}: {
  series: number[]
  height?: number
}) {
  const clean = series.filter((v) => Number.isFinite(v))
  if (clean.length < 2) return null

  const first = clean[0]
  const last = clean[clean.length - 1]
  const up = last >= first
  const colour = up ? '#22c55e' : '#ef4444'

  const data = clean.map((v, i) => ({ i, v }))
  const min = Math.min(...clean)
  const max = Math.max(...clean)
  // Pad the domain so a small move does not fill the whole box and look dramatic.
  const pad = (max - min) * 0.15 || Math.abs(max) * 0.01 || 1

  return (
    <div style={{ height }} aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`spark-${up ? 'up' : 'down'}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colour} stopOpacity={0.22} />
              <stop offset="100%" stopColor={colour} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis domain={[min - pad, max + pad]} hide />
          <Area
            type="monotone"
            dataKey="v"
            stroke={colour}
            strokeWidth={1.75}
            fill={`url(#spark-${up ? 'up' : 'down'})`}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
