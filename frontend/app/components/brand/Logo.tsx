/**
 * AutoOverlay AI brand mark.
 *
 * Concept: a flat portfolio baseline with two overlay layers stacked above it —
 * the product name rendered literally. Deliberately flat: no gradients, no glow,
 * no glassmorphism. Emerald accent on the active overlay, slate for structure.
 */
export function LogoMark({ className = 'h-8 w-8' }: { className?: string }) {
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
      <path
        d="M6 23h20"
        stroke="#334155"
        strokeWidth="2"
        strokeLinecap="round"
      />

      {/* first overlay — premium collected, stepping up */}
      <path
        d="M6 18.5h6l3-3h5l3 3h3"
        stroke="#64748b"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* second overlay — the active layer the agent manages */}
      <path
        d="M6 12.5h4l3.5-4h5l3 4h4.5"
        stroke="#22c55e"
        strokeWidth="2.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** Mark plus wordmark, for headers and sidebars. */
export function LogoLockup({
  subtitle,
  className = '',
}: {
  subtitle?: string
  className?: string
}) {
  return (
    <span className={`flex items-center gap-2 ${className}`}>
      <LogoMark className="h-8 w-8 shrink-0" />
      <span className="flex flex-col leading-tight">
        <span className="text-sm font-semibold text-[#22c55e]">AutoOverlay</span>
        {subtitle && (
          <span className="text-[10px] uppercase tracking-widest text-[#94a3b8]">{subtitle}</span>
        )}
      </span>
    </span>
  )
}
