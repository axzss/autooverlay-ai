# TESTING

```bash
pytest agent/tests backend/tests -q
# 236 passed, 1 skipped  (237 collected)
```

```bash
cd frontend
npx tsc -p tsconfig.json --noEmit   # type check
npm run build                       # 11/11 pages incl. /icon and /opengraph-image
```

```bash
cd frontend
npx playwright test --reporter=list  # E2E tests (requires both dev servers running)
```

**No test touches the network.** Fundamentals tests use monkeypatched fetchers,
Alpaca tests use mocked clients, and screening tests force mock mode via an
autouse fixture.

## E2E Test Suite (Playwright)

The frontend includes a full E2E regression suite covering the three critical
bugs (BUG 1: same-origin requests, BUG 2: health check via /api rewrite, BUG 3:
cold-load visibility) plus auth gates, console hygiene, asset delivery, and
navigation tests.

**Prerequisites (both must be running):**
```bash
# Terminal 1: Backend
cd backend && PYTHONPATH=.. /root/.venvs/qa/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Frontend (custom Express proxy server)
cd frontend && npm run dev
```

The frontend dev server (`frontend/server.js`) proxies `/api/*` →
`http://127.0.0.1:8000` with `pathRewrite: { '^/api': '/api' }`, fixing the
Next.js 14 `duplex` POST body bug.

```bash
cd frontend && npx playwright test --reporter=list
# Expected: 57 tests pass (auth-gates, bug1/2/3, navigation, console-hygiene, agent-run)
```

