# FRONTEND

Next.js App Router + Tailwind. Owner: `axzss` (see [`JOBDESK.md`](JOBDESK.md)).

The governing rule in this layer: **never render a number the backend did not
produce.** An empty state is information; a plausible-looking placeholder is a
lie that survives into a demo.

---

## Structure

```
frontend/
├── app/
│   ├── layout.tsx              root layout, fonts, OG/Twitter metadata
│   ├── icon.tsx                favicon (next/og, generated)
│   ├── opengraph-image.tsx     1200x630 link preview (next/og, generated)
│   ├── page.tsx                redirects to /dashboard
│   ├── dashboard/page.tsx      metrics, charts, holdings, agent panel
│   ├── assets/page.tsx         position detail + order history
│   ├── terminal/page.tsx       agent feed, daily cycle, order intents
│   ├── council/page.tsx        six-persona verdicts
│   ├── settings/page.tsx       live StrategyConfig editing
│   ├── components/
│   │   ├── brand/Logo.tsx      LogoMark + LogoLockup (self-drawing)
│   │   ├── charts/             EquitySparkline, ScoreGauge, AllocationDonut, YieldBars
│   │   ├── motion/primitives.tsx  shared variants + Reveal wrappers
│   │   ├── council/            CouncilBoard
│   │   ├── dashboard/          AgentStatusCard
│   │   ├── terminal/           TerminalClient, AgentFeedCard
│   │   ├── AgentRunProvider.tsx  shares ONE agent run across dashboard panels
│   │   ├── AgentControl.tsx      run trigger + intent preview
│   │   ├── ThoughtProcess.tsx    reasoning trace viewer
│   │   ├── Sidebar.tsx / MobileSidebar.tsx / Header.tsx
│   │   └── ActiveOverlayContracts · UnderlyingAssets · AssetHoldings ·
│   │       PortfolioStats · RecentHistory · MetricCard · StrategyConfigCard
│   ├── types/portfolio.ts      AccountInfo, Position, Order
│   └── data/mock_portfolio.json  offline fallback for usePortfolio
├── lib/api.ts                  typed client — the only place fetch() appears
└── next.config.js              dev proxy /api/* → :8000
```

Single app root: `frontend/app` only. There is no `src/app`, and adding one would
give Next two competing route trees.

---

## `lib/api.ts` — the only network boundary

Every request in the app goes through here. Components never call `fetch`
directly, so response-shape changes land in one file.

```ts
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'
```

### Paths carry the `/api` prefix, except `/health`

`backend/app/main.py` mounts every router with `prefix="/api"`; only `/health` is
bare. For about a day this client called bare paths and **every request 404'd
while the UI looked healthy**, because failures fell back to mock data. Verified:

```
GET /health          → 200
GET /api/portfolio   → 200
GET /portfolio       → 404
```

The dev proxy in `next.config.js` must map `/api/health` → bare `/health`
**before** the catch-all `/api/:path*` rule; Next matches in order.

### Client surface

| Method | Endpoint |
|---|---|
| `api.getHealth()` | `GET /health` |
| `api.getPortfolio()` | `GET /api/portfolio` |
| `api.screenStrategies()` | `GET /api/strategy/screen` |
| `api.getStrategyConfig()` / `api.updateStrategyConfig()` | `GET|PUT /api/strategy/config` |
| `api.assessCouncil(symbols?)` | `GET|POST /api/council/assess` |
| `api.runDailyCycle()` | `POST /api/council/cycle` |
| `api.runAgent()` | `POST /api/agent/run` |
| `api.submitTrade()` | `POST /api/trade` — never called automatically |

Types (`OrderIntent`, `AgentRunResponse`, `CouncilAssessment`, `CouncilVerdict`,
`CouncilDissent`, `CouncilTierPolicy`, `DailyDirective`, `CycleResponse`) were
written by reading `backend/app/routes/*.py` and confirming against live
responses — **not** from a design document. `specials/BACKEND_FRONTEND_API.md`
currently disagrees with the API in three places; see
[`KNOWN-ISSUES.md`](KNOWN-ISSUES.md). [`API-CONTRACT.md`](API-CONTRACT.md) has the
verified shapes.

### Helpers

- `normalizeScreenings(res)` — tolerates the several shapes `/strategy/screen` can
  return, and surfaces `liveError`
- `toFeedEntry(raw, i)` → `FeedEntry`; yields are fractional (`0.12`) from the
  backend but already-percent values are tolerated
