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

Why now: the logo, four charts **and a full framer-motion pass** have all landed
unverified. Animation is where a type check tells you least — wrong easing, a
crawling stagger, a drawer sliding from the wrong edge and a `layoutId` marker
that jumps instead of gliding all compile perfectly. Everything built on top of
an unverified layout inherits its errors.

Check while you are there: toggle OS reduced-motion and confirm the UI goes still.

### 3 · Resolve `_order_intents`
**Backend.** Now largely done: `_pick_option_contract` resolves `option_symbol`
and `limit_price` from the Alpaca option chain using the tier's delta band and DTE,
with abs-delta comparison for puts. Remaining gap: it returns `None` when
`is_configured()` is false, so **the feature is invisible in mock mode** — a demo
without live credentials still shows "contract pending". Consider a mock option
chain so the order preview can be demonstrated offline.

Also unaddressed: `_pick_option_contract`, `_occ_expiration` and `_tier_bands`
have **no test coverage at all**, and two sign bugs in that function already
reached master and were caught by human diff review rather than by tests.

---

## Next — makes the demo land

### 4 · Reconcile `BACKEND_FRONTEND_API.md`
**Backend.** Mostly done: `tier` (`LOW`/`MID`/`HIGH`), the 0–100 `consensus_score`
scale, and the short-option absolute `delta_min`/`delta_max` semantics are now
documented. Still open: `dissent[].why` is a list of strings, not a single string.

### 5 · Tests for `_pick_option_contract`
**Backend.** The most intricate function in the backend has zero coverage, and two
sign bugs in it already reached master. All testable offline by monkeypatching
`get_option_snapshots`:

- negative put delta is selected (regression for the abs-delta filter fix)
- sorting picks the candidate nearest the band centre with puts and calls mixed
- candidates outside the DTE window are excluded, and `dte == 0` is rejected
- snapshots with no `greeks.delta`, or with both bid and ask `None`, are skipped
- malformed OCC symbols are skipped rather than raising
- `_tier_bands` returns `(None, None, None)` when `delta_min >= delta_max`

### 6 · Playwright E2E smoke test
**Frontend + QA.** One run: dashboard → council → terminal, asserting no console
errors and that key panels render. This catches the class of regression a type
check cannot, and it is the automated half of item 2.

### 7 · Frontend polish pass
**Frontend.** Now that the structure is settled: skeleton and empty states audited
on every page, mobile viewport walked end to end, Lighthouse run, contrast ratios
and focus states checked. `aria-label`s exist on icon-only buttons; nothing else
has been audited.

Motion items belong here too: confirm reduced-motion actually stills the UI, and
consider `LazyMotion` if the ~34 kB per-page cost matters.

Also delete the four dead `Providers.tsx` stubs in the route folders, and decide
the Dashboard vs Terminal split for the two "run agent" entry points.

### 8 · Demo script
**Team — Aji best placed.** A written sequence showing kill-switch → council →
order preview in order, with the exact clicks. Aji knows every response shape, so
he can write the path that demonstrates the most in the fewest steps.

Note: order preview only shows real contracts with live credentials — decide
whether the demo runs live or needs a mock option chain first.

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

### 14 · Frontend unit tests
**Frontend.** `normalizeScreenings`, `toFeedEntry`, `riskBadgeClasses` are pure
functions with no coverage. Type check and build are the only gates today.

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

---

## Housekeeping

- Rotate the Alpaca key that was exposed in the predecessor repo's history —
  manual, dashboard-side. Scrubbing history does not un-leak a key.
- Archive or delete `axzss/alpaca-overlay-agent-a2z`.
- Investigate the one permanently skipped test.
- Add `premium <= 0` guard in `exit_manager.py`.

---

## Sequencing note

The frontend build-out is **done**: fabricated data removed, `AgentControl` wired
honestly, brand identity built, four charts landed, framer-motion applied across
every page. See `MEMORY.md` 2026-08-29.

What remains at the top is the last way this can fail without anyone touching it
(the ephemeral fundamentals cache), and the last thing nobody has ever checked
(whether the UI actually looks right — now with animation stacked on top of it).
Everything after that is depth, and depth only pays once the surface holds up.

Note on shape: the frontend has run ahead of its verification for three
consecutive days. Each pass was type-checked, built and HTTP-probed, and none of
it has been seen. That is a coverage problem, not a code problem, and item 2
closes it in about ten minutes of someone's attention.