**Test structure:**
| File | Tests | Purpose |
|------|-------|---------|
| `bug1-api-origin.spec.ts` | 6 | BUG 1 regression — no cross-origin requests to :8000 |
| `bug2-health-endpoint.spec.ts` | 3 | BUG 2 regression — health check via /api/health |
| `bug3-cold-load-visibility.spec.ts` | 5 | BUG 3A regression — cold load paints content |
| `auth-gates.spec.ts` | 12 | Login, logout, protected pages, CSRF, rate limiting, sidebar auth |
| `navigation.spec.ts` | 1 | Desktop sidebar active marker follows route |
| `console-hygiene.spec.ts` | 10 | No console errors on public/protected pages |
| `agent-run.spec.ts` | 2 | Agent run flow: reasoning panel, line length limit |
| `asset-delivery.spec.ts` | 5 | All pages load their JS/CSS chunks (no 4xx/5xx on _next/*) |

**Known test quirks (these are infrastructure, not app bugs):**
- `workers: 1`, `fullyParallel: false` — sequential execution required because the
  backend's in-process login rate limiter (5/min/IP) is shared across tests.
- `domcontentloaded` not `networkidle` — HMR websocket hangs `networkidle`.
- Auth helper (`authenticateDemoUser`) uses `page.evaluate` → `fetch()` to
  bypass Next.js proxy internals and avoid the `duplex` error.
- Hydration gate (`waitForDashboardHydration`) waits for AuthProvider to
  resolve loading state and CSRF token sync before clicking "Run Agent Now".
- Sidebar tests wait for `aside a.sidebar-nav-item` to appear (loading skeleton
  resolves after AuthProvider.checkAuth completes).
- Rate-limiting test runs LAST with 65s wait to let the 60s window reset.

---

## Suite map with counts

### `agent/tests` — 151 tests

| File | Tests | Covers |
|---|---|---|
| `test_strategies.py` | 27 | Covered call + CSP screening, delta/DTE filters, ≥100-share requirement, collateral, tier policy precedence |
| `test_council.py` | 23 | Consensus scoring, dissent detection per persona, split committees, contrarian bearish dissent on value traps |
| `test_council_handoff.py` | 23 | HANDOFF parsing, tier mapping by volatility, TSLA override, sector cap, delta/DTE clamps |
| `test_config.py` | 17 | Config validation, NaN/±Infinity rejection, magnitude bounds, `STRATEGY_CONFIG_JSON` override |
| `test_graham_persona.py` | 16 | The seven Ch.14 tests against **book thresholds**, INCONCLUSIVE handling, Ch.20 inversion |
| `test_security_regression.py` | 14 | Agent-side portions of the 7 red-team findings |
| `test_exit_and_portfolio.py` | 14 | TP 60% / SL 200% / roll triggers, concentration, cash reserve, sector cap |
| `test_daily_cycle.py` | 11 | **Step ordering**, kill-switch short-circuit, directive structure, provenance, euphoric-market block |
| `test_fundamentals.py` | 10 | Cache hit/expiry/refetch, total-failure degradation to `None`, short-history → INCONCLUSIVE, merge correctness |
| `test_risk_mitigation.py` | 6 | Kill-switch thresholds: drawdown, daily loss, consecutive stop-losses |

### `backend/tests` — 86 tests

| File | Tests | Covers |
|---|---|---|
| `test_security_regression.py` | 18 | Route-side portions of the 7 findings — 422 instead of 500 on hostile input |
| `test_routes.py` | 13 | Core route happy paths and mock fallback |
| `test_strategy_config.py` | 8 | GET/PUT config, validation rejection |
| `test_council_route.py` | 6 | `/council/assess` and `/council/cycle` |
| `test_alpaca_client.py` | 5 | Timeout, network error, `AlpacaAPIError` |
| `test_strategy_screen_engine.py` | 4 | Engine enrichment, isolated from real credentials |
| `test_option_positions.py` | 4 | Live option overlay parsing |
| `test_alpaca_data_client.py` | 4 | Daily bars fetch |
| `test_agent_intents.py` | 4 | `/agent/run` order intent generation |
| `test_council_chaos.py` | 3 | **Alpaca failing mid-flight** during a council cycle |
| `test_agent_route.py` | 3 | `/agent/run` route shape |
| `test_strategy_live_errors.py` | 2 | `live_error` surfacing on the screen route |
| `test_alpaca_error_routes.py` | 2 | Live failure → HTTP 502 rather than silent mock |

---

## The tests that matter most

**`test_daily_cycle.py` — step ordering.** Asserts that when the kill-switch
fires, `steps_run` contains only `kill_switch` and no directives are produced.
This is the single most important safety property in the system: a halted
portfolio must not be able to open a position through any path.

**`test_config.py` — NaN rejection.** Guards security finding S1. A NaN threshold
makes every comparison return `False`, silently disabling the kill-switch while
the UI shows it as active. These tests exist so that failure mode cannot return.

**`test_council_handoff.py` — clamps.** Guards S5. A crafted council report could
inject `delta 0.99`; the clamp holds delta ≤ 0.95 and DTE ≤ 365.

**`test_council_chaos.py` — mid-flight failure.** Alpaca dying halfway through a
council cycle used to be untested. Now it is.

---

## Two hard-won lessons

### Tests that read real credentials are worse than no tests

Screening tests originally read `ALPACA_KEY` from the environment and hit the live
API. They passed on the developer's machine, were non-deterministic, and would
have failed in CI. Fixed with an autouse `monkeypatch` fixture forcing mock mode
(`a5458a5`).

A test that only passes in one environment produces false confidence, which is
worse than the honest signal of having no test at all.

### Test fixtures encode assumptions, and changing them is a visible act

Two `test_daily_cycle.py` failures were fixed by correcting the **test**, not the
module. `daily_cycle` evaluates every symbol in `wanted`, so asserting "the
INITIATE directive is MSFT" broke once SPY was also a candidate; and SPY must be
in the snapshot pool at all for Mr. Market to have a market proxy.

Separately, `test_council.py`'s value-trap fixture had to gain full Ch.14 history
(sales, 10-year earnings, 20-year dividends) once INCONCLUSIVE stopped being
free — a stock Graham is *supposed* to love must actually carry the history his
tests require.

Both are legitimate fixture corrections. Both are also indistinguishable, from a
diff alone, from weakening the suite. Rule in `JOBDESK.md`: **if you modify an
existing test, say so explicitly** in the commit message and the report.

---

## What is NOT covered

Being specific here is more useful than a coverage percentage.

| Gap | Risk |
|---|---|
| **No E2E test** | Nothing verifies the UI actually renders. A page can return 200 while showing an error boundary |
| **No visual verification, ever** | `browser_exec` could not attach, Playwright is not installed, headless Chrome hit sandbox → `DISPLAY` → websocket-origin walls in sequence. Nobody has confirmed the UI looks correct — and a brand mark, four charts and a full framer-motion pass have now shipped on top of that. Motion and charts are exactly where a type check tells you least: an inverted domain, unreadable contrast, wrong easing or a crawling stagger all compile perfectly |
| **`prefers-reduced-motion` untested** | Implemented in every motion primitive, never exercised with the OS setting enabled |
| **`_pick_option_contract` untested** | The backend's most intricate function — OCC parsing, abs-delta filtering, DTE windowing, sorting — has zero coverage. Two sign bugs in it reached master and were caught by human diff review |
| **No backtest** | Nothing establishes that TP 60% / SL 200% is profitable. Theory only |
| **No load or concurrency test** | Behaviour under parallel cycle requests is unknown |
| **No real assignment path** | Assignment risk is reasoned about, never exercised |
| **Frontend has no unit tests** | Type check + build only. `normalizeScreenings`, `toFeedEntry`, `riskBadgeClasses` are untested |
| **`premium <= 0` in exit_manager** | ~~Would divide by zero; no test, no guard~~ — **guard exists** at `exit_manager.py:102`, verified 29 Aug. Still no test asserting it |
| **Kill-switch persistence** | The consecutive-stop-loss counter is now produced within a cycle (`_consecutive_stop_losses`) and covered by two tests, but does **not** accumulate across cycles. Needs the W1 `exit_event` ledger |
| **Fixtures drifting from production payload shape** | The lesson from finding A3: `test_drawdown_breach_halts` passed for eighteen days because its fixture omitted `market_value`, so test and production took **opposite branches** of the drawdown control. Any fixture missing a field the broker always sends is testing dead code |


---

## Adding tests

**Agent layer** — no network, no credentials. Monkeypatch any fetcher, use
`tmp_path` for caches.

**Backend** — use FastAPI `TestClient`, mock `AlpacaClient`. Cover the mock path
*and* the live-failure path, since the two used to be indistinguishable from the
outside.

**Both suites, always.** `agent/config.py` and the council modules are imported by
backend routes, so an agent-layer change can break backend tests:

```bash
pytest agent/tests backend/tests -q
```

---

## The one skipped test

One test is skipped, consistently, across all runs. It has been skipped since the
suite was built and its reason has not been re-examined. Worth a look — a
permanently skipped test is either obsolete or a hidden gap.
