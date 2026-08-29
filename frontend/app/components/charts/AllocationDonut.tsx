'use client'

import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'

/**
 * Allocation donut with the legend outside the ring — percentages next to names
 * are readable; percentages crammed onto slices are not.
 *
 * Muted slate ramp with one emerald accent for the largest holding, so
 * concentration is the thing your eye lands on.
 */
const RAMP = ['#22c55e', '#475569', '#64748b', '#94a3b8', '#cbd5e1', '#334155']

export interface AllocationSlice {
  name: string
  value: number
}

export default function AllocationDonut({
  slices,
  size = 132,
}: {
  slices: AllocationSlice[]
  size?: number
}) {
  const clean = slices
    .filter((s) => Number.isFinite(s.value) && s.value > 0)
    .sort((a, b) => b.value - a.value)

  if (clean.length === 0) {
    return <p className="text-xs text-[#64748b]">No positions to allocate.</p>
  }

  const total = clean.reduce((sum, s) => sum + s.value, 0)

  return (
    <div className="flex flex-wrap items-center gap-4">
      <div style={{ width: size, height: size }} className="shrink-0" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={clean}
              dataKey="value"
              nameKey="name"
              innerRadius="62%"
              outerRadius="100%"
              paddingAngle={1.5}
              stroke="#0f172a"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {clean.map((s, i) => (
                <Cell key={s.name} fill={RAMP[i % RAMP.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>

      <ul className="min-w-0 flex-1 space-y-1">
        {clean.map((s, i) => {
          const pct = (s.value / total) * 100
          return (
            <li key={s.name} className="flex items-center gap-2 text-xs">
              <span
                className="h-2 w-2 shrink-0 rounded-sm"
                style={{ background: RAMP[i % RAMP.length] }}
              />
              <span className="truncate text-[#e2e8f0]">{s.name}</span>
              <span className="ml-auto shrink-0 tabular-nums text-[#94a3b8]">
                {pct.toFixed(1)}%
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
