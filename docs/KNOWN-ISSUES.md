# KNOWN-ISSUES

Open defects and unfinished work, verified present at the time of writing. Ordered
by how much damage each one can do.

Legend: **owner** is per `JOBDESK.md`.

---

## 1 · Mockup components render fabricated data — CRITICAL

**Owner:** frontend · **File:** `frontend/app/components/ThoughtProcess.tsx`

The component contains a hardcoded log array, rendered on `/dashboard`:

```
10:00:14  MCP     Executing SELL to OPEN 1 Contract SPY 565C 09/04.
10:00:16  SYSTEM  Order Confirmed. Yield harvested: $120.00. Returning to sleep.
```

None of this happened. To anyone watching a demo it reads as the agent having
just executed a trade and collected $120. This is the single biggest credibility
risk in the project — worse than a broken feature, because a broken feature is
honest.

**Scope is wider than one file.** 20 of ~28 components in
`frontend/app/components/` have no `lib/api` import at all. Confirmed mockups
still in the tree: `ActiveOverlayContracts.tsx`, `ThoughtProcess.tsx`,
`TradeLog.tsx`, `PortfolioStats.tsx`, `AssetHoldings.tsx`, `RecentHistory.tsx`,
`ActiveOverlay.tsx`, `OverlayControl.tsx`, `AgentTerminal.tsx`, `Dashboard.tsx`,
`StrategyCard.tsx`, `AgentConfiguration.tsx`.

Root cause: two generations of components coexist — mockups from the design phase
and wired components from integration — with no record of which is which. The
dashboard renders a mix of both in the same column (`AgentStatusCard` is wired,
`AgentControl` and `ThoughtProcess` are not).

**Fix:** replace `ThoughtProcess` content with real `reasoning_trace` from
`/api/agent/run`, or delete it. An empty panel is better than a lying one.

---

## 2 · Fundamentals cache is ephemeral — HIGH

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

## 3 · `_order_intents` cannot produce a real contract — HIGH

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

## 4 · `specials/BACKEND_FRONTEND_API.md` contradicts the code — HIGH

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

## 5 · Council handoff is parsed markdown, unauthenticated — MEDIUM

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

## 6 · Mr. Market has no hysteresis — MEDIUM

**Owner:** AI engineering · **File:** `agent/council/mr_market.py`

`classify_market_mood()` recomputes the regime on every call from run-up and
realised volatility. Two consecutive requests can produce different moods on
noise, and because `euphoric` blocks new entries, the system can flip between
"screening" and "blocked" without the market having meaningfully changed.

**Fix:** accept an optional `previous_mood` and require the threshold to be
exceeded by a margin before switching away from an established regime.

---

## 7 · Graham INCONCLUSIVE counts as neutral — MEDIUM

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

## 8 · Two "Run Agent" buttons, one endpoint — MEDIUM

**Owner:** frontend

`AgentControl.tsx` on `/dashboard` has a `<button>` with **no `onClick` at all** —
it was never wired, not broken. Meanwhile Terminal's "Run agent (preview)" button
calls `api.runAgent()` correctly.

Once both work, two buttons hit the same endpoint on two pages and a user will
reasonably wonder why results differ (they differ only by call time).

**Fix:** wire `AgentControl` to `api.runAgent()`, and decide the division —
Dashboard as a compact trigger with a summary, Terminal as the detailed view. Or
remove one.

The wired version must be honest about reality: show `risk_summary.halted` with
its reason when the kill-switch is active, and "no order intents" when the list is
empty — because with issue #3 open, empty is the normal case.

---

## 9 · No backend authentication — MEDIUM (context-dependent)

**Owner:** backend

Every endpoint is unauthenticated, including `POST /api/trade`. Any caller who can
reach the port can submit an order.

Acceptable for a localhost demo. **Not acceptable when exposed** — and it has been
exposed via Cloudflare quick tunnels during development, which are public URLs.

**Fix:** at minimum, bind to localhost and never tunnel the backend port. Better:
a shared-secret header on mutating routes.

---

## 10 · `premium <= 0` unguarded in exit manager — LOW

**Owner:** AI engineering · **File:** `agent/exit_manager.py`

Premium-capture percentage divides by initial premium with no zero check. An
illiquid option quoting zero would raise `ZeroDivisionError` mid-cycle.

**Fix:** `if premium <= 0: return MONITOR` and skip exit evaluation.

---

## 11 · No visual verification, no E2E test — LOW (but persistent)

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

## 12 · Kill-switch state is not persisted — LOW

**Owner:** AI engineering

The consecutive-stop-loss counter is recomputed from portfolio state each cycle. A
process restart resets it silently, so three stop-losses spread across a restart
never trigger the halt.

**Fix:** persist the counter, or derive it from order history rather than
in-process state.

---

## 13 · One test permanently skipped — LOW

**Owner:** QA

One test has been skipped in every run since the suite was built and its reason
has not been re-examined. A permanently skipped test is either obsolete or a
hidden gap; either way it should not sit there silently.

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
