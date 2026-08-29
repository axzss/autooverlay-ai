# KNOWN-ISSUES

Open defects and unfinished work, verified present at the time of writing. Ordered
by how much damage each one can do.

Legend: **owner** is per `JOBDESK.md`.

---

## 1 · Fundamentals cache is ephemeral — HIGH

**Owner:** AI engineering · **File:** `agent/council/fundamentals.py`

Cache lives at `/tmp/fundamentals_cache.json`. On any container or VPS restart it
is gone.

Consequence: the council silently drops from HIGH to LOW confidence. NVDA (68.0)
and MSFT (60.2) revert from ACCUMULATE to HOLD, every P/E and dividend figure
disappears, and the report on disk no longer matches what the running system
produces. Nothing warns you — the degradation is invisible.

If this happens mid-demo, the numbers on screen contradict the numbers in the
report.

**Fix:** move the cache to `docs/.cache/fundamentals.json` (already gitignored),
keep the 24h TTL and atomic writes, fall back to `/tmp` if the repo path is not
writable, and expose `data_age_hours` + `stale` on the merged snapshot so
consumers can tell fresh from stale.

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

## 9 · `premium <= 0` unguarded in exit manager — LOW

**Owner:** AI engineering · **File:** `agent/exit_manager.py`

Premium-capture percentage divides by initial premium with no zero check. An
illiquid option quoting zero would raise `ZeroDivisionError` mid-cycle.

**Fix:** `if premium <= 0: return MONITOR` and skip exit evaluation.

---

## 10 · No visual verification, no E2E test — LOW (but persistent)

**Owner:** frontend + QA

Nobody has ever confirmed the UI renders correctly — not by eye, not by
automation. Attempts failed in sequence: `browser_exec` could not attach
(`chrome-not-running`), Playwright is not installed in any venv, and headless
Chrome hit root-sandbox → missing `DISPLAY` → websocket-origin-403 walls.

`tsc` clean + `npm run build` passing + HTTP 200 is not the same as "it looks
right". A page can return 200 while rendering an error boundary.

**Fix:** open the tunnel in a real browser and check by hand — faster than fixing
headless Chrome in this box. Then add one Playwright smoke test:
dashboard → council → terminal.

---

## 11 · Kill-switch state is not persisted — LOW

**Owner:** AI engineering

The consecutive-stop-loss counter is recomputed from portfolio state each cycle. A
process restart resets it silently, so three stop-losses spread across a restart
never trigger the halt.

**Fix:** persist the counter, or derive it from order history rather than
in-process state.

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
