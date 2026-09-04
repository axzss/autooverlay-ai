# SPEC-F2 · Risk cockpit (`/risk`)

**Workstream:** F2 of `docs/BRIEF-FRONTEND-V2.md`
**Producer:** `docs/BRIEF-AGENT-V2.md` W3 — `PortfolioGreeks` (`agent/greeks.py`)
**Transport:** `GET /api/risk/greeks` — **REQUESTED, NOT BUILT.** Nothing in this
spec may ship a number that endpoint did not return.
**Governing rule:** `docs/FRONTEND.md` — *never render a number the backend did
not produce; an empty state is information, a plausible placeholder is a lie that
survives into the demo.*

Scope: new route `app/risk/page.tsx`, new component directory
`app/components/risk/`, new pure module `lib/risk/format.ts`, new pure module
`lib/risk/model.ts`, and a compact strip pinned to `/dashboard`.

Out of scope, do not touch: `backend/**`, `agent/**`, any existing chart under
`app/components/charts/` (they are reused as-is or a sibling is added).

Dependency budget: only what is already in `frontend/package.json` — `recharts`,
`framer-motion`, `lucide-react`, `@tanstack/react-query`, `@radix-ui/react-tabs`,
`@radix-ui/react-label`, `@radix-ui/react-slot`, `zod`, `react-hook-form`. No new
package, no chart library, no table library.

Colour budget: only these Tailwind tokens from `frontend/tailwind.config.js` —
`background` `#020617`, `surface` `#0f172a`, `surface-container` `#131c2e`,
`surface-container-high` `#1a2332`, `primary` `#22c55e`, `secondary` `#fbbf24`,
`error` `#ef4444`, `on-surface` `#f8fafc`, `on-surface-variant` `#94a3b8`,
`outline` `#334155`. Type scale: `label-caps` (11px / .05em), `body-sm`,
`headline-md`, `mono-code`.

---

## 1 · Payload contract

Derived field-for-field from W3's dataclass. W3's hard rule — *"missing greeks
must yield `None`, never `0.0`"* — means the wire type is nullable everywhere a
number appears. That nullability is the contract, not an edge case, so it is
encoded in the type rather than defended at each call site.

`lib/risk/types.ts`:

```ts
/** One greek family for one symbol. Every member nullable: W3 degrades to None. */
export interface SymbolGreeks {
  delta: number | null
  theta: number | null
  vega: number | null
  gamma: number | null
}

/**
 * Caps come from agent config (max_net_vega_pct_nav,
 * max_beta_weighted_delta_pct_nav, min_net_theta). A cap that is not configured
 * is absent or null — it is NOT zero, and the frontend never substitutes one.
 */
export interface RiskCaps {
  max_net_vega_pct_nav: number | null
  max_beta_weighted_delta_pct_nav: number | null
  min_net_theta: number | null
}

/** Severity is backend-assigned when present; unknown severities sort last. */
export type BreachSeverity = 'critical' | 'warning' | 'info'

export interface CapBreach {
  /** Raw string from PortfolioGreeks.breaches — always present, always shown. */
  message: string
  /** Which greek the breach names, when the backend parsed it out. */
  greek: 'delta' | 'theta' | 'vega' | 'gamma' | 'beta_weighted_delta' | null
  observed: number | null
  cap: number | null
  severity: BreachSeverity | null
}

export interface KillSwitchState {
  halted: boolean
  /** Free-text reasons, one per line, straight from the agent. */
  reasons: string[]
  /** What clears each reason, index-aligned with `reasons` when supplied. */
  clears: string[] | null
  halted_at: string | null
}

export interface PortfolioGreeksPayload {
  net_delta: number | null
  net_theta: number | null
  net_vega: number | null
  net_gamma: number | null
  beta_weighted_delta: number | null
  /** NAV is needed to evaluate the *_pct_nav caps client-side for display only. */
  nav: number | null
  per_symbol: Record<string, SymbolGreeks>
  breaches: CapBreach[]
  caps: RiskCaps
  kill_switch: KillSwitchState
  /** ISO-8601. Feeds freshness.ts; null means the backend did not stamp it. */
  as_of: string | null
}
```

A `zod` schema mirrors this one-for-one in `lib/risk/schema.ts` and is applied in
the query function. `zod` is already a dependency. The schema uses
`.nullable()` on every numeric, never `.default(0)`; a `.default(0)` anywhere in
this file is a spec violation and the test in §8 asserts against it.

```ts
import { z } from 'zod'

export const symbolGreeksSchema = z.object({
  delta: z.number().nullable(),
  theta: z.number().nullable(),
  vega: z.number().nullable(),
  gamma: z.number().nullable(),
})

export const riskCapsSchema = z.object({
  max_net_vega_pct_nav: z.number().nullable(),
  max_beta_weighted_delta_pct_nav: z.number().nullable(),
  min_net_theta: z.number().nullable(),
})
```

Missing keys are coerced to `null`, not to `0`: the schema wraps each numeric as
`z.number().nullable().catch(null)` at the payload boundary so a malformed or
absent field lands in the honest-unknown branch instead of throwing the whole
panel away.

### 1.1 · Numbered rendering requirements

**R1 — `null` renders as an em dash plus a reason.** A `null` numeric renders the
glyph `—` (U+2014) in `on-surface-variant` `#94a3b8`, accompanied by an
accessible reason string exposed both as `title` and as `aria-label` on the
element: `"not reported by backend"`. It is never `0`, never `0.00`, never
`"N/A"`, never `"-"` (hyphen), and never omitted from the layout — the slot stays
in place so the reader can see that a measurement is missing rather than absent
from the design.