- `riskBadgeClasses(score)`, `actionLabel(action)` — shared so a score reads the
  same colour everywhere
- `usePortfolio()` — hook with `usingFallback` when the backend is unreachable

### `live_error` is never swallowed

`/api/strategy/screen` returns an optional `live_error` when live data failed and
fallback was used. Terminal renders it as an amber banner. This exists because a
silent mock fallback hid an Alpaca auth-header bug (`APCA-API-SECRET` vs
`APCA-API-SECRET-KEY`) for a full day — every live call was returning 401 and the
app looked fine.

---

## Layout

`Sidebar` is `fixed inset-y-0 left-0 w-[240px]` on `lg+`, so it leaves the
document flow. Each page's content wrapper therefore carries `lg:ml-[240px]`:

```tsx
<div className="flex h-screen …">
  <Sidebar />
  <div className="flex flex-1 flex-col min-w-0 lg:ml-[240px]">
    <Header />
    <main className="flex-1 overflow-y-auto">…</main>
  </div>
</div>
```

Without that margin the flex child starts at x=0 and **cards render underneath the
sidebar** — that was a real reported bug, not a hypothetical.

`240px`, not `ml-64` (256px), so it matches the sidebar exactly. `lg:` only:
below that breakpoint the sidebar is `hidden` and navigation is the
`MobileSidebar` drawer driven by `useState`. **No bottom navigation.**

### Header holds no navigation

`Header` is brand + status indicators (VPS, PAPER TRADING) + profile actions.
It previously carried its own nav array duplicating the sidebar — and that array
was **stale, missing the Council link entirely**, so anyone navigating from the
header could not reach `/council`. Sidebar is the single source of primary
navigation; duplicating it means one copy silently rots.

---

## Brand

`components/brand/Logo.tsx` exports `LogoMark` (square, 32×32 viewBox) and
`LogoLockup` (mark + wordmark + optional subtitle).

The mark draws the product name literally: a flat slate baseline (equity held,
going nowhere) with two overlay layers stepping above it, the active layer in
emerald. Deliberately flat — **no gradients, no glow, no glassmorphism**, because
those read as generic AI-startup styling rather than as a financial tool.

`app/icon.tsx` and `app/opengraph-image.tsx` generate the favicon and the
1200×630 link preview via `next/og`, so there are no binary assets to keep in
sync with the SVG.

> Satori gotcha: every div with more than one child needs an explicit
> `display: 'flex'`, and `<br/>` is not laid out. The OG route failed to
> prerender until each text line became its own flex div.

On mount each layer of the mark draws itself via `pathLength` — baseline first,
then the two overlays — so the mark builds the way the product does. One pass, no
looping: a logo that animates forever is a distraction. Pass `animate={false}` for
static contexts.

---

## Motion

`framer-motion` was already in `package.json` and entirely unused.
`components/motion/primitives.tsx` is the single source of animation timing, so
values cannot drift between pages. Import from there; do not hand-roll variants
per component.

### House rules

| Rule | Reason |
|---|---|
| 160–260ms | Longer reads as lag in a trading UI |
| 4–10px of travel | Bigger slides feel like a marketing site |
| Ease out `[0.22, 1, 0.36, 1]`, never spring | Overshoot on financial data looks unserious |
| Opacity and transform only | Animating layout-affecting properties causes reflow |
| `prefers-reduced-motion` honoured **per primitive** | Checked inside each one via `useReducedMotion`, not bolted on globally — reduced motion collapses to a plain `div` |

### Exports

- Variants: `fadeUp`, `fade`, `slideIn`, `collapse`
- `staggerParent(stagger, delayChildren)`
- Wrappers: `Reveal`, `RevealGroup`, `RevealItem`
- `pressable` — scale 1.01 hover / 0.98 tap for buttons
- `EASE`, `DURATION` (`fast` 0.16, `base` 0.22, `slow` 0.32)
- Re-exports `motion` and `useReducedMotion` so components need one import

### Per surface

