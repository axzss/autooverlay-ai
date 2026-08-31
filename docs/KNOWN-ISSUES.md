# KNOWN-ISSUES

Open defects and unfinished work, verified present at the time of writing. Ordered
by how much damage each one can do.

Legend: **owner** is per `JOBDESK.md`.

---

## 0 · Resolved 29 Aug — W0 safety-floor fixes

Four findings from the audit in `BRIEF-AGENT-V2-REVIEW.md`, all fixed and
regression-tested. Kept here because the *class* of each bug matters more than
the instance.

| # | Finding | Fix |
|---|---|---|
| A | `overlay_only_drawdown` assigned overlay equity to **both** sides of the drawdown ratio, so `dd` was always exactly `0.0` | Real overlay high-water mark via `portfolio_state["overlay_peak_equity"]`; NAV fallback with a note when absent |
| A1 | Overlay sum ran over the **equity book** — long stock counted as overlay collateral, so the branch fired on every live account | `_is_short_option()` — OCC symbol **and** negative qty; `daily_cycle` now passes `positions + open_options` |
| A2 | `overlay_only_drawdown=False` was unsettable — `_cfg_get` rejects bools and returned the default | New `_cfg_flag()` for boolean config; `_cfg_get` left strict for numeric thresholds |
| A3 | `test_drawdown_breach_halts` passed because its fixture **omitted `market_value`**, taking the opposite branch from production | Fixture now production-shaped; 6 new tests in `test_risk_mitigation.py` |
| B | Backend passes **current** equity as `peak_equity`, and nothing anywhere produced `consecutive_stop_losses` | Supplied peak treated as a *candidate max*; `_consecutive_stop_losses()` derives the counter from exit decisions, with a post-exit kill-switch recheck |
| B1 | `8fc3928` added an `equity` override to `_build_portfolio_state`, so both sides of the ratio became `account["equity"]` again — the mock cycle stopped halting and finding B was live for a second time | Caller may **raise** the mark, never lower it, and never supply it outright. Persistent `agent/state/peak.py` owns the mark; a caller-supplied `peak_equity` is folded in as an *observation* |
| B2 | Execution gate derived its peak from `max(equity, last_equity)` — a **two-day window**. Same book, opposite verdict depending on which calendar day the peak fell on: `equity 55000/last 55100 → halted=False`, `equity 55000/last 200000 → halted=True` | `backend/app/risk/state._peak_marks()` reads the persistent store, keyed per account; degrades to the two-day window only when the store is unreachable, and labels it `source="absent"` |
| B3 | `overlay_peak_equity` was never supplied by any caller — `grep` found it only in agent-layer tests, so the overlay basis was unreachable in production and every evaluation silently fell back to NAV | Gate computes overlay collateral via the shared `_is_short_option` rule and observes it into the store |
| B4 | Gate discarded `notes` and `drawdown_basis`, the two fields added specifically to make a NAV fallback visible | Notes ride along with breaches as `note: …` entries in `halt_reasons` |
| C | `with ThreadPoolExecutor(...)` → `shutdown(wait=True)` on exit, so the timeout fired only **after** the worker it was meant to abandon finished. Measured 60.4s against a 1.0s budget | One executor per batch, `as_completed(timeout=budget)`, `shutdown(wait=False)`, `except Exception` narrowed |

**The pattern worth naming.** A, B, B1 and B2 are four routes into one defect:
*the drawdown denominator was derived from the numerator.* Each fix closed one
route and the next commit found another. What closed the class was moving the
mark out of caller control entirely — a caller can raise it, never lower it,
never supply it. Regression coverage: `agent/tests/test_peak_store.py` (21) and
`backend/tests/test_risk_state_peak.py` (11).


Live Layer 1 status before W0: drawdown **dead twice over**, stop-loss counter
**never fed**, single-day loss the only working trigger. Verified after:

```
1) NAV drawdown -72.5%            halted=True  basis=nav      'nav drawdown -72.50% breaches -5.00%'
3) 3 stop-losses, no override     halted=True  observed=3     '3 consecutive stop-losses reached'
4) NAV flat, overlay -60%         halted=True  basis=overlay  'overlay drawdown -60.00% breaches -5.00%'
```

`kill_switch` now also returns `notes: list[str]` and `drawdown_basis:
"nav"|"overlay"`, so a fallback is visible rather than silent. Two existing
whole-dict-equality assertions were relaxed to field assertions — flagged in the
commit message per `JOBDESK.md`.

