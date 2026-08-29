import { ImageResponse } from 'next/og'

export const alt = 'AutoOverlay AI — agentic options-income overlay'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

/**
 * Link-preview card. Flat, slate + one emerald accent, no gradients.
 *
 * Note for anyone editing this: Satori requires an explicit `display` on every
 * div that has more than one child, and it does not lay out <br/>. Each text
 * line is its own flex div for that reason.
 */
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          background: '#020617',
          padding: '72px 80px',
          fontFamily: 'sans-serif',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <svg width="72" height="72" viewBox="0 0 32 32" fill="none">
            <rect x="1" y="1" width="30" height="30" rx="7" fill="#0f172a" stroke="#1e293b" />
            <path d="M6 23h20" stroke="#334155" strokeWidth="2" strokeLinecap="round" />
            <path
              d="M6 18.5h6l3-3h5l3 3h3"
              stroke="#64748b"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M6 12.5h4l3.5-4h5l3 4h4.5"
              stroke="#22c55e"
              strokeWidth="2.25"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', fontSize: 44, fontWeight: 700, color: '#22c55e' }}>
              AutoOverlay AI
            </div>
            <div style={{ display: 'flex', fontSize: 20, color: '#94a3b8', letterSpacing: 2 }}>
              ALPACA HACKATHON · TRACK 04
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', fontSize: 52, fontWeight: 600, color: '#f8fafc' }}>
            Options income on the equity
          </div>
          <div style={{ display: 'flex', fontSize: 52, fontWeight: 600, color: '#f8fafc' }}>
            you already hold.
          </div>
          <div style={{ display: 'flex', fontSize: 26, color: '#94a3b8', marginTop: 8 }}>
            Six-persona investment council · Graham&apos;s seven defensive tests
          </div>
          <div style={{ display: 'flex', fontSize: 26, color: '#94a3b8' }}>
            Kill-switch first · No order submitted without approval
          </div>
        </div>

        <div style={{ display: 'flex', gap: 14 }}>
          {['6 personas', 'kill-switch', 'full reasoning traces', 'paper trading'].map((t) => (
            <div
              key={t}
              style={{
                display: 'flex',
                fontSize: 20,
                color: '#22c55e',
                border: '1px solid #14532d',
                background: '#052e16',
                borderRadius: 6,
                padding: '8px 16px',
              }}
            >
              {t}
            </div>
          ))}
        </div>
      </div>
    ),
    { ...size },
  )
}