**R2 — zero is a real value.** `0` renders as a formatted zero (`0.00`,
`$0.00`, `0.0%`) in the same colour as any other real value. Zero and `null`
must be visually and programmatically distinguishable at a glance and to a screen
reader. No code path may treat `0` with `!value`, `value || fallback`, or
`Number(value) || 0`.

**R3 — caps come from the payload.** No threshold is hardcoded in `app/**` or
`lib/**`. When a cap is `null`, the gauge draws no band and the cap label reads
`not configured`. A missing cap never becomes an unbounded green.

**R4 — breach state is textual as well as chromatic.** Every breached element
carries a text badge (§6). Colour alone never encodes breach.

**R5 — HALT is unmissable and disabling.** When `kill_switch.halted` is true, the
full-width banner renders above everything else on `/risk` and on `/dashboard`,
and every "run agent" affordance app-wide is `disabled` with
`aria-disabled="true"` and an explanatory `title`.

**R6 — endpoint absence is a first-class state.** A `404` from
`/api/risk/greeks` renders the "risk engine not deployed" empty state, not an
error toast and not a zeroed cockpit (§7).

**R7 — no client-side arithmetic is presented as a reading.** Any number the
frontend computes (a percentage of NAV, a projection) is labelled as derived and
names its inputs. See §4.

---

## 2 · Components

All five live under `app/components/risk/`. All are `'use client'`. All accept
data as props — none fetches. `app/risk/page.tsx` owns the single
`useRiskQuery()` call from F1's `lib/live/hooks.ts` and passes slices down, so
every panel is directly renderable from a fixture in a unit test.

Shared status type, `lib/risk/types.ts`:

```ts
export type PanelStatus =
  | { kind: 'loading' }
  | { kind: 'not-deployed' }               // 404 from /api/risk/greeks
  | { kind: 'error'; message: string }     // 5xx, timeout, unreachable, parse fail
  | { kind: 'ready'; data: PortfolioGreeksPayload }
```

`not-deployed` is deliberately not folded into `error`: an endpoint that does not
exist yet is a build state, an endpoint that failed is an incident, and the two
read differently to a judge.

### 2.1 · `GreeksCockpit`

```ts
import type { PanelStatus, RiskCaps } from '@/../lib/risk/types'

export interface GreeksCockpitProps {
  status: PanelStatus
  /** Optional: force a single-column stack regardless of viewport (dashboard strip). */
  dense?: boolean
}

/** Internal, one per gauge. Exported for the unit tests. */
export interface GreekGaugeSpec {
  key: 'net_delta' | 'net_theta' | 'net_vega' | 'net_gamma'
  label: 'NET DELTA' | 'NET THETA' | 'NET VEGA' | 'NET GAMMA'
  unit: 'shares' | '$/day' | '$ / vol pt' | 'Δ per $1'
  value: number | null
  /** Absolute cap in the same unit as `value`, or null when not configured. */
  cap: number | null
  /** Direction the cap bites: 'max' breaches above, 'min' breaches below. */
  bound: 'max' | 'min' | null
  breached: boolean
}
```