**The lesson worth keeping:** finding A had a *passing test* for eighteen days.
A green suite is not evidence a control works when the fixture and production
take different branches.

**Still open from the same audit:** the `/tmp` fundamentals cache is
world-writable and feeds persona scoring — the same trust boundary as security
finding S5, one step earlier in the pipeline. See #1 below.

---


## 1 · Fundamentals cache is ephemeral **and world-writable** — HIGH

**Owner:** AI engineering · **File:** `agent/council/fundamentals.py:26`

Cache lives at `/tmp/fundamentals_cache.json`. Two distinct problems.

**Durability.** On any container or VPS restart it is gone. The council silently
drops from HIGH to LOW confidence: NVDA (68.0) and MSFT (60.2) revert from
ACCUMULATE to HOLD, every P/E and dividend figure disappears, and the report on
disk no longer matches what the running system produces. Nothing warns you. If
this happens mid-demo, the numbers on screen contradict the numbers in the report.

**Trust (added 29 Aug).** `/tmp` is mode `0o41777` — shared and world-writable —
and the path is fixed and predictable. Any process on the box can pre-create or
overwrite that file, and the loader validates nothing beyond a JSON parse and a
TTL check. Fundamentals feed persona scoring, and persona output drives the
HANDOFF tier policy, so this is the same trust boundary as security finding S5
(a crafted report injecting `delta 0.99`) reached one step earlier in the
pipeline. S5 was rated worth fixing; this was not tracked at all. The sticky bit
prevents deleting another user's file, not creating it first, and offers nothing
against anything running as the same user — `root`, on this box.

**Fix:** move the cache to `docs/.cache/fundamentals.json` (already gitignored),
keep the 24h TTL and atomic writes, fall back to `/tmp` if the repo path is not
writable, validate entry shape on load rather than trusting parsed JSON, and
expose `data_age_hours`, `stale` and `source: "cache"|"live"` on the merged
snapshot so consumers — and persona bullets — can tell fresh from stale.

This was written and then removed in a reverted batch. It needs redoing.


---

## 2 · `_order_intents` cannot produce a real contract — HIGH

**Owner:** backend · **File:** `backend/app/routes/agent.py`

`_order_intents()` reads `params.get("option_symbol")` and
`params.get("limit_price")` from each `INITIATE` directive. But `INITIATE`
directives from `daily_cycle.py` carry **tier policy** — `strategy_allowed`,
`delta_min/max`, `size` — not a resolved contract.

Verified result: `option_symbol` is always `null`, `limit_price` is always `null`,
and `type` always falls back to `"market"`.

Any UI table with strike / expiry / premium columns renders `—` in all three. The
order-preview feature looks half-finished because functionally it is.

**Two possible fixes:**
- (a) `_order_intents` resolves the contract itself from the Alpaca option chain
  using the tier's delta band and DTE window. Cleaner — order construction is a
  backend concern.
- (b) `daily_cycle` populates concrete contracts into `params`. Pushes
  broker-specific detail into the agent layer.

Recommendation: (a).

---

## 3 · `specials/BACKEND_FRONTEND_API.md` contradicts the code — HIGH

**Owner:** backend

Three fields documented differently from what the API returns:

| Field | Document says | **Actual (verified)** |
|---|---|---|
| `tier` | `"CORE"` | `"LOW"` \| `"MID"` \| `"HIGH"` |
| `consensus_score` | `7.5` (0–10 scale) | `53.6` (**0–100 scale**) |
| `delta_min` | `-0.2` (negative) | `0.1` (**positive** — short option delta) |

Also: `dissent[].why` is a `string[]`, not a string.

This is not academic. A frontend brief was written from this document, and UI
built to it would have every colour threshold and number format wrong. See
`docs/API-CONTRACT.md` for verified shapes.

**Fix:** update the document, or change the backend if the document reflects the
intended design.

---

## 4 · Council handoff is parsed markdown, unauthenticated — MEDIUM

**Owner:** AI engineering · **File:** `agent/council/handoff.py`

Tier policy is extracted from `docs/council_report.md` with regular expressions.

Two problems. **Fragility:** any change to the report's formatting silently
degrades the policy to defaults, losing the council's intent with no error.
**Trust:** this was security finding S5 — a crafted report could inject
`delta 0.99`. It is now clamped (delta ≤ 0.95, DTE ≤ 365), which limits the damage
but does not make the channel trustworthy.

**Fix:** emit machine-readable JSON alongside the human report and parse that.
The red team's stronger recommendation — cryptographically sign the report before
trusting its HANDOFF section — is also still open.

---

