# ROADMAP

Ordered by value delivered per unit of work, not by how interesting the work is.

---

## Now — before any demo

### 1 · Persist the fundamentals cache
**AI engineering.** Move `/tmp/fundamentals_cache.json` → `docs/.cache/fundamentals.json`
(already gitignored), keep 24h TTL and atomic writes, `/tmp` fallback if the repo
path is read-only, and add `data_age_hours` + `stale` to the merged snapshot.

Why first: a restart silently drops the council from HIGH to LOW confidence and
reverts NVDA/MSFT to HOLD. This is the only way the demo fails without anyone
touching anything.

### 2 · Verify the UI visually
**Frontend.** Nobody has ever looked at it. Open the tunnel in a real browser,
walk all five pages, confirm no console errors — faster than fixing headless
Chrome in this environment. `tsc` clean plus a passing build plus HTTP 200 does
not tell you a page renders correctly.

Why now: the logo and four charts just landed unverified. If the layout is wrong,
everything built on top of it is wrong too.

### 3 · Resolve `_order_intents`
**Backend.** Make it produce a real contract: resolve `option_symbol` and
`limit_price` from the Alpaca option chain using the tier's delta band and DTE.
The frontend already renders "contract pending" / "no limit set" honestly, but the
order-preview feature only becomes interesting once those fields are real.

---

## Next — makes the demo land

### 4 · Reconcile `BACKEND_FRONTEND_API.md`
**Backend.** Fix `tier`, `consensus_score` scale, `delta_min` sign, and
`dissent[].why` type. A contract document that disagrees with the code is worse
than no document — it produces confidently wrong client code.

### 5 · Playwright E2E smoke test
**Frontend + QA.** One run: dashboard → council → terminal, asserting no console
errors and that key panels render. This catches the class of regression a type
check cannot, and it is the automated half of item 2.

### 6 · Frontend polish pass
**Frontend.** Now that the structure is settled: skeleton and empty states audited
on every page, mobile viewport walked end to end, Lighthouse run, contrast ratios
and focus states checked. `aria-label`s exist on icon-only buttons; nothing else
has been audited.

Also delete the four dead `Providers.tsx` stubs in the route folders, and decide
the Dashboard vs Terminal split for the two "run agent" entry points.

### 7 · Demo script
**Team — Aji best placed.** A written sequence showing kill-switch → council →
order preview in order, with the exact clicks. Aji knows every response shape, so
he can write the path that demonstrates the most in the fewest steps.

---

## Then — depth the judges will probe

### 8 · Mr. Market hysteresis
**AI engineering.** Accept `previous_mood`, require a margin before switching
regime. Stops the euphoric-block from flickering on noise.

### 9 · Graham INCONCLUSIVE as half-fail
**AI engineering.** `FAIL < INCONCLUSIVE < PASS`, with each affected bullet
stating the penalty came from unverifiable data. Removes the bullish bias on
thin-data names. Known effect: SPY/QQQ −1.2, NVDA −0.4, JPM −0.4.

### 10 · Structured council handoff
**AI engineering.** Emit JSON alongside the markdown report and parse that
instead of regex-matching prose. Then consider signing it, per the red team's
residual recommendation.

### 11 · Deeper fundamentals coverage
**AI engineering.** Source 10-year earnings and 20-year dividend history so Ch.14
tests 3, 4 and 5 can actually be decided instead of returning INCONCLUSIVE. This
is the difference between a Graham persona that has an opinion and one that
mostly shrugs.

### 12 · Real sector classification
**AI engineering.** `sector_cap_group` is a hardcoded tuple of four tickers.
Replace with actual sector data so the correlation cap generalises beyond the
current universe.

### 13 · Frontend unit tests
**Frontend.** `normalizeScreenings`, `toFeedEntry`, `riskBadgeClasses` are pure
functions with no coverage. Type check and build are the only gates today.

---

## Later — beyond the hackathon

### 14 · Backend authentication
Currently every route including `POST /api/trade` is unauthenticated. Fine on
localhost, not fine once tunnelled — and it has been tunnelled.

### 15 · Backtest harness
Nothing establishes that TP 60% / SL 200% is profitable, or that this blend of six
personas beats any single one. The theory is sound; the evidence does not exist.

### 16 · Persistence layer
No database. Kill-switch counters, cycle history, and directive audit trail all
live in-process and vanish on restart.

### 17 · Scheduler
The "daily cycle" runs when something calls it. Nothing runs it daily.

### 18 · Assignment handling
The system reasons about assignment risk but has never been through an
assignment. Untested path.

---

## Housekeeping

- Rotate the Alpaca key that was exposed in the predecessor repo's history —
  manual, dashboard-side. Scrubbing history does not un-leak a key.
- Archive or delete `axzss/alpaca-overlay-agent-a2z`.
- Investigate the one permanently skipped test.
- Add `premium <= 0` guard in `exit_manager.py`.

---

## Sequencing note

The frontend items that were 1, 3, 4 and 5 here are **done** — fabricated data
removed, `AgentControl` wired honestly, brand identity built, four charts landed.
See `MEMORY.md` 2026-08-29.

What remains at the top is the last way this can fail without anyone touching it
(the ephemeral fundamentals cache), and the last thing nobody has ever checked
(whether the UI actually looks right). Everything after that is depth, and depth
only pays once the surface holds up.

