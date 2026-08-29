'use client'

/**
 * Concentric ring gauge for a 0-100 score. Pure SVG, no chart library needed —
 * recharts has no radial gauge worth the bundle cost for this.
 *
 * Colour bands match riskBadgeClasses in lib/api.ts so a score reads the same
 * everywhere: emerald >= 60, amber >= 40, red below.
 */
export default function ScoreGauge({
  score,
  size = 64,
  label,
}: {
  score: number
  size?: number
  label?: string
}) {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(score) ? score : 0))
  const stroke = size >= 56 ? 5 : 4
  const r = (size - stroke) / 2
  const circumference = 2 * Math.PI * r
  const filled = (clamped / 100) * circumference

  const colour = clamped >= 60 ? '#22c55e' : clamped >= 40 ? '#f59e0b' : '#ef4444'

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#1e293b"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={colour}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference - filled}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="font-semibold tabular-nums leading-none"
          style={{ color: colour, fontSize: size >= 56 ? 16 : 13 }}
        >
          {clamped.toFixed(1)}
        </span>
        {label && (
          <span className="mt-0.5 text-[8px] uppercase tracking-wider text-[#64748b]">{label}</span>
        )}
      </div>
      <span className="sr-only">
        {label ?? 'Score'}: {clamped.toFixed(1)} out of 100
      </span>
    </div>
  )
}