| Surface | Motion |
|---|---|
| `MobileSidebar` | `AnimatePresence` owns mount/unmount — the early `if (!open) return null` had to go, otherwise the drawer vanishes instead of animating out. Backdrop fades, panel slides from `-100%`, nav items stagger at 35ms |
| `Sidebar` | Active emerald marker is a `layoutId` element, so it **slides** between items on route change rather than disappearing and reappearing |
| `MetricCard` | Value crossfades on change, keyed on the value itself, so a refresh reads as an update rather than a silent swap. Fixed-height wrapper prevents reflow |
| Dashboard / Assets / Settings | Staggered card entrances via `RevealGroup` |
| `CouncilBoard` | Cards stagger; verdict list expands by height with rows sliding in; chevron rotates instead of swapping icons |
| `ScoreGauge` | Arc sweeps from zero on mount. 400ms — deliberately above the house ceiling, because a sweep needs to be legible |
| `TerminalClient` | Directive cards stagger, **capped at 240ms** so a long list does not crawl; reasoning traces expand by height; error and `live_error` banners animate in and out |
| `AgentControl` / `ThoughtProcess` | HALT and error banners animate; trace lines slide in at 35ms capped at 400ms; run summary fades up |
| `YieldBars` | Bars grow from zero, staggered top to bottom, so the ranking reads as it fills |

### Cost

Shared JS is unchanged at 87.3 kB, but per-page first load rose roughly 34 kB:

| Page | Before | After |
|---|---|---|
| `/assets` | 111 kB | 145 kB |
| `/council` | 112 kB | 146 kB |
| `/terminal` | 115 kB | 149 kB |
| `/dashboard` | 221 kB | 255 kB |

That is the price of the library. Worth naming rather than discovering later.

### Pitfalls found doing this

- `Transition['ease']` is not exported usefully in framer-motion 10 — typing the
  cubic array as `as const` is what compiles.
- Any component importing from `primitives.tsx` becomes a client component.
  `Logo.tsx` needed `'use client'` added for this reason.
- Repeated dev-server restarts while editing corrupt `.next` and produce a 500
  with `__webpack_modules__[moduleId] is not a function`. `rm -rf .next`.

---

## Charts

`recharts` was already a dependency and completely unused. Four charts now use it
where a picture beats a number — all restrained: thin strokes, muted palette, one
emerald accent, `tabular-nums` on every figure.

| Component | Where | Notes |
|---|---|---|
| `EquitySparkline` | Dashboard | Emerald up / red down. Domain padded 15% so a small move doesn't fill the box and look dramatic |
| `ScoreGauge` | Council cards | Pure SVG ring, not recharts — no radial gauge there is worth the bundle. Bands match `riskBadgeClasses`: emerald ≥60, amber ≥40, red below |
| `AllocationDonut` | Dashboard | Percentages in the legend, not on the slices. Largest holding takes the emerald so concentration is what your eye lands on |
| `YieldBars` | Terminal | Hand-rolled divs: at this size a BarChart's axes and tooltips make comparison harder. Amber marks risk ≥60 |

### Charts must not invent data

- The sparkline gets **two real points** — `last_equity` and `equity` — because
  that is all `/api/portfolio` exposes. No interpolation. Fewer than two points
  renders an explanatory line instead of a flat fake curve.
- `YieldBars` **omits** candidates with no reported yield. A bar at 0% would read
  as "no premium" rather than "not provided".
- `AllocationDonut` filters non-finite and non-positive values rather than
  coercing them to zero.

---

## The agent panels

### `AgentRunProvider`

One run, shared. `AgentControl` and `ThoughtProcess` both consume the same
context, so they always describe the same run instead of each firing its own
request and disagreeing.

```tsx
<AgentRunProvider>
  <AgentControl />
  <ThoughtProcess />
</AgentRunProvider>
```

### `AgentControl`

Calls `api.runAgent()`. Its job is to be truthful about what the backend actually
returns:

- `risk_summary.halted` → renders the kill-switch HALT banner **with reasons**,
  and no intent table. The kill-switch runs first in the cycle, so a halted run
  genuinely produced nothing — an empty table would misrepresent that.
