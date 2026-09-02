# BRIEF-BACKEND-V2 — Scale-Up Mandate for the Backend Agent Team

**Status note 2026-09-02:** `/api/agent/run/{run_id}` and `/api/bot/*` autonomous-scheduler surfaces are implemented and reflected in `docs/BACKEND_FRONTEND_API.md` and `docs/API-CONTRACT.md`. `/api/bot/status` now documents automatic first-cycle startup behavior.

**Issued by:** Orchestrator / CTO
**Owner:** Backend (`AjiNurAji`) — `backend/**`, `specials/**`
**Out of scope:** `frontend/**`, `agent/**`. New capability is exposed by adding routes, adapters and modules under `backend/`. If a route contract changes, announce it and update `specials/BACKEND_FRONTEND_API.md` in the same commit (JOBDESK rule).
**Window:** D-6 (29 Aug) → D0 (4 Sep, 15:00 UTC submission). Freeze 06:00 UTC on D0.

---

## 0 · Why this brief exists

`docs/JOBDESK.md` currently says: *Backend — Complete — 11 routes, zero TODOs, chaos coverage.* That claim is false, and I can prove it in four commands.

The backend is **correct in mock mode and broken in live mode**. Every test is green (236 passed, 1 skipped) because every test runs with credentials stripped by `conftest.py`. The suite therefore validates the fallback path and never once exercises the path a judge will run on stage with real paper keys.

Three live-mode defects were reproduced today against the current `master` (`ddcc665`). Two of them mean **zero options data reaches the strategy layer**; one returns **HTTP 500**.

This brief is deliberately larger than six comfortable days. **B1–B7 are mandatory. B8–B12 are ranked spend-if-you-have-it.** Ship mandatory-complete rather than everything half-done.

Standing constraint for this layer: **no mutating route without an audit record, and no live-mode failure that silently degrades to mock.**

---

## 1 · Verified defects — reproduce these before you write anything

Run this first. It sets fake credentials so the live-mode branches actually execute, and stubs every broker response — no network:

```bash
python backend/tests/repro_live_defects.py
```

Against `ddcc665` it prints **1/7 checks pass**. Do not take my word for any finding below; the script is the evidence, and it is also your regression target — each fix should flip one line from FAIL to PASS.

### D1 · `get_option_snapshots` cannot parse Alpaca's actual response — CRITICAL

`backend/app/alpaca_client.py:171-179` does `payload.get("snapshots", [])` and then rejects anything that is not a `list`. The Alpaca options snapshots endpoint returns a **dict keyed by OCC option symbol**, not a list.

Reproduced:

```
CLAIM1 CONFIRMED - raises: AlpacaAPIError Alpaca snapshots response must contain a list
```

Consequence: in live mode with valid keys, **every** call to `/api/strategy/screen` catches this `RuntimeError` per symbol, appends it to `live_error`, and returns `count: 0`. The UI shows an amber banner and an empty table. The core feature of an options-income agent — finding options — never runs.

This is the single most damaging line in the backend, and no test covers it because `is_configured()` is false in every test.

### D2 · `_candidate_from_snapshot` reads field names Alpaca does not send — CRITICAL

`backend/app/routes/strategy.py:82-134` reads `snap["details"]["type"]`, `snap["details"]["strike_price"]`, `snap["latest_quote"]["bid_price"]`, `snap["underlying_asset"]["price"]`. The snapshots payload carries `greeks`, `impliedVolatility`, `latestQuote` (camelCase, with `bp`/`ap` keys), `latestTrade` — and **no `details` and no `underlying_asset` at all**. Strike and expiry live in the OCC symbol, which the codebase already knows how to parse (`parse_occ_symbol`).

Reproduced with a correctly-shaped snapshot:

```
candidate from real-shaped snapshot -> None
```

So even if D1 were fixed, every candidate is dropped at `details.get("type") != "call"`. Two independent bugs both produce "no candidates", which is why neither was noticed: the observable symptom is identical to an empty portfolio.

### D3 · `_occ_expiration` raises `TypeError` → HTTP 500 — HIGH

`backend/app/routes/agent.py:113` calls `datetime.date(2000 + int(...), ...)`. `datetime` here is the **class**, not the module, so `datetime.date` is an unbound descriptor:

```
TypeError: descriptor 'date' for 'datetime.datetime' objects doesn't apply to a 'int' object
```