## 5 · Mr. Market has no hysteresis — MEDIUM

**Owner:** AI engineering · **File:** `agent/council/mr_market.py`

`classify_market_mood()` recomputes the regime on every call from run-up and
realised volatility. Two consecutive requests can produce different moods on
noise, and because `euphoric` blocks new entries, the system can flip between
"screening" and "blocked" without the market having meaningfully changed.

**Fix:** accept an optional `previous_mood` and require the threshold to be
exceeded by a margin before switching away from an established regime.

---

## 6 · Graham INCONCLUSIVE counts as neutral — MEDIUM

**Owner:** AI engineering · **Files:** `graham_principles.py`, `personas.py`

Four of the seven Ch.14 tests need 10–20 years of history that free data sources
do not reliably supply, so they return INCONCLUSIVE. INCONCLUSIVE currently drops
out of the Graham blend entirely — scored as neutral.

Effect: the council is biased **bullish** on exactly the names with the thinnest
data. Being rigorous about criteria while being sloppy about missing data is worse
than being uniformly crude.

**Fix:** weight INCONCLUSIVE as a half-fail (0.5), giving `FAIL < INCONCLUSIVE <
PASS`, and state in each affected bullet that the penalty came from unverifiable
data rather than a failed criterion. Measured effect when previously implemented:
SPY/QQQ −1.2, NVDA 68.0 → 67.6, JPM 52.0 → 51.6.

Also reverted; needs redoing.

---

## 7 · Two "Run Agent" entry points, one endpoint — LOW

**Owner:** frontend

Both `/dashboard` (`AgentControl`) and `/terminal` now call `/api/agent/run`. The
intended split is a compact trigger with a summary on the dashboard and the
detailed view in Terminal, but a user could still wonder why two buttons exist and
why their results differ (they differ only by call time).

**Fix:** decide the division explicitly, or remove one.

Both are already honest about what comes back: kill-switch HALT renders with its
reasons, an empty `order_intents` list says so, and null `option_symbol` /
`limit_price` render as "contract pending" / "no limit set" rather than a
fabricated strike — because with issue #2 open, that is the normal case.

---

## 8 · No backend authentication — MEDIUM (context-dependent)

**Owner:** backend

Every endpoint is unauthenticated, including `POST /api/trade`. Any caller who can
reach the port can submit an order.

Acceptable for a localhost demo. **Not acceptable when exposed** — and it has been
exposed via Cloudflare quick tunnels during development, which are public URLs.

**Fix:** at minimum, bind to localhost and never tunnel the backend port. Better:
a shared-secret header on mutating routes.

---

## 9 · `premium <= 0` unguarded in exit manager — **NOT A DEFECT** (closed 29 Aug)

**Owner:** AI engineering · **File:** `agent/exit_manager.py`

This entry was wrong. The guard exists at `exit_manager.py:102`:

```python
if initial <= 0:
    trace.append(f"initial premium ${initial:.2f} invalid — cannot evaluate P&L rules ✗")
    pnl_capture_pct = None
    loss_multiple = None
```

Verified by calling `evaluate_position` with `initial_premium` of `0.0`, `-1.0`
and `None` — all three return cleanly, and delta/DTE roll rules still fire
(`prem=0, delta .55 → ROLL`). No `ZeroDivisionError` is reachable.

Kept as a record: this item sat on the roadmap and in two layer docs as
outstanding work that did not exist. **Audit the code before scheduling the
fix** — the reverse of finding A, where a doc claimed a control worked and it
did not.


---

## 10 · No visual verification, no E2E test — MEDIUM (and now worse)

**Owner:** frontend + QA

Nobody has ever confirmed the UI renders correctly — not by eye, not by
automation. Attempts failed in sequence: `browser_exec` could not attach
(`chrome-not-running`), Playwright is not installed in any venv, and headless
Chrome hit root-sandbox → missing `DISPLAY` → websocket-origin-403 walls.

`tsc` clean + `npm run build` passing + HTTP 200 is not the same as "it looks
right". A page can return 200 while rendering an error boundary.

**Raised from LOW because motion has landed on top of it.** A brand mark, four
charts and a full framer-motion pass now sit on a layout nobody has seen.
Animation is the worst possible category for this gap: a type check cannot detect
an easing curve that feels wrong, a stagger that crawls, a drawer sliding from
the wrong edge, or a `layoutId` marker jumping instead of gliding. Every one of
those compiles perfectly.

**Fix:** open the tunnel in a real browser and check by hand — faster than fixing
headless Chrome in this box. Then add one Playwright smoke test:
dashboard → council → terminal.