**Chart reuse.** `ScoreGauge.tsx` is **not** reused. It is hardcoded to a 0–100
domain (`Math.min(100, score)`), it clamps a non-finite input to `0` — which is
exactly the `null → 0` lie R1/R2 forbid — and its colour bands are score-semantics
(`>= 60` green) rather than cap-semantics. A new sibling
`app/components/charts/CapGauge.tsx` is required. It is the same technique
(pure SVG arc + `framer-motion` sweep + `useReducedMotion`, no recharts, matching
ScoreGauge's stated rationale that "recharts has no radial gauge worth the bundle
cost"), with four differences: the domain is `[0, cap]` supplied per-instance; a
`null` value renders the track only and prints `—`; a `null` cap renders the value
with no arc fill and the caption `not configured`; and the arc turns
`error` `#ef4444` only when `breached` is true, never as a function of magnitude.

**States.**

| State | Rendering |
|---|---|
| loading | Four `animate-pulse` blocks, `surface-container-high` `#1a2332`, at the exact gauge footprint so nothing reflows on arrival. `aria-busy="true"`, `role="status"`, sr-only text `"Loading portfolio greeks"`. |
| not-deployed | Single centred card, `surface-container` `#131c2e`, `outline` `#334155` border, `lucide-react` `Unplug` icon, heading `label-caps` "RISK ENGINE NOT DEPLOYED", body-sm `"GET /api/risk/greeks returned 404. No greeks to display."` No gauges drawn — an empty gauge ring reads as zero. |
| empty | Payload parsed but all four nets `null`: gauges render with track + `—` + reason. This is the honest-ignorance render, not the empty state. |
| error | Same card shell as not-deployed with `error` `#ef4444` left border, `AlertTriangle` icon, the message verbatim, and a `Retry` button wired to the query's `refetch`. |
| partial-null | Per-gauge. A `null` gauge shows track + `—` + `aria-label="Net vega: not reported by backend"`; its siblings render normally. Mixed states in one row are expected and must not be normalised. |
| breach | The breached gauge's arc and value switch to `error` `#ef4444` **and** a text badge `BREACH` (§6) renders under the label. Non-breached siblings are unchanged. |
| halted | `GreeksCockpit` itself does not change; the halt banner sits above it. The cockpit is still the truth about exposure while halted and must keep rendering. |

**Layout.** At 1440px: a 4-column grid, `gap-gutter` (16px), each cell a
`surface-container` `#131c2e` card with an 88px gauge left and label/value/cap
stacked right. At 390px: single column, four stacked cards, gauge shrinks to 64px,
`headline-md` value drops to `body-sm`. `dense` forces the 390px layout at any
width.

### 2.2 · `BetaWeightedDelta`

```ts
export interface BetaWeightedDeltaProps {
  value: number | null              // payload.beta_weighted_delta
  nav: number | null                // payload.nav
  capPctNav: number | null          // payload.caps.max_beta_weighted_delta_pct_nav
  status: PanelStatus['kind']
}
```

**Chart reuse.** Reuses the new `CapGauge` from §2.1 at 120px plus a horizontal
cap-band rail. No recharts. `EquitySparkline` is not applicable — a single scalar
has no series, and drawing one point as a line implies history the payload does
not contain.

The absolute cap displayed is `nav * capPctNav / 100`, which is **derived**, so per
R7 the rail label reads `cap 8.0% NAV = $24,000 (derived from NAV)` and collapses
to `cap 8.0% NAV (NAV not reported)` when `nav` is `null`. The gauge value itself
is always the raw backend `beta_weighted_delta`, never a recomputation.

**States.** loading → single pulse block at 120px. not-deployed → hidden entirely;
the cockpit's not-deployed card covers the page. error → inline `body-sm` error row
in `error` `#ef4444`. partial-null (`value === null`) → `—` + reason, rail drawn in
`outline` `#334155` with no marker. partial-null (`capPctNav === null`) → value
rendered, rail replaced by the text `cap not configured` in
`on-surface-variant` `#94a3b8`. breach → marker and value in `error` `#ef4444`
plus `BREACH` badge and the sr-only sentence
`"Beta-weighted delta 1,240 exceeds cap 8.0 percent of NAV"`. halted → unchanged.

**Layout.** 1440px: 2-column card spanning half the grid — gauge left, rail and
labels right. 390px: gauge above, rail full-width beneath, labels wrap to two
lines.

### 2.3 · `ExposureMatrix`

```ts
export type GreekColumn = 'delta' | 'theta' | 'vega' | 'gamma'
export type SortDir = 'asc' | 'desc'

export interface ExposureMatrixProps {
  perSymbol: Record<string, SymbolGreeks>
  /** Symbols named by any breach, used to mark rows/cells. */
  breachedCells: ReadonlyArray<{ symbol: string; greek: GreekColumn }>
  status: PanelStatus['kind']
  initialSort?: { column: GreekColumn | 'symbol'; dir: SortDir }
}
```

**Chart reuse.** None — this is a semantic `<table>`, hand-rolled. No table
dependency exists in `package.json` and none is added. `recharts` is wrong for
tabular data and would destroy the screen-reader semantics §6 requires.

Sorting: `null` always sorts last regardless of direction, so a column of unknowns
never masquerades as the smallest exposure. Sort is client-side over the supplied
object and is presentational only — it never mutates or recomputes values.

**States.** loading → six skeleton rows, `surface-container-high` `#1a2332`.
empty (`perSymbol` has no keys) → single full-width row, `body-sm`,
`"No per-symbol greeks reported."` not-deployed → panel not rendered. error →
error row inside the table shell so the header still explains what is missing.
partial-null → per-cell `—` + `aria-label`; a row may be entirely `—` and still
lists its symbol. breach → the cell gets `error` `#ef4444` text, a 1px
`#ef4444` ring, and an inline `BREACH` badge; the row's symbol cell gets
`aria-describedby` pointing at the badge. halted → unchanged.

**Layout.** 1440px: full-width table, sticky header, columns
`SYMBOL | Δ | Θ | V | Γ` right-aligned `mono-code`, `tabular-nums`,
zebra via `surface` `#0f172a` / `surface-container` `#131c2e`. 390px: the table
becomes one card per symbol — symbol as `label-caps` heading, four
label/value rows inside — because a 5-column numeric table at 390px is
unreadable and horizontal scroll hides breaches off-screen.

### 2.4 · `CapBreachList`

```ts
export interface CapBreachListProps {
  breaches: CapBreach[]
  caps: RiskCaps
  status: PanelStatus['kind']
}
```

**Chart reuse.** None — an ordered list. `lucide-react` supplies `AlertOctagon`
(critical), `AlertTriangle` (warning), `Info` (info).

Order: `critical` → `warning` → `info` → `severity === null`, stable within a
band by payload order. A `null` severity is rendered with the neutral `Info` icon
and the badge text `UNCLASSIFIED`, never silently promoted or demoted.

**States.** loading → three skeleton rows. empty (`breaches.length === 0`) →
`primary` `#22c55e` check row, `"No cap breaches reported."` This is a real
assertion from the backend and is allowed to be green. not-deployed → panel not
rendered; a "no breaches" green with no engine behind it would be the worst lie on
the page. error → error row. partial-null → a breach whose `observed` or `cap` is
`null` still renders its `message` verbatim with `—` for the missing numbers.
breach → the list's normal state. halted → the list renders under the halt banner
and each breach that is also a halt reason gets the suffix badge `HALT CAUSE`.

**Layout.** 1440px: right column, 1/3 width, vertical list, icon + message +
`observed vs cap` line. 390px: full width, message wraps, numbers move to a second
line.

### 2.5 · `KillSwitchPanel`

```ts
export interface KillSwitchPanelProps {
  killSwitch: KillSwitchState
  status: PanelStatus['kind']
  /** Rendered full-bleed above page content when true; inline card otherwise. */
  variant: 'banner' | 'card'
}
```

**Chart reuse.** None.

**States.** loading → nothing rendered (a flashing halt banner is worse than a
late one). not-deployed → nothing rendered; halt state is unknown, and R1's
discipline applies to booleans too — the page prints
`"Kill-switch state unknown (risk engine not deployed)"` in
`on-surface-variant` `#94a3b8` inside the cockpit's not-deployed card rather than
claiming "not halted". error → same unknown-state line with the error message.
empty / not halted (`halted === false`) → a one-line `primary` `#22c55e` chip
`"TRADING ENABLED"`. partial-null (`clears === null`) → reasons listed, and a
single line `"Clearing conditions not reported."` breach → irrelevant here; the
panel keys off `halted` only. halted → full-width banner, `error` `#ef4444` 2px
top border, `#1a2332` fill, `headline-md` `"TRADING HALTED"`, `Ban` icon,
`halted_at` formatted, every reason as its own list item with its `clears` string
beneath, and `role="alert"` so it is announced immediately.

**Layout.** 1440px banner: full-bleed above the page grid, 3-column reason list.
390px: same banner, single-column reasons, icon above heading.

**App-wide effect (R5).** `app/risk/page.tsx` publishes `halted` through the F1
query cache; `AgentControl` and every other "run agent" affordance reads
`useRiskQuery()` and sets `disabled` plus
`title="Agent halted — see /risk for reasons"`. If the risk query is in
`not-deployed`, controls stay **enabled** — an unbuilt endpoint must not brick the
demo — and that asymmetry is intentional and documented here.

---

## 3 · Formatters — `lib/risk/format.ts`

The point of this module is that the unknown case is a **return variant**, not a
string fallback. Callers cannot accidentally print an em dash in the same colour
as a real number, because the variant carries the styling decision with it.

```ts
/**
 * Every formatter returns this discriminated union. `kind: 'unknown'` is a
 * first-class result, not an error and not a fallback: `text` is already the
 * em dash, and `reason` is the accessible explanation R1 requires.
 */
export type Formatted =
  | { kind: 'value'; text: string; reason: null }
  | { kind: 'unknown'; text: '—'; reason: string }

export const UNKNOWN_REASON = 'not reported by backend' as const

/** The single construction site for the unknown variant. */
export function unknown(reason: string = UNKNOWN_REASON): Formatted {
  return { kind: 'unknown', text: '—', reason }
}

/**
 * Greeks. `digits` defaults to 2; delta uses 0 because share-equivalent delta in
 * hundredths is noise. Signed so a short book reads as short.
 */
export function formatGreek(
  value: number | null | undefined,
  opts?: { digits?: number; signed?: boolean },
): Formatted

/** Dollar amounts: net theta ($/day), net vega ($ per vol point), NAV. */
export function formatCurrency(
  value: number | null | undefined,
  opts?: { digits?: number; signed?: boolean },
): Formatted

/** Percentages already expressed as percent (8.5 → "8.5%"), not as ratios. */
export function formatPct(
  value: number | null | undefined,
  opts?: { digits?: number },
): Formatted

/**
 * The cap caption under a gauge. Distinguishes three worlds: a configured cap,
 * an unconfigured cap, and a cap whose absolute value cannot be derived because
 * NAV is missing.
 */
export function formatCapBand(
  capPctNav: number | null | undefined,
  nav: number | null | undefined,
  bound: 'max' | 'min',
): Formatted
```

Implementation rules, each individually testable:

1. The `null` branch is entered by `value === null || value === undefined ||
   !Number.isFinite(value)`. It is **never** entered by `value === 0`,
   `value === -0`, or `value === ''`-style coercion. `!value` is banned in this
   file and the grep check in §5 enforces it.
2. `Number.isFinite` guards `NaN` and `±Infinity` into `unknown` with the reason
   `'value not finite'` — a `NaN` is ignorance wearing a number's clothes.
3. `-0` normalises to `0` before formatting so a real flat book never prints
   `-0.00`.
4. Formatters never round a value into or out of a breach; the breach flag comes
   from the payload.

### 3.1 · Exact outputs

| Call | Result |
|---|---|
| `formatGreek(1240.5)` | `{ kind: 'value', text: '1,240.50', reason: null }` |
| `formatGreek(1240.5, { digits: 0, signed: true })` | `{ kind: 'value', text: '+1,241', reason: null }` |
| `formatGreek(-88.2, { signed: true })` | `{ kind: 'value', text: '-88.20', reason: null }` |
| `formatGreek(0)` | `{ kind: 'value', text: '0.00', reason: null }` |
| `formatGreek(0, { signed: true })` | `{ kind: 'value', text: '0.00', reason: null }` — signed zero prints no sign |
| `formatGreek(null)` | `{ kind: 'unknown', text: '—', reason: 'not reported by backend' }` |
| `formatGreek(NaN)` | `{ kind: 'unknown', text: '—', reason: 'value not finite' }` |
| `formatCurrency(412.8)` | `{ kind: 'value', text: '$412.80', reason: null }` |
| `formatCurrency(412.8, { signed: true })` | `{ kind: 'value', text: '+$412.80', reason: null }` |
| `formatCurrency(-1250)` | `{ kind: 'value', text: '-$1,250.00', reason: null }` |
| `formatCurrency(0)` | `{ kind: 'value', text: '$0.00', reason: null }` |
| `formatCurrency(null)` | `{ kind: 'unknown', text: '—', reason: 'not reported by backend' }` |
| `formatPct(8.5)` | `{ kind: 'value', text: '8.5%', reason: null }` |
| `formatPct(0)` | `{ kind: 'value', text: '0.0%', reason: null }` |
| `formatPct(null)` | `{ kind: 'unknown', text: '—', reason: 'not reported by backend' }` |
| `formatCapBand(8, 300000, 'max')` | `{ kind: 'value', text: 'max 8.0% NAV = $24,000.00 (derived from NAV)', reason: null }` |
| `formatCapBand(8, null, 'max')` | `{ kind: 'value', text: 'max 8.0% NAV (NAV not reported)', reason: null }` |
| `formatCapBand(0, 300000, 'max')` | `{ kind: 'value', text: 'max 0.0% NAV = $0.00 (derived from NAV)', reason: null }` — a zero cap is a real, very strict cap |
| `formatCapBand(null, 300000, 'max')` | `{ kind: 'unknown', text: '—', reason: 'cap not configured' }` |
| `formatCapBand(null, null, 'min')` | `{ kind: 'unknown', text: '—', reason: 'cap not configured' }` |

Zero and `null` differ in `kind`, in `text`, and in `reason`. There is no input
for which they produce the same object, which is the property §8 asserts.

### 3.2 · Render helper

One component consumes `Formatted` so the styling of the unknown case exists in
exactly one place — `app/components/risk/Num.tsx`:

```ts
export interface NumProps {
  formatted: Formatted
  /** Prefixed to the accessible label, e.g. 'Net vega'. */
  srLabel: string
  className?: string
  /** Breach styling is applied by the caller, never inferred from magnitude. */
  breached?: boolean
}
```

`kind: 'unknown'` renders `<span>` with text `—`,
`text-[#94a3b8]`, `title={formatted.reason}`, and
`aria-label={`${srLabel}: ${formatted.reason}`}`. `kind: 'value'` renders
`tabular-nums` in `on-surface` `#f8fafc`, or `error` `#ef4444` when `breached`,
with `aria-label={`${srLabel}: ${formatted.text}`}`. No other component in
`app/components/risk/` may emit a bare `—`.

---

## 4 · `ThetaLadder` — resolved: **KEEP, labelled as a projection**

**Decision: build it, and label it a projection with its assumptions printed on
the panel.** Justification: net theta is a single scalar and a judge's immediate
next question is "how much of that decays before expiry, and when does it stop?" —
a question the scalar cannot answer, which is why the ladder earns its place.
Cutting it would leave the most valuable thing the overlay actually does, harvest
time decay, represented by one number with no shape. The honesty rule forbids
rendering a number the backend did not produce *as a reading*, and the fix is not
deletion but disclosure: a projection that names its inputs, states its
assumptions, and is visually separated from measured panels is not a fabricated
reading, it is a stated model — the same standard W3's brief applies to synthetic
backtest data, which is shipped and labelled rather than suppressed. The failure
mode we are guarding against is a plausible number that *looks* measured, so the
whole requirement is to make it impossible to mistake this panel for one.

**R8 — ThetaLadder is a labelled projection.** The panel:

1. Carries a persistent header badge `PROJECTION — NOT BACKEND DATA` in
   `secondary` `#fbbf24` on `surface-container-high` `#1a2332`, `label-caps`,
   always visible, not a tooltip and not behind a hover.
2. Prints its assumptions verbatim beneath the chart, in `body-sm`
   `on-surface-variant` `#94a3b8`:
   - `"Assumes net theta of $X/day held constant."`
   - `"Assumes 21 trading sessions per month, no weekends or holidays."`
   - `"Ignores gamma, assignment, early close, roll, and IV change."`
   - `"Source: net_theta from GET /api/risk/greeks at <as_of>. Curve computed in the browser."`
3. Uses `secondary` `#fbbf24` for its series and never `primary` `#22c55e`, so it
   is chromatically distinct from every measured panel on the page.
4. Renders nothing but the not-deployed / unknown card when `net_theta` is `null`
   or `as_of` is `null`. A projection off an unknown base is pure invention.
5. Lives in `lib/risk/model.ts`, not in `lib/risk/format.ts`, so projection code
   can never be reached from a formatter.
6. Is excluded from the dashboard risk strip (§7). A projection has no place in a
   compact summary where the label cannot travel with it.

```ts
/** lib/risk/model.ts — CLIENT-SIDE MODEL. Nothing here is backend-reported. */
export interface ThetaProjectionAssumptions {
  readonly sessionsProjected: 30
  readonly sessionsPerMonth: 21
  readonly thetaHeldConstant: true
  readonly ignores: readonly ['gamma', 'assignment', 'early_close', 'roll', 'iv_change']
}

export interface ThetaLadderPoint {
  session: number          // 1..30
  dailyTheta: number       // held constant, = netTheta
  cumulative: number       // session * netTheta
}

export interface ThetaProjection {
  kind: 'projection'
  points: ThetaLadderPoint[]
  assumptions: ThetaProjectionAssumptions
  /** Echoed from the payload so the panel can cite its source. */
  sourceNetTheta: number
  sourceAsOf: string
}

/** Returns null — never an empty projection — when the base is unknown. */
export function projectTheta(
  netTheta: number | null,
  asOf: string | null,
  sessions?: 30,
): ThetaProjection | null
```

```ts
export interface ThetaLadderProps {
  projection: ThetaProjection | null
  status: PanelStatus['kind']
}
```

**Chart reuse.** Reuses `recharts` the same way `YieldBars.tsx` does — a
`BarChart` of cumulative decay per session. A new component
`app/components/risk/ThetaLadder.tsx` wraps it rather than extending `YieldBars`,
because `YieldBars` is bound to a screening payload shape and the projection badge
and assumptions block are structural here, not decoration.

**Layout.** 1440px: full-width panel below `ExposureMatrix`, 30 bars, x-axis
labelled every 5 sessions. 390px: 10 bars visible with horizontal scroll, badge
and assumptions stack above the chart so they are read first.

---

## 5 · Fixture strategy — build before the endpoint exists

The endpoint does not exist. The panels are still built and verified today, by
making every component a pure function of props and driving those props from
fixtures that live **only** in the test tree.

### 5.1 · Where fixtures live

```
frontend/tests/fixtures/
├── realTrace.ts            (existing)
└── risk/
    ├── allPresent.ts       every greek and every cap populated, no breach
    ├── oneNull.ts          net_vega null, everything else present
    ├── noCaps.ts           all three caps null, greeks present
    ├── breached.ts         two breaches, one critical one warning
    ├── halted.ts           kill_switch.halted true, three reasons, clears present
    └── index.ts            named re-exports, typed as PortfolioGreeksPayload
```

Each fixture is typed, so a change to the payload interface breaks the fixtures at
compile time rather than at demo time:

```ts
import type { PortfolioGreeksPayload } from '@/../lib/risk/types'

export const oneNull: PortfolioGreeksPayload = {
  net_delta: 1240,
  net_theta: 412.8,
  net_vega: null,
  net_gamma: 0,            // a REAL zero, deliberately present in this fixture
  beta_weighted_delta: 980,
  nav: 300000,
  per_symbol: {
    AAPL: { delta: 620, theta: 210.4, vega: null, gamma: 0 },
    MSFT: { delta: 620, theta: 202.4, vega: null, gamma: null },
  },
  breaches: [],
  caps: {
    max_net_vega_pct_nav: 8,
    max_beta_weighted_delta_pct_nav: 30,
    min_net_theta: 100,
  },
  kill_switch: { halted: false, reasons: [], clears: null, halted_at: null },
  as_of: '2026-08-29T14:32:00Z',
}
```

### 5.2 · How the engineer verifies without the endpoint

1. Unit tests drive `lib/risk/format.ts`, `lib/risk/model.ts`, the sort
   comparator, the breach-ordering comparator, and the `PanelStatus` mapper from
   the fixtures. These run today under the existing `vitest.config.ts` (`node`
   environment, `include: ['tests/**/*.test.ts']`) with no DOM.
2. Visual verification uses a **dev-only route** `app/risk/preview/page.tsx` that
   is gated on `process.env.NODE_ENV !== 'production'` and returns `notFound()`
   otherwise. It does not import fixtures. It reads a payload from a local file
   the engineer places at `frontend/.local/risk-sample.json` — untracked, listed in
   `.gitignore`, absent in CI — via a `fetch` in a `useEffect`. If the file is
   absent the preview route renders the not-deployed state, which is itself one of
   the four states the acceptance criteria require screenshotting.
3. Screenshots for `docs/frontend-verification/` are taken from
   `/risk/preview` for the four acceptance states plus the halt state, at 1440px
   and 390px.
4. When `GET /api/risk/greeks` lands, `app/risk/page.tsx` switches from nothing to
   `useRiskQuery()` and the preview route is deleted in the same commit.

### 5.3 · Enforcement — not discipline

Two mechanisms, both mechanical.

**(a) A vitest assertion that greps the source tree.** New file
`frontend/tests/fixtures-isolation.test.ts`, running in the existing node
environment with `node:fs`:

```ts
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const ROOT = resolve(__dirname, '..')
const SCANNED = ['app', 'lib']
const FORBIDDEN = /(tests\/fixtures|from\s+['"].*fixtures)/

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.(ts|tsx)$/.test(full)) out.push(full)
  }
  return out
}

describe('fixture isolation', () => {
  it('no file under app/ or lib/ imports anything from tests/fixtures', () => {
    const offenders: string[] = []
    for (const dir of SCANNED) {
      for (const file of walk(join(ROOT, dir))) {
        if (FORBIDDEN.test(readFileSync(file, 'utf8'))) offenders.push(file)
      }
    }
    expect(offenders).toEqual([])
  })

  it('no risk source file uses falsy-coercion on a numeric', () => {
    const offenders: string[] = []
    const patterns = [/\|\|\s*0\b/, /!\s*(value|greek|net_[a-z]+)\b/, /Number\([^)]*\)\s*\|\|/]
    for (const file of walk(join(ROOT, 'lib', 'risk'))) {
      const src = readFileSync(file, 'utf8')
      if (patterns.some((p) => p.test(src))) offenders.push(file)
    }
    expect(offenders).toEqual([])
  })
})
```

The second assertion is the one that catches the actual bug class: `value || 0`
silently converts a real zero into a fallback and a `null` into a lie, and it is
the single most likely way R1 and R2 get violated during a hackathon push.

**(b) A pre-push grep in the checklist.** Added to the frontend pre-push block:

```bash
# fixtures must never be reachable from shipped code
grep -rn "tests/fixtures" frontend/app frontend/lib && exit 1
# the dev-only preview route must not exist at freeze
test -e frontend/app/risk/preview/page.tsx && echo "DELETE preview route before freeze"
```

Both run in under a second and fail loudly. Neither depends on anyone remembering
the rule.

---

## 6 · Accessibility

**Breach is never colour-only.** Every breached element carries a text badge in
addition to its `error` `#ef4444` treatment. The badge is a shared component,
`app/components/risk/BreachBadge.tsx`:

```ts
export type BadgeKind = 'breach' | 'halt-cause' | 'unclassified' | 'projection'

export interface BreachBadgeProps {
  kind: BadgeKind
  /** Full sentence for assistive tech, e.g. 'Net vega 26,400 exceeds cap 24,000'. */
  detail: string
  id?: string
}
```

Badge text is literal and short: `BREACH`, `HALT CAUSE`, `UNCLASSIFIED`,
`PROJECTION`. `label-caps` (11px, .05em), uppercase, 1px border, `rounded`
2px padding. `breach` and `halt-cause` use `#ef4444` text on
`surface-container-high` `#1a2332` with a `#ef4444` border; `unclassified` uses
`on-surface-variant` `#94a3b8`; `projection` uses `secondary` `#fbbf24`. The badge
renders `detail` in an `sr-only` span so a screen reader gets the full sentence
while the projector gets three legible words.

**Contrast against `background` `#020617`.** Every foreground colour used for text
on this page must clear WCAG AA 4.5:1 against `#020617` at body size and 3:1 at
`headline-md` and above. Measured against `#020617`:

| Foreground | Ratio vs `#020617` | Verdict |
|---|---|---|
| `on-surface` `#f8fafc` | ~19.0:1 | body text, values |
| `on-surface-variant` `#94a3b8` | ~7.6:1 | labels, reasons, em dash |
| `primary` `#22c55e` | ~8.4:1 | enabled/OK states |
| `secondary` `#fbbf24` | ~11.4:1 | projection badge |
| `error` `#ef4444` | ~4.6:1 | breach text — passes AA at body size, but only just |
| `outline` `#334155` | ~1.7:1 | **borders and non-text only, never text** |

Because `#ef4444` clears 4.5:1 with almost no margin, breach text is never
rendered below 14px (`body-sm`) and never at font-weight below 500, and it is
always accompanied by the badge, so legibility never rests on the red alone. The
badge sits on `surface-container-high` `#1a2332` rather than on `#020617`, where
`#ef4444` reads at roughly 4.2:1 — below AA — which is precisely why the badge
text is uppercase `label-caps` at weight 600 with a `#ef4444` border carrying the
signal, and why the full sentence is duplicated in `sr-only` text rather than
relying on the small red glyphs.

**How `ExposureMatrix` announces a breached cell.** The table is a real
`<table>` with `<caption class="sr-only">`, `<th scope="col">` per greek and
`<th scope="row">` per symbol, so every cell is already announced with its symbol
and greek. On top of that:

1. The breached `<td>` contains a visible `BreachBadge kind="breach"` whose
   `sr-only` detail reads
   `"Breach: AAPL vega 26,400 exceeds cap 24,000 dollars per volatility point."`
2. The `<td>` carries `aria-describedby` pointing at that badge's `id`, so the
   description is read after the cell's value rather than replacing it.
3. The `<td>` also carries `data-breach="true"`, which is what the vitest DOM-free
   assertions and the Playwright spec key off — never the colour class.
4. The table has a live `role="status"` sibling that summarises
   `"3 of 12 exposure cells are in breach."` so a screen-reader user knows to look
   before traversing 12 rows.
5. Sorting a column moves focus to the column header and announces
   `"Sorted by vega, descending. Unknown values last."` — the last clause matters,
   because a sighted user can see the em dashes at the bottom and a screen-reader
   user cannot.

`ScoreGauge`'s existing pattern of an `aria-hidden="true"` SVG plus an `sr-only`
sentence is carried into `CapGauge` verbatim; that is the one thing the existing
gauge gets exactly right and it is reused rather than reinvented.

---

## 7 · Dashboard risk strip

`app/components/risk/RiskStrip.tsx`, mounted in `app/dashboard/page.tsx`
immediately below the existing `MetricCard` row and above `UnderlyingAssets`,
inside the existing `RevealGroup` / `RevealItem` pair so it inherits the house
reveal and the reduced-motion path already implemented in
`app/components/motion/primitives.tsx`.

```ts
export interface RiskStripProps {
  status: PanelStatus
}
```

**What it shows** — one row, five slots, each `label-caps` label over a
`mono-code` value rendered through `Num`:

| Slot | Source | Notes |
|---|---|---|
| NET Δ | `net_delta` | `formatGreek(v, { digits: 0, signed: true })` |
| NET Θ | `net_theta` | `formatCurrency(v, { signed: true })`, suffix `/day` |
| NET V | `net_vega` | `formatCurrency(v)`, suffix `/vol pt` |
| β-WTD Δ | `beta_weighted_delta` | `formatGreek(v, { digits: 0, signed: true })` |
| BREACHES | `breaches.length` | count; `0` renders `0` in `primary` `#22c55e`, non-zero renders the count in `error` `#ef4444` with a `BREACH` badge |

Plus a trailing link `RISK COCKPIT →` to `/risk`, and the F1 freshness dot fed by
`freshness.ts` so a stale strip is visibly stale rather than quietly wrong.

Not shown: `net_gamma` (no room and least legible at a glance), `per_symbol`, and
`ThetaLadder` (R8.6 — a projection cannot travel without its label).

When `kill_switch.halted` is true, `KillSwitchPanel variant="banner"` renders
above the strip on `/dashboard` as well, and the strip's own background shifts to
`surface-container-high` `#1a2332` with a 1px `#ef4444` top border. The halt
banner is the same component in both places; there is no second implementation to
drift.

**When the endpoint 404s.** The strip collapses to a single line, full width,
`surface-container` `#131c2e`, `outline` `#334155` border, `body-sm`
`on-surface-variant` `#94a3b8`:

> `Portfolio greeks unavailable — risk engine not deployed (GET /api/risk/greeks → 404)`

with a `lucide-react` `Unplug` icon and **no numbers, no zeros, no gauges, and no
placeholder slots**. It does not retry on a loop (F1's query config governs), it
does not surface a toast, it does not disable any control, and it does not hide
itself — an invisible strip would let a viewer assume risk is being monitored. The
`RISK COCKPIT →` link stays live so `/risk` can show the same honest empty state
in full. A `5xx` or timeout renders the same shell with the error message and a
`Retry` button, in `error` `#ef4444`; the two are never conflated, because one
means "not built yet" and the other means "broken right now".

---

## 8 · Test list

New files, added to the existing suite (`vitest.config.ts`: `environment: 'node'`,
`include: ['tests/**/*.test.ts']`, `@` → `./app`). All pure-logic; no DOM, no
network. Every one of these fails against the current commit, because none of the
modules exists yet.

`tests/riskFormat.test.ts`

1. `formatGreek(1240.5)` returns `kind: 'value'` with text `'1,240.50'`.
2. `formatGreek(1240.5, { digits: 0, signed: true })` returns `'+1,241'`.
3. `formatGreek(-88.2, { signed: true })` returns `'-88.20'` — sign preserved.
4. **`formatGreek(null)` returns `kind: 'unknown'` and its `text` is never `'0'`, `'0.00'`, or `''`.**
5. **`formatGreek(0)` returns `kind: 'value'` with text exactly `'0.00'` — a real zero renders as zero.**
6. `formatGreek(0)` and `formatGreek(null)` are deep-unequal in `kind`, `text`, and `reason`.
7. `formatGreek(NaN)` returns `kind: 'unknown'` with reason `'value not finite'`.
8. `formatGreek(Infinity)` returns `kind: 'unknown'`, not a formatted `'∞'`.
9. `formatGreek(-0)` returns text `'0.00'`, never `'-0.00'`.
10. `formatGreek(undefined)` returns `kind: 'unknown'` with the default reason.
11. `formatCurrency(412.8)` returns `'$412.80'`.
12. `formatCurrency(0)` returns `'$0.00'` with `kind: 'value'`.
13. `formatCurrency(null)` returns `kind: 'unknown'` with text `'—'` (U+2014, asserted by code point).
14. `formatCurrency(-1250)` returns `'-$1,250.00'` — minus outside the symbol.
15. `formatPct(8.5)` returns `'8.5%'`; `formatPct(0)` returns `'0.0%'` with `kind: 'value'`.
16. `formatPct(null)` returns `kind: 'unknown'`.
17. `formatCapBand(8, 300000, 'max')` returns the derived string including `'(derived from NAV)'`.
18. `formatCapBand(8, null, 'max')` returns `'max 8.0% NAV (NAV not reported)'` and does not invent an absolute cap.
19. `formatCapBand(null, 300000, 'max')` returns `kind: 'unknown'` with reason `'cap not configured'`.
20. `formatCapBand(0, 300000, 'max')` returns `kind: 'value'` — a zero cap is configured, not missing.
21. Every `UNKNOWN_REASON` string is non-empty, so no unknown ever renders a bare dash with no explanation.

`tests/riskSchema.test.ts`

22. `allPresent` fixture parses and every numeric field is a `number`.
23. `oneNull` fixture parses with `net_vega === null` after validation — not coerced.
24. A payload with `net_vega` absent entirely parses to `net_vega === null`, never `0`.
25. A payload with `net_vega: "n/a"` parses to `null` via `.catch(null)` rather than throwing away the whole object.
26. `caps` with all three fields absent parses to three `null`s.
27. The schema source contains no `.default(0)` (source-text assertion, guards regression).
28. `kill_switch.clears` absent parses to `null`, and `reasons` absent parses to `[]`.

`tests/riskStatus.test.ts`

29. A 404 response maps to `PanelStatus { kind: 'not-deployed' }`, not `'error'`.
30. A 500 response maps to `{ kind: 'error' }` with the server message preserved.
31. An `AbortError` maps to `{ kind: 'error' }` with a message distinguishing timeout from unreachable.
32. A valid payload maps to `{ kind: 'ready' }` with the parsed object.
33. `not-deployed` never yields a `data` property, so no panel can read zeros off it.

`tests/riskMatrix.test.ts`

34. Descending sort on `vega` orders real values high→low.
35. Ascending sort on `vega` still places `null` cells **last**, not first.
36. A symbol whose every greek is `null` still appears as a row.
37. `breachedCells` marks exactly the named `(symbol, greek)` pairs and no neighbours.
38. Breach detection reads the payload's breach list, never a comparison the frontend computed.
39. Sort is stable for equal values (insertion order preserved).

`tests/riskBreachOrder.test.ts`

40. Ordering is `critical` → `warning` → `info` → `null` severity.
41. `severity: null` maps to badge text `'UNCLASSIFIED'`, never promoted to `critical`.
42. A breach with `observed: null` still renders its `message` verbatim.
43. Breaches that are also halt reasons are flagged `HALT CAUSE`.

`tests/thetaProjection.test.ts`

44. `projectTheta(412.8, '2026-08-29T14:32:00Z')` returns 30 points with `cumulative` monotonic in the sign of theta.
45. `projectTheta(null, '...')` returns `null` — no projection from an unknown base.
46. `projectTheta(412.8, null)` returns `null` — a projection with no `as_of` cannot cite its source.
47. `projectTheta(0, '...')` returns 30 points all `cumulative === 0` — a real zero-theta book projects a flat line, which is honest.
48. The returned object carries `kind: 'projection'` and the full `assumptions` record, so the panel cannot render without them.
49. `sourceNetTheta` equals the input exactly (no rounding into the projection).

`tests/fixtures-isolation.test.ts`

50. No file under `app/` or `lib/` references `tests/fixtures`.
51. No file under `lib/risk/` contains `|| 0`, `!value`, or `Number(...) ||`.

`tests/riskA11y.test.ts`

52. Every `BadgeKind` maps to a non-empty uppercase label string.
53. Breach badge construction requires a non-empty `detail` sentence (throws or fails type-check on empty).
54. The em dash constant is U+2014, asserted by `codePointAt`, not a hyphen or en dash.

That is 54 assertions from F2 alone against the brief's ≥40 target for F6, and
every one of them fails on the current commit.

---

## 9 · Acceptance checklist

- [ ] `/risk` renders correctly against `allPresent`, `oneNull`, `noCaps`, and `halted`.
- [ ] Screenshots of all four states plus `not-deployed`, at 1440px and 390px, in `docs/frontend-verification/`.
- [ ] `npm run test` green including the 54 assertions above.
- [ ] `grep -rn "tests/fixtures" frontend/app frontend/lib` returns nothing.
- [ ] `app/risk/preview/page.tsx` deleted before freeze.
- [ ] No hardcoded threshold anywhere in `app/components/risk/` or `lib/risk/`.
- [ ] `ThetaLadder` badge and assumptions block visible in the 1440px screenshot.
- [ ] Reduced-motion run: `CapGauge` sweep and `RiskStrip` reveal both go still.