- `order_intents: []` → says so explicitly.
- `option_symbol` / `limit_price` are `null` → renders "contract pending" and
  "no limit set", not a fabricated strike. `_order_intents` cannot resolve a
  contract yet ([`KNOWN-ISSUES.md`](KNOWN-ISSUES.md) #3), and the UI should show
  that rather than paper over it.
- Every intent shows `requires_approval`. Nothing here calls `/api/trade`.

### `ThoughtProcess`

Renders `reasoning_trace` from the run, numbered, or an empty state.

This component previously contained a hardcoded array claiming
`Executing SELL to OPEN 1 Contract SPY 565C` and
`Order Confirmed. Yield harvested: $120.00`. None of it ever happened. On a
dashboard it read as a completed live trade — the single largest credibility risk
in the project, and worse than a missing feature because a missing feature is
honest.

### `ActiveOverlayContracts`

Filters real positions by `asset_class` containing `option` and parses the OCC
symbol (`ROOT + YYMMDD + C|P + strike×1000`) for strike, expiry and DTE. Empty
state when no overlay is open — which is the truthful answer most of the time.

Previously a hardcoded `SPY 520c 15Mar24 / $125.00` row that existed nowhere in
the account.

---

## Deleted mockups

Twelve files removed. Two generations of components had been coexisting — mockups
from the design phase and wired components from integration — with no record of
which was which, and the dashboard rendered a mix of both in the same column.

| Removed | Why |
|---|---|
| `AgentConfiguration` | A second config panel whose Save called `alert('Configuration saved successfully.')` and persisted nothing. `StrategyConfigCard` already owns every tunable it claimed |
| `ActiveOverlay`, `TradeLog`, `OverlayControl`, `AgentTerminal`, `Dashboard`, `StrategyCard` | Never imported by any route |
| `ai/`, `portfolio/`, `strategy/`, `trading/` | Never imported |
| `ui/` (Badge, Button, Card, tabs) | Never imported; pages use Tailwind directly |

Net −1290 lines. An unused mockup is not harmless: the next person to open the
tree cannot tell it from a feature.

---

## Verification gate

```bash
cd frontend
npx tsc -p tsconfig.json --noEmit   # must be clean
npm run build                       # must compile every page
```

Then load every page and confirm no console errors. **HTTP 200 is not
sufficient** — a page can return 200 while rendering an error boundary.

Last verified state: `tsc` clean; build 11/11 pages including `/icon` and
`/opengraph-image`; all five pages plus both image routes 200; all six API
endpoints 200 through the dev proxy.

**Motion is exempt from none of this and covered by none of it.** A type check
cannot tell you an easing curve is wrong, a stagger is too slow, or a drawer
animates in the wrong direction. Animation is the part of this layer with the
weakest verification story.

> `/dashboard` returning 500 with
> `TypeError: __webpack_modules__[moduleId] is not a function` is a corrupt
> `.next` cache from repeated dev-server restarts, not a code bug.
> `rm -rf .next` and rebuild.

---

## Conventions

- **Tailwind only.** No CSS modules, no styled-components, no inline `style`
  except inside `next/og` routes where Satori requires it.
- Colours are literal hex in class names (`text-[#22c55e]`) matching the existing
  palette; no theme indirection was introduced.
- `'use client'` on anything with state or effects. Pages are client components
  because they all fetch.
- `tabular-nums` on every numeric column so digits do not jitter between renders.
- Mobile navigation is a `useState` drawer. No bottom nav.
- One app root. No `src/app`.
- **Animation comes from `components/motion/primitives.tsx`.** Do not write
  per-component variants; add to the primitives module if something is missing,
  so timing stays consistent and `prefers-reduced-motion` stays honoured.

---

## Open frontend work

See [`ROADMAP.md`](ROADMAP.md) for ordering.

1. **No visual verification has ever happened.** `browser_exec` cannot attach,
   Playwright is not installed, and headless Chrome hit root-sandbox → missing
   `DISPLAY` → websocket-origin-403 in sequence. Nobody has looked at this UI —
   and animation now sits on top of that, entirely unwatched. Easing, stagger
   timing and drawer direction are reasoned, not observed.
2. **No E2E test.** One Playwright smoke run (dashboard → council → terminal)
   would catch the class of regression that a type check cannot.
3. **No unit tests.** `normalizeScreenings`, `toFeedEntry`, `riskBadgeClasses`
   are pure functions with no coverage.
4. **Lighthouse / a11y unrun.** `aria-label`s were added to icon-only buttons,
   but contrast ratios and focus states have not been audited. Motion adds a
   dimension here too: `prefers-reduced-motion` is implemented but has never
   been tested with the setting actually on.
5. **Motion bundle cost is unmitigated.** ~34 kB per page. No code-splitting or
   `LazyMotion` attempt yet; if page weight becomes a concern, that is where to
   look first.
6. **Two "run agent" entry points.** Dashboard and Terminal both call
   `/api/agent/run`. Intended split is compact trigger vs detailed view, but a
   user could still wonder why two buttons exist.
7. **Four one-line `Providers.tsx` stubs** sit in the route folders
   (`app/{assets,dashboard,settings,terminal}/Providers.tsx`), each returning
   `children` unchanged and imported by nothing. Harmless, but they are noise.