Also untested: `prefers-reduced-motion`. It is implemented in every primitive but
has never been exercised with the OS setting actually enabled.

---

## 10b · Motion bundle cost is unmitigated — LOW

**Owner:** frontend

framer-motion adds roughly 34 kB to each page's first load (`/assets` 111→145 kB,
`/council` 112→146 kB, `/terminal` 115→149 kB, `/dashboard` 221→255 kB). Shared JS
is unchanged at 87.3 kB, so this is per-route weight.

Acceptable for a hackathon demo on a local network; not something to leave
unexamined if the app is ever served to real users on mobile.

**Fix if it matters:** `LazyMotion` with `domAnimation` features, or split the
primitives module so pages that only need `Reveal` do not pull the full library.

---

## 11 · Kill-switch state is not persisted — HIGH

**Owner:** AI engineering

**Reclassified from LOW on 29 Aug.** The original entry said the
consecutive-stop-loss counter "is recomputed from portfolio state each cycle" and
that a restart loses it. The audit found something worse: **nothing computed it
at all.** `_build_portfolio_state` read it only from caller overrides, and the
one live caller (`backend/app/routes/council.py`) never sets it — so the trigger
was unreachable in production regardless of restarts.

W0 added `_consecutive_stop_losses()`, which derives the count from this cycle's
exit decisions and re-checks the kill-switch after exit evaluation. That makes
the trigger reachable, but it is **within-cycle only**: three stop-losses spread
across three separate cycles still do not accumulate.

**Remaining fix:** the W1 `exit_event` ledger. Count trailing `STOP_LOSS` rows
across cycles, reset on any non-stop exit. Until then the counter is a floor, not
the true value.


---

## 12 · One test permanently skipped — LOW

**Owner:** QA

One test has been skipped in every run since the suite was built and its reason
has not been re-examined. A permanently skipped test is either obsolete or a
hidden gap; either way it should not sit there silently.

---

## 13 · Four dead `Providers.tsx` stubs — LOW

**Owner:** frontend

`app/{assets,dashboard,settings,terminal}/Providers.tsx` each contain a
seven-line component that returns `children` unchanged, and none of them is
imported anywhere. Harmless, but they are noise for the next person reading the
route folders.

**Fix:** delete them, or give them a purpose.

---

## Resolved — kept for context

| Issue | Resolution |
|---|---|
| Alpaca key in git history (predecessor repo) | History scrubbed, fresh clone verified, this repo started clean |
| `APCA-API-SECRET` header typo → every live call 401 | Fixed to `APCA-API-SECRET-KEY`, verified live |
| Frontend calling bare paths → every endpoint 404 | All paths prefixed `/api`; `/health` stays bare |
| Dev proxy stripping the `/api` prefix | Rewrite corrected, `/api/health` mapped to bare `/health` |
| Content rendering behind the fixed sidebar | `lg:ml-[240px]` on all five page wrappers |
| Header nav missing the Council link entirely | Duplicate header nav removed; Sidebar is the single source |
| Tests reading real credentials | Autouse `monkeypatch` forces mock mode |
| 7 penetration-test findings | All fixed, 32 regression tests |
| Mock account id `PA3CBCJTGBJS` in fixtures | Replaced with `MOCK_ACCOUNT_1` |
| `ThoughtProcess` rendering a fabricated executed trade and $120 yield | Replaced with real `reasoning_trace` from `/api/agent/run`, or an empty state |
| `AgentControl` button with no `onClick` — never wired | Calls `api.runAgent()` via `AgentRunProvider`, shared with the reasoning panel |
| `ActiveOverlayContracts` hardcoded `SPY 520c 15Mar24 / $125.00` row | Filters real option positions, parses OCC symbols for strike/expiry/DTE |
| `AgentConfiguration` — second config panel whose Save called `alert()` and persisted nothing | Removed; `StrategyConfigCard` owns every tunable it claimed |
| 11 never-rendered mockup files (`ActiveOverlay`, `TradeLog`, `OverlayControl`, `AgentTerminal`, `Dashboard`, `StrategyCard`, `ai/`, `portfolio/`, `strategy/`, `trading/`, `ui/`) | Deleted, −1290 lines |
| No brand identity — no favicon, no mark, no OG image | `brand/Logo.tsx`, `app/icon.tsx`, `app/opengraph-image.tsx`, OG/Twitter metadata |
| `recharts` in dependencies but unused | Four charts added: equity sparkline, score gauge, allocation donut, yield bars |
