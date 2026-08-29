# ROADMAP

Ordered by value delivered per unit of work, not by how interesting the work is.

---

## Now — before any demo

### 1 · Remove the fabricated trade log
**Frontend.** `ThoughtProcess.tsx` displays a fake executed trade and a fake $120
yield harvest. In front of judges this is worse than a missing feature. Replace
with real `reasoning_trace` from `/api/agent/run`, or delete the component.

Why first: it costs minutes and removes the only defect that could damage
credibility rather than merely function.

### 2 · Persist the fundamentals cache
**AI engineering.** Move `/tmp/fundamentals_cache.json` → `docs/.cache/fundamentals.json`
(already gitignored), keep 24h TTL and atomic writes, `/tmp` fallback if the repo
path is read-only, and add `data_age_hours` + `stale` to the merged snapshot.

Why: a restart silently drops the council from HIGH to LOW confidence and reverts
NVDA/MSFT to HOLD. This is the only way the demo fails without anyone touching
anything.

### 3 · Wire `AgentControl` honestly
**Frontend.** The dashboard button has no `onClick`. Connect it to
`api.runAgent()` and render the result truthfully: show the halt reason when
`risk_summary.halted`, and "no order intents" when the list is empty — which with
issue #3 open is the normal case.

---

## Next — makes the demo land

### 4 · Logo and visual identity
**Frontend.** Currently nothing: no favicon, no mark in the sidebar, no OG image.
Needed: SVG mark, wordmark, favicon, Next.js app icon, OG image for link previews.

Direction: flat, slate + a single emerald accent. Metaphor options — layered
overlay lines (matching the product name), or an AO monogram. Explicitly **not**
purple/blue gradients, glow, or glassmorphism.

### 5 · Charts
**Frontend.** `recharts` is already in dependencies and completely unused. Four
places where a chart says more than a number:

| Chart | Page | Why |
|---|---|---|
| Equity sparkline | Dashboard | Single strongest "this is a real product" signal |
| Risk gauge ring | Council cards | Replaces a bare number with something readable at a glance |
| Allocation donut | Assets | Concentration becomes visible instead of arithmetic |
| Premium yield bars | Terminal | Makes candidate comparison instant |

Restraint is the whole point: thin strokes, muted palette, minimal gridlines,
`tabular-nums` on every number.

### 6 · Verify the UI visually
**Frontend.** Nobody has ever looked at it. Open the tunnel in a real browser,
walk all five pages, confirm no console errors — faster than fixing headless
Chrome in this environment. Then add one Playwright smoke test so the next
regression is caught automatically.

### 7 · Resolve `_order_intents`
**Backend.** Make it produce a real contract: resolve `option_symbol` and
`limit_price` from the Alpaca option chain using the tier's delta band and DTE.
Until this lands, the order-preview table shows `—` in its three most interesting
columns.

### 8 · Reconcile `BACKEND_FRONTEND_API.md`
**Backend.** Fix `tier`, `consensus_score` scale, `delta_min` sign, and
`dissent[].why` type. A contract document that disagrees with the code is worse
than no document — it produces confidently wrong client code.

---

## Then — depth the judges will probe

### 9 · Mr. Market hysteresis
**AI engineering.** Accept `previous_mood`, require a margin before switching
regime. Stops the euphoric-block from flickering on noise.

### 10 · Graham INCONCLUSIVE as half-fail
**AI engineering.** `FAIL < INCONCLUSIVE < PASS`, with each affected bullet
stating the penalty came from unverifiable data. Removes the bullish bias on
thin-data names. Known effect: SPY/QQQ −1.2, NVDA −0.4, JPM −0.4.

### 11 · Structured council handoff
**AI engineering.** Emit JSON alongside the markdown report and parse that
instead of regex-matching prose. Then consider signing it, per the red team's
residual recommendation.

### 12 · Deeper fundamentals coverage
**AI engineering.** Source 10-year earnings and 20-year dividend history so Ch.14
tests 3, 4 and 5 can actually be decided instead of returning INCONCLUSIVE. This
is the difference between a Graham persona that has an opinion and one that
mostly shrugs.

### 13 · Real sector classification
**AI engineering.** `sector_cap_group` is a hardcoded tuple of four tickers.
Replace with actual sector data so the correlation cap generalises beyond the
current universe.

### 14 · Demo script
**Team — Aji best placed.** A written sequence showing kill-switch → council →
order preview in order, with the exact clicks. Aji knows every response shape, so
he can write the path that demonstrates the most in the fewest steps.

---

## Later — beyond the hackathon

### 15 · Backend authentication
Currently every route including `POST /api/trade` is unauthenticated. Fine on
localhost, not fine once tunnelled — and it has been tunnelled.

### 16 · Backtest harness
Nothing establishes that TP 60% / SL 200% is profitable, or that this blend of six
personas beats any single one. The theory is sound; the evidence does not exist.

### 17 · Persistence layer
No database. Kill-switch counters, cycle history, and directive audit trail all
live in-process and vanish on restart.

### 18 · Scheduler
The "daily cycle" runs when something calls it. Nothing runs it daily.

### 19 · Assignment handling
The system reasons about assignment risk but has never been through an
assignment. Untested path.

### 20 · Frontend unit tests
`normalizeScreenings`, `toFeedEntry`, `riskBadgeClasses` are pure functions with
no tests. Type check and build are the only gates.

---

## Housekeeping

- Rotate the Alpaca key that was exposed in the predecessor repo's history —
  manual, dashboard-side. Scrubbing history does not un-leak a key.
- Archive or delete `axzss/alpaca-overlay-agent-a2z`.
- Investigate the one permanently skipped test.
- Add `premium <= 0` guard in `exit_manager.py`.

---

## Sequencing note

Items 1–3 close the two ways this can embarrass us: showing fabricated data, and
losing the fundamentals that make the council meaningful. Items 4–6 are what turn
a working system into something that reads as a product. Everything after that is
depth, and depth only pays once the surface holds up.