`_pick_option_contract` catches `AlpacaAPIError, ValueError, TypeError, FuturesTimeoutError` — but the call sits **outside** that try block, inside the candidate loop. Reproduced end to end:

```
POST /api/agent/run -> 500
```

`docs/API-CONTRACT.md` promises *"500 | Bug | Should not happen — all known paths return 422"*. It happens on the flagship endpoint the moment credentials exist and one option snapshot comes back. Note also that `ROADMAP.md` §3 claims this function is *"now largely done"* — it has never executed successfully even once.

### D4 · `POST /api/trade` has zero coupling to the risk system — CRITICAL (design, not typo)

Reproduced in mock mode:

```
POST /api/trade {"symbol":"GME301231C00100000","qty":500,"side":"sell",...} -> 200
```

500 short call contracts on a symbol the portfolio does not hold. The route validates *syntax* — NaN, magnitude, OCC format, TIF — and nothing else. It does not check share coverage, cash collateral, the kill-switch, concentration caps, portfolio Greeks, or whether the agent ever recommended this trade.

`BRIEF-AGENT-V2.md` states the rule that does not bend: **"Never naked."** The agent layer enforces it in its own reasoning; the backend then exposes an endpoint that bypasses the agent layer entirely. Unauthenticated (KNOWN-ISSUES #8), and it has been tunnelled publicly during development.

The agent's discipline is decoration if the execution surface does not enforce it. **This is the finding I most want closed.**

### D5 · Blocking I/O inside `async def` serialises the whole process — HIGH

Every route is `async def`; every Alpaca call is synchronous `httpx.Client`. Two concurrent council requests, each stubbed to a 0.4s fetch:

```
wall clock for 2 concurrent requests: 0.80s (serialized => event loop blocked)
```

Perfectly additive — the event loop is blocked, not concurrent. A real `/api/council/cycle` fans out ~9 symbols × (bars + fundamentals), so a judge clicking twice, or the dashboard polling while someone runs the agent, queues behind a multi-second stall. `/health` stalls too, so the mock-mode badge freezes at exactly the moment the demo looks slow.

### D6 · `_snapshots` is a module-level global mutated per request — HIGH

`backend/app/routes/council.py:168` — `_snapshots: dict[str, dict] = {}`, reassigned inside `_assess()` via `global`, then read by `_assessment_to_dict()`. Two overlapping requests share it. Today D5 accidentally hides this by serialising everything; fix D5 without fixing D6 and you get **request A rendering request B's market data**, silently and non-deterministically. The correct fix order is D6 first.

### D7 · N+1 broker calls per screen — MEDIUM

`strategy.py:297-310` loops held positions and issues one `get_option_snapshots` per symbol, sequentially, with no cache and no concurrency. Ten holdings = ten round trips inside one HTTP request, each up to 15s timeout. Rate limits are not handled anywhere: `grep -c "retry|backoff|sleep" alpaca_client.py` → **0**.

### D8 · No auth, no logging, no correlation IDs, no rate limiting — HIGH

`grep -rn "Depends|api_key|Authorization|logging|logger|limiter" backend/app` → **no matches**. There is no way to answer "what did the system do at 14:32?" after the fact. For a system that submits orders, the absence of an audit log is not a missing nice-to-have; it is the absence of the primary control.

### D9 · Response envelopes exist and are unused — LOW

`backend/app/responses.py` defines five Pydantic models. Not one route declares `response_model=`. The OpenAPI schema at `/docs` therefore documents every endpoint as returning a bare `dict` — the schema a judge inspects tells them nothing.

### D10 · Strategy config is a process-local singleton — MEDIUM

`strategy.py:33` — `_active_config` is module state mutated by `PUT /api/strategy/config`. It survives no restart, is not shared across workers (`uvicorn --workers 2` gives two divergent configs), and is not audited: no record of who changed the kill-switch threshold or when.

---

## 2 · Target end-state

| Dimension | Today | Target D0 |
|---|---|---|
| Live options data | broken (D1+D2) | parsed, normalised, contract-tested against a captured real payload |
| Order safety | syntax validation only | pre-trade risk gate: coverage, collateral, kill-switch, caps, Greeks |
| Order provenance | none | every order traceable to a `run_id` + directive, or explicitly flagged manual |
| Idempotency | client-supplied `client_order_id`, unenforced | deterministic key + duplicate rejection inside a window |
| Concurrency | event loop blocked | broker I/O off-thread, per-request state, bounded fan-out |
| Auth | **IMPLEMENTED (2026-09-01): session + CSRF on mutating routes + /api/agent/run** | shared-secret on mutating routes + POST /api/agent/run and /api/council/cycle gated (session + CSRF), localhost-bind default |
| Observability | none | structured JSON logs, `X-Request-ID`, `/metrics`, audit trail |
| Resilience | no retry, no cache, no breaker | backoff on 429/5xx, TTL cache, circuit breaker with visible state |
| Persistence | stateless | SQLite audit + order ledger (own store; do not reach into agent's) |
| OpenAPI | every route `dict` | `response_model` on all, examples, error envelopes |
| Tests | 236, live path never exercised | ≥ 330, live path covered by fixtures captured from real payload shapes |

---

## MANDATORY WORKSTREAMS

### B1 · Fix the live data path and make it impossible to break again
**Closes:** D1, D2, D3 · **Blocks:** everything else · **Do this first**

Three fixes, then the structural change that stops the class of bug recurring.

**1a · `get_option_snapshots` accepts the real shape.** Handle `dict` keyed by option symbol *and* `list` (some endpoints/feeds differ), normalising to a list of dicts each carrying its `symbol`. Follow the `next_page_token` when present — a chain for a liquid underlying exceeds one page, and silently truncating it biases every screen toward whichever strikes happen to come first.

**1b · One options-data adapter — `backend/app/adapters/options.py`.** Add `normalize_snapshot(option_symbol, raw) -> OptionQuote | None` as the *single* place raw broker JSON becomes an internal object. Typed, with explicit provenance:

```python
@dataclass(frozen=True)
class OptionQuote:
    option_symbol: str
    underlying: str
    expiration: date        # from OCC symbol, not from a payload field
    strike: float
    option_type: Literal["call", "put"]
    bid: float | None
    ask: float | None
    mid: float | None
    last: float | None
    implied_volatility: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    open_interest: int | None
    source: Literal["indicative", "opra"]
    as_of: datetime
```

Accept both `latestQuote`/`latest_quote` and both `bp`/`bid_price` spellings. Missing fields are `None`, **never `0.0`** — the same rule the agent brief sets for greeks, for the same reason: `0.0` is a claim of flatness and a filter cannot tell it from a real zero. `delta is None` must exclude a contract from delta-band screening rather than treating it as delta 0 and passing the band trivially.

Then rewrite `_candidate_from_snapshot` to consume `OptionQuote` and delete every raw `snap.get(...)` from route code. Routes must never touch broker JSON again.

**1c · `_occ_expiration` uses `date(...)`, and OCC parsing exists once.** Import `date` properly. There are now three OCC parsers (`alpaca_client.parse_occ_symbol`, `agent.py::_occ_expiration`, the regex in `normalize_option_position`) — collapse to one in the adapter, re-exporting from `alpaca_client` for compatibility.

**1d · Golden fixture, so this cannot silently regress.** Capture one real snapshots payload from paper credentials, redact nothing (it is public market data, but verify no account identifiers), and commit it as `backend/tests/fixtures/options_snapshots_aapl.json`. Every parsing test loads that file. A hand-written fixture proves only that the parser agrees with your assumptions — which is precisely how D1 and D2 both shipped green.

Also fix the D3 test gap named in `ROADMAP.md` §5: `_pick_option_contract`, `_tier_bands`, `_occ_expiration` have **zero** coverage and two sign bugs already reached master.

Acceptance: `test_options_adapter.py` (golden fixture → ≥1 valid `OptionQuote`; dict and list shapes; `None` propagation; pagination; malformed OCC skipped not raised), `test_pick_option_contract.py` (the six cases in ROADMAP §5). `POST /api/agent/run` returns 200 with live credentials and a stubbed chain. **A live-mode integration test must exist that fails against `ddcc665`.**

---

### B2 · Pre-trade risk gate — `backend/app/risk/`
**Closes:** D4 · **Depends:** B1 · **This is the highest-value item in the brief**

`POST /api/trade` must not reach the broker without passing a gate. Structure it as a pure function so it is trivially testable and reusable:

```python
@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    checks: list[CheckResult]      # every check, pass and fail, with the numbers
    hard_failures: list[str]
    warnings: list[str]
    evaluated_at: datetime
    snapshot_hash: str             # portfolio state the decision was made against
```

Checks, in order, each returning its computed values rather than a bare boolean:

| # | Check | Rejects |
|---|---|---|
| 1 | **Kill-switch** | any order while the agent layer reports halted |
| 2 | **Coverage** | short call without `qty × 100` shares held — *the "never naked" rule, enforced* |
| 3 | **Collateral** | short put without cash ≥ strike × 100 × qty, respecting `min_cash_reserve_pct` |
| 4 | **Concentration** | breach of `max_concentration_pct` / `max_sector_concentration_pct` |
| 5 | **Duplicate** | same contract + side within the idempotency window (B3) |
| 6 | **Contract sanity** | expired, expiring today, or DTE outside config band |
| 7 | **Price sanity** | limit price outside a tolerance of the current bid/ask; market orders on options rejected outright |
| 8 | **Provenance** | `run_id` + directive reference absent → allowed only with explicit `manual_override: true` **and** an audit reason string |
| 9 | **Greeks caps** | if `agent.greeks` exists (agent brief W3), portfolio-level breach downgrades or blocks |

Order matters: cheap local checks before anything that costs a broker round trip.

Hard failure → **HTTP 409** with the full `checks` array. Not 422: the request was well-formed and the *state* forbids it, and the frontend must be able to distinguish "you sent nonsense" from "this trade is unsafe right now". Announce 409 to Adit — it is a new status on a route he already calls.

Two failure modes to design against explicitly:

- **Fail-closed.** If portfolio state cannot be fetched, the gate returns `allowed: false`. A gate that opens when it cannot see is worse than no gate, because it creates unearned confidence.
- **No silent bypass.** `manual_override` is logged at warning level with the operator's reason, appears in the audit ledger, and surfaces in the response. An override nobody can see later is indistinguishable from no gate at all.

Wire `GET /api/trade/preflight` (same gate, no submission) so the frontend can show why a button is disabled before the user clicks it.

Acceptance: `test_risk_gate.py` — one test per check, both directions; naked call rejected; CSP without collateral rejected; kill-switch halt blocks everything; state-fetch failure fails closed; override path logs and records. Plus `test_trade_route_risk.py` asserting the exact `GME` payload from D4 now returns 409.

---

### B3 · Idempotency and the order ledger — `backend/app/store/`
**Closes:** D10 partly, D8 partly · **Depends:** B2

Duplicate submission is the failure that costs real money: a double-click, a frontend retry on timeout, or a judge pressing a button twice becomes two short positions where the risk model assumed one.

SQLite at `backend/.cache/backend_state.db` (gitignore it), WAL mode, schema-versioned. **Your own store — do not read or write the agent layer's `agent_state.db`.** Cross-layer database sharing is how a boundary violation becomes a data-corruption bug; if you need agent state, call an agent function.

| Table | Purpose |
|---|---|
| `order_intent` | every attempted order: payload, `run_id`, directive ref, risk decision JSON, idempotency key, outcome |
| `audit_event` | every mutating request: route, actor, request ID, before/after for config changes |
| `config_history` | every `PUT /strategy/config`: full before/after, actor, timestamp |
| `broker_call` | outbound Alpaca calls: endpoint, status, latency, retry count, correlation ID |

Idempotency key = `sha256(symbol|side|qty|type|limit_price|date)` unless the client supplies `client_order_id`. A repeat inside the window returns **the original response with `duplicate: true`**, and does not call the broker. Idempotency that returns an error on retry is not idempotency — a client that legitimately retries after a network timeout must be able to converge.

Constructible with `:memory:` so tests never touch disk.

Acceptance: `test_order_ledger.py`, `test_idempotency.py` — identical payload twice → one broker call, second response `duplicate: true`; different qty → two calls; window expiry → new call; crash between broker call and ledger write leaves a recoverable `pending` row, not a lost order. That last case is the one that matters: **write the intent row before the broker call, update after.** Reverse the order and a timeout gives you an order you have no record of.

---

### B4 · Concurrency and correctness under load
**Closes:** D5, D6, D7

**4a · Broker I/O off the event loop.** Either `async` httpx throughout, or wrap sync calls in `anyio.to_thread.run_sync`. Prefer the second: smaller diff, no behaviour change in the client, and it composes with the existing `ThreadPoolExecutor` in `agent.py`.

**4b · Kill `_snapshots`.** Pass snapshots explicitly as a parameter through `_assess` → `_assessment_to_dict`. **Do this before 4a** — real concurrency turns a hidden global into a cross-request data leak.

Then grep the backend for every other module-level mutable: `_active_config` is the other one, and B6 addresses it.

**4c · Bounded fan-out with a semaphore.** Replace the N+1 loop with concurrent fetches capped at 4–5 in flight. Unbounded `gather` over held positions trades a slow endpoint for a rate-limit ban, which is strictly worse: slow degrades, banned fails.

**4d · TTL cache for chains and bars.** 60s for option chains, 15min for daily bars, keyed by symbol, with the age exposed in the response (`data_age_seconds`). A judge clicking screen three times should not cost 30 broker calls. Cached data must be *labelled* cached — the fundamentals-cache lesson in KNOWN-ISSUES #1 is exactly this: silent staleness reads as analysis.

**4e · Retry, backoff, circuit breaker.** Retry 429 and 5xx with exponential backoff plus jitter, honouring `Retry-After`; **never retry a POST /v2/orders** without an idempotency key (B3) — a retried order submission is a duplicate position. Open a breaker after N consecutive failures and return 503 with the breaker state visible, so the failure is legible instead of a wall of timeouts.

Acceptance: `test_concurrency.py` — two concurrent council requests complete in materially less than the sum of their latencies (the D5 measurement, inverted); interleaved requests with different symbol sets never see each other's snapshots (D6); semaphore bounds in-flight calls; 429 retried with backoff; POST orders never retried; breaker opens and recovers.

---

### B5 · Auth, audit and observability
**Closes:** D8 · KNOWN-ISSUES #8

**PARTIALLY COMPLETE (2026-09-01):** Session-based auth with CSRF double-submit is implemented on mutating routes (`POST /api/trade`, `POST /api/trade/preflight`, `PUT /api/strategy/config`, `POST /api/agent/run`). Login endpoint returns `csrf_token` in body and sets `ao_session` cookie (HttpOnly). Rate limiting: 5 login attempts/min/IP (in-process, 60s sliding window). **Remaining: structured logging, `X-Request-ID`, `/metrics`, audit trail.**

**5a · Shared-secret on mutating routes.** `X-API-Key` compared with `hmac.compare_digest` against `BACKEND_API_KEY`, applied via a FastAPI dependency on `POST /api/trade`, `PUT /api/strategy/config`, and — deliberately — `POST /api/agent/run` and `POST /api/council/cycle`, because both are expensive and both trigger real broker reads.

If `BACKEND_API_KEY` is unset: **serve, but log a loud startup warning and expose `auth: "disabled"` on `/health`.** Refusing to start would break Adit's local dev; hiding the state is what created KNOWN-ISSUES #8 in the first place. Default the bind to `127.0.0.1` and document that the backend port is never tunnelled — the frontend is the only thing that should be public.

Constant-time comparison is not paranoia here; `==` on a secret is a finding a judge with a security background will look for.

**5b · Structured logging + request IDs.** JSON logs to stdout, one line per request: `request_id` (accept inbound `X-Request-ID`, else generate), method, path, status, duration, mode, `alpaca_configured`. Echo `X-Request-ID` back on every response. Then propagate it into `broker_call` rows so one ID links a UI click to a broker call to a ledger entry.

**Never log a full order payload at info level with credentials in scope, and never log `ALPACA_SECRET` or `BACKEND_API_KEY` even truncated.** Add a redaction filter and a test that asserts a known secret value never appears in captured log output — a leak into a log file is the same incident as a leak into git, and this repo has already had one key exposure.

**5c · `/metrics` and a real readiness probe.** Counters: requests by route and status, broker calls by endpoint and outcome, retries, breaker state, orders submitted/blocked/duplicated, cache hit rate. Split `/health` (process alive) from `/ready` (config valid, agent modules importable, broker reachable if configured, breaker closed) — a load balancer needs the difference, and so does the demo laptop.

Acceptance: `test_auth.py` (missing/wrong/correct key; unset key path warns and allows; constant-time function used), `test_logging.py` (secret redaction, request ID echo and propagation), `test_metrics.py`.

---

### B6 · Persisted, audited, validated configuration
**Closes:** D10

Move `_active_config` into the B3 store: read-through on request, write with a `config_history` row capturing before/after and actor. Add `GET /api/strategy/config/history`.

Two rules worth stating because the current code violates the spirit of both:

- **Reject a config that disables a safety control silently.** `kill_max_drawdown_pct: 100.0` is arithmetically valid and functionally disables the kill-switch. Require `confirm_unsafe: true` for any value outside a sane band, and record it as a warning in the history row.
- **Config changes are versioned, and every order references the config version it was evaluated under.** Otherwise "why was this trade allowed?" is unanswerable after someone widens the delta band mid-session.

Acceptance: `test_config_persistence.py` — survives restart, history records before/after, unsafe values require confirmation, two workers converge on one stored config.

---

### B7 · Contract truth: OpenAPI, response models, and killing the doc drift
**Closes:** D9, KNOWN-ISSUES #3

`response_model=` on every route using the existing `backend/app/responses.py` envelopes, extended for the new shapes (`RiskDecisionResponse`, `PreflightResponse`, `OrderLedgerEntry`). Add `examples` so `/docs` is demonstrable.

Then close KNOWN-ISSUES #3 properly. `specials/BACKEND_FRONTEND_API.md` is *your* file and it contradicts the code in three places, plus `dissent[].why` typed as string when it is `string[]`. A frontend brief was written from it. Two options — pick one and say which:

- generate the doc from the OpenAPI schema so drift is structurally impossible, or
- delete the hand-written field tables and link to `/docs` + `docs/API-CONTRACT.md`.

**A hand-maintained API document that has already misled a teammate once should not survive this brief in hand-maintained form.**

Acceptance: `test_openapi_contract.py` — schema generates, every route declares a response model, no route documents a bare `dict`, and a snapshot test on the schema so a field rename fails a test instead of a frontend.

---

---

## RANKED OPTIONAL

**B8 · Mock option chain generator** (ROADMAP §3, and it gates the demo) — synthesise a chain from mock positions so `order_intents` shows real strikes/premiums **without credentials**. Highest optional value: it decides whether the demo needs live keys. Label every synthetic field `synthetic: true`, per the agent brief's rule.

**B9 · WebSocket or SSE stream** — push cycle progress (`step 3/7: council assessing NVDA`) instead of the frontend polling. Visible in a demo; do not attempt before B1–B4 are green.

**B10 · `POST /api/trade/batch`** — submit a whole approved directive set atomically, with all-or-nothing semantics and a single risk evaluation across the batch. Per-order gating can pass three orders individually that together breach concentration.

**B11 · Broker abstraction seam** — `BrokerPort` protocol with `AlpacaBroker` and `FakeBroker` implementations. Makes live-path tests trivial and removes the credential dependency from integration tests.

**B12 · Response compression + pagination on `cycle`** — `/api/council/cycle` returns the entire cycle including every assessment and trace; it will only grow as the agent layer expands. Add `?verbose=false`.

---

## Sequencing

| Day | Backend workstream |
|---|---|
| **D-6** Sat 29 | B1 — adapter, three fixes, golden fixture, live-path tests |
| **D-5** Sun 30 | B2 — risk gate + `preflight` + 409 wiring (announce to Adit) |
| **D-4** Mon 31 | B3 — SQLite store, order ledger, idempotency |
| **D-3** Tue 1 | B4 — 4b (globals) then 4a (off-thread), then 4c/4d |
| **D-2** Wed 2 | B4e breaker/retry + B5 auth, logging, metrics |
| **D-1** Thu 3 | B6 config persistence + B7 OpenAPI/doc reconciliation + full-suite run |
| **D0** Fri 4 | Freeze 06:00 UTC. Demo rehearsal only. |

B8 slots in wherever it fits — if the demo turns out to need it, promote it above B6.

---

## Definition of done

Per JOBDESK, plus two additions this layer needs:

1. `pytest backend/tests agent/tests -q` green — **both suites**.
2. New behaviour has tests that **fail against `ddcc665`**. A test that passes before your change tests nothing — and the four critical defects above all shipped under a green suite, so this rule is the one that would have caught them.
3. **No network in tests.** Broker calls monkeypatched or served by `FakeBroker`.
4. **A live-mode test exists for every live-mode code path.** `conftest.py` strips credentials globally; add an explicit opt-in fixture that injects fake credentials so the `is_configured() == True` branch is exercised. This is the root cause of D1, D2 and D3, and closing it is worth more than any single fix.
5. Any route/field/status change is announced and `specials/BACKEND_FRONTEND_API.md` updated **in the same commit**.
6. Modified existing tests called out explicitly in the commit message.

---

## Rules that do not bend

- **Never naked, enforced in code.** The gate, not the prompt, is what makes this true. B2 is not optional.
- **Fail closed.** Cannot read state → refuse the order. Cannot verify coverage → refuse. Silence is never consent.
- **Never auto-submit.** `orders_ready` stays `false`; `/api/agent/run` never submits. Submission requires a separate authenticated, gated, human-initiated call.
- **Degrade to `None`, never to a number.** Missing bid, missing delta, missing IV are `None`. A default of `0.0` passed a delta-band filter trivially — that is D2's mechanism.
- **Live failures surface.** Never silently substitute mock data when credentials exist. `live_error` and 502 exist for this; keep them.
- **Secrets: env only.** No keys in code, tests, fixtures, docs, or logs. Verify before every push:
  ```bash
  grep -rInE "PK[A-Z0-9]{15,}" . --exclude-dir=.git --exclude-dir=node_modules
  ```
- **Stay in `backend/**` and `specials/**`.** Need agent behaviour? Call an agent function or raise it with Zaki. Need a UI change? Raise it with Adit.
- **Read your own diff before committing.** Every file in it must be one you meant to change.

---

## Risk register — what can go wrong with this brief

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | B2's gate is too strict and blocks the demo trade | High | Demo dies on stage | `preflight` first; rehearse the exact demo order end to end on D-1; every rejection returns the numbers so it is diagnosable in seconds |
| R2 | Concurrency refactor (B4a) introduces a subtle race worse than the stall it fixes | Medium | Wrong data, silently | Do B4b **before** B4a; land them as separate commits; concurrency tests before the refactor |
| R3 | SQLite in a container without a writable volume | Medium | Store unavailable at runtime | `/tmp` fallback with a loud warning + `degraded: true` on `/health` — same pattern the agent brief mandates for its cache |
| R4 | Auth (B5a) breaks Adit's local dev without warning | High | Frontend appears broken, hours lost | Unset key ⇒ serve + warn + `auth: "disabled"` on `/health`; tell Adit in the same message as the commit |
| R5 | 409 from the trade route is unhandled by the frontend | High | Silent failure or misleading UI | Announce before implementing; ship `preflight` so the UI can disable the button pre-emptively |
| R6 | Golden fixture cannot be captured — no paper credentials in time | Medium | B1 lands on assumed shapes again | Capture during market hours on D-6; if impossible, build against the published schema **and mark the fixture `assumed: true`** so the risk stays visible |
| R7 | Scope overrun — B1–B7 is more than six days | High | Half-finished layer at freeze | B1+B2 alone is a materially better submission than all seven half-done. Stop at whatever is green. |
| R8 | Backend changes break the agent suite via shared imports | Medium | Cross-layer breakage | Both suites on every commit (already the JOBDESK rule); backend imports agent, never the reverse |
| R9 | Breaker/retry masks a real outage during the demo | Low | Stale data presented as live | Breaker state and `data_age_seconds` in every response; UI can show it |
| R10 | Live keys leak into logs or the ledger | Low | Second key-exposure incident | Redaction filter + a test asserting a known secret never appears in log output or DB rows |

---

## What this buys us with judges

| Question | Answer after this brief |
|---|---|
| "Can it actually read an options chain?" | Yes — parsed via one adapter, contract-tested against a captured real payload |
| "What stops it selling a naked call?" | A nine-check pre-trade gate that fails closed, returns numbers, and cannot be bypassed without an audited override |
| "What if I click submit twice?" | Deterministic idempotency key; one broker call, second response `duplicate: true` |
| "Who can call your trade endpoint?" | Authenticated on mutating routes, localhost-bound by default, every call audited |
| "Show me what happened at 14:32." | One request ID links UI click → risk decision → broker call → ledger row |
| "What happens when Alpaca rate-limits you?" | Backoff with `Retry-After`, breaker opens, 503 with visible state — never a retried order |
| "Is the API contract real?" | Generated from code; a field rename fails a test, not a frontend |

The pattern across all seven: **the backend stops being the layer that trusts the agent to be careful, and becomes the layer that enforces it.** That is the difference between a demo that works and a system a judge would believe with real money behind it.

One more thing, said plainly. The reason the four critical defects sat in a repo with 236 green tests is that the suite tests the fallback and never the real path. Fix the fixture gap (definition-of-done #4) and every future bug of this class fails a test instead of a demo. If you only take one structural change from this brief, take that one.

