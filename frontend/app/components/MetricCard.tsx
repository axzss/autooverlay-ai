'use client'

interface MetricCardProps {
  label: string
  value: string
  accent?: boolean
}

export default function MetricCard({ label, value, accent }: MetricCardProps) {
  return (
    <div className="card">
      <p className="text-xs font-medium text-[#94a3b8] uppercase tracking-wider">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${accent ? 'text-[#22c55e]' : 'text-white'}`}>{value}</p>
    </div>
  )
}
