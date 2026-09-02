# AutoOverlay AI — Backend / Frontend API Contract

Status: Current public API contract for the hackathon MVP

## 1. System relationship

```text
Frontend (Next.js)
        |
        | HTTP JSON requests to /api/*
        v
Backend (FastAPI)
        |
        +--> DecisionEngine / strategy modules
        +--> Council assessment and daily cycle
        +--> Alpaca paper-trading/data APIs
        +--> Mock data fallback without credentials
```

The backend is stateless. Alpaca is the source of truth for live account data,
positions, option snapshots, and broker orders. The backend currently stores no
application history in PostgreSQL or another database.

## 2. Public endpoint map

All application routes use the `/api` prefix. Duplicate routes without this
prefix have been removed and intentionally return HTTP 404.

| Endpoint | Method | Frontend purpose | Source |
|---|---:|---|---|
| `/health` | GET | Backend and Alpaca configuration check | `backend/app/main.py` |
| `/api/portfolio` | GET | Account summary and holdings | `backend/app/routes/portfolio.py` |
| `/api/strategy/screen` | GET | Screen covered-call opportunities | `backend/app/routes/strategy.py` |
| `/api/strategy/screen` | POST | Screen with symbols and filters | `backend/app/routes/strategy.py` |
| `/api/strategy/config` | GET | Load strategy parameters | `backend/app/routes/strategy.py` |
| `/api/strategy/config` | PUT | Update strategy parameters | `backend/app/routes/strategy.py` |
| `/api/council/assess` | GET/POST | Run persona-based assessment | `backend/app/routes/council.py` |
| `/api/council/cycle` | POST | Run autonomous daily cycle | `backend/app/routes/council.py` |
| `/api/agent/run` | POST | Run recommendation-only agent cycle | `backend/app/routes/agent.py` |
| `/api/agent/run/{run_id}` | GET | Fetch prior agent run by id | `backend/app/routes/agent.py` |
| `/api/bot/status` | GET | Scheduler state and last execution metrics | `backend/app/routes/bot.py` |
| `/api/bot/start` | POST | Start/resume the 1h scheduler | `backend/app/routes/bot.py` |
| `/api/bot/stop` | POST | Stop the scheduler | `backend/app/routes/bot.py` |
| `/api/bot/config` | POST | Update scheduler interval and auto-execution | `backend/app/routes/bot.py` |
| `/api/bot/cycle` | POST | Trigger one immediate autonomous cycle | `backend/app/routes/bot.py` |
| `/api/bot/history` | GET | Recent autonomous runs | `backend/app/routes/bot.py` |
| `/api/bot/logs` | GET | Tail bot log lines | `backend/app/routes/bot.py` |
| `/api/trade` | POST | Validate and submit/simulate order | `backend/app/routes/trade.py` |
| `/api/trade/orders` | GET | Load broker or mock orders | `backend/app/routes/trade.py` |

## 3. Endpoint contracts

### GET `/health`

```json
{
  "status": "ok",
  "alpaca_configured": false
}
```

This endpoint does not call Alpaca. `alpaca_configured` reports whether the
required trading environment values are present.

### GET `/api/portfolio`

```json
{
  "mode": "mock",
  "account_info": {},
  "positions": []
}
```

Live mode reads the Alpaca account and positions. Without credentials, bundled
mock data is returned.

If credentials are configured but Alpaca is unavailable or returns malformed
data, the backend does not silently switch to mock mode. Trading endpoints
return HTTP 502 with a safe error detail; screening may skip an unavailable
market-data symbol.

### GET/POST `/api/strategy/screen`

The screening route evaluates covered-call opportunities over eligible equity
positions and enriches candidates with DecisionEngine risk information.

GET parameters:

- `symbols`: comma-separated tickers
- `min_open_interest`: minimum open interest
- `top_n`: maximum candidates, 1–25
- `full`: enable DecisionEngine enrichment

POST example:

```json
{
  "symbols": ["AAPL"],
  "min_open_interest": 0,
  "max_annualized_return": 10.0,
  "top_n": 5,
  "full": true
}
```

Candidate records may include:

- `symbol`
- `option_symbol`
- `strike_price`
- `expiration_date`
- `annualized_return_rate`
- `risk_score`
- `action`
- `rationale`
- `reasoning_trace`

#### Nullable candidate fields (changed 2026-08-29)

Several candidate fields are now `null` when the broker feed does not supply the
underlying data, where they previously defaulted to `0`. A `0` was
indistinguishable from a real zero and passed range filters trivially — that
defect (D2) meant live screening produced no candidates at all. Frontend must
treat these as optional:

| Field | `null` when | Render as |
|---|---|---|
| `delta`, `theta`, `implied_volatility` | the contract has no greeks block (the indicative feed omits greeks on illiquid strikes — 273 of 500 in a captured AAPL chain) | `—` |
| `open_interest` | **always on the indicative feed** — it does not carry OI. The OPRA feed would, and returns HTTP 403 `OPRA agreement is not signed` on this account | `—`; do not filter on it |
| `probability_itm` | `delta` is null | `—` |
| `bid` / `ask` | that side of the book is empty (`bp: 0` means no bid, not a price of zero) | `—` |
| `underlying_price` | no held-position price available | `—` |
| `annualized_return_rate` | `underlying_price` is null, so the yield has no denominator | `—`, and expect `recommendation: "MONITOR_CLOSELY"` |

`min_open_interest` is still accepted as a request parameter, but because the
indicative feed carries no OI, any value above `0` filters out every candidate.
Leave it at `0` until an OPRA-entitled feed is available.

### GET/PUT `/api/strategy/config`

The configuration includes entry, exit, delta, DTE, concentration, and cash
reserve parameters. Initial values can come from `STRATEGY_CONFIG_JSON`.
Valid PUT changes remain in process memory until restart. Invalid values return
HTTP 422 and do not replace the active configuration.

### GET/POST `/api/council/assess`

Runs the council personas for requested symbols. Without Alpaca credentials it
uses bundled snapshots. The response contains mode, assessment count, and per-symbol records with:
- `symbol`
- `tier`: one of `LOW` / `MID` / `HIGH` (derived from annualized vol band)
- `consensus_score`: 0–100 weighted score
- `recommendation`
- `majority_stance`
- `is_split`
- `verdicts`
- `dissent`
- `tier_policy_summary`
- `tier_policy`
- `mr_market_context`

`tier_policy` exposes the active council-derived option filter for that
volatility tier. `delta_min` and `delta_max` are **short-option absolute
deltas**: positive numbers such as `0.15` represent a `-0.15` delta for puts
or `+0.15` for calls. The backend normalizes to `abs(delta)` before comparing,
so frontend consumers should **not** negate these values.

GET example:

```text
/api/council/assess?symbols=AAPL,MSFT
```

### POST `/api/council/cycle`

Runs the autonomous daily council cycle using the live portfolio when Alpaca is
configured, otherwise mock portfolio data. The cycle applies council policy,
portfolio risk controls, and candidate decisions. It does not submit a broker
order automatically merely because a recommendation exists.

In live mode, open short option positions from Alpaca are normalized from OCC
symbols and passed to `ExitManager`, so the cycle can produce `EXIT` or `ROLL`
directives. Invalid option records are ignored safely. If live portfolio fetch
fails, the endpoint returns HTTP 502 instead of silently switching to mock data.

### POST `/api/agent/run`

Runs the existing council daily cycle as a recommendation-only agent workflow.
It accepts the same optional `candidates`, `cash_override`, and
`portfolio_state_overrides` values as the council cycle.

The response includes:

- `run_id`
- `status`
- `mode`
- `recommendations`
- `risk_summary`
- flattened `reasoning_trace`
- full `cycle` result
- `orders_ready: false`

This endpoint never calls order submission. A later, separately approved flow
must call `/api/trade` after the user reviews the recommendation.

`order_intents` contains approval-gated `SELL_TO_OPEN` payloads derived from
`INITIATE` directives. Each intent includes `requires_approval: true` and
`submitted: false`.

### POST `/api/trade`

```json
{
  "symbol": "AAPL260929C00250000",
  "qty": 1,
  "side": "sell",
  "type": "limit",
  "time_in_force": "day",
  "limit_price": 2.5,
  "run_id": "run-f1a12436422144e1",
  "directive_ref": "directive-1"
}
```

Validation covers quantity, side, order type, time-in-force, limit price, equity
symbols, and OCC option symbols. Valid OCC symbols are supported for covered
calls/CSP flows. Option orders require `day` time-in-force.

#### BREAKING (2026-08-29): every order passes a pre-trade risk gate

`POST /api/trade` previously validated request *syntax* only. It accepted 500
naked short calls on a symbol the portfolio did not hold and returned HTTP 200.
It now runs nine checks before the broker is contacted, and **rejects with HTTP
409** when any of them blocks.

**Four request fields are new:**

| Field | Meaning |
|---|---|
| `run_id` | the `/api/agent/run` run this order came from. **Required** unless overriding |
| `directive_ref` | optional identifier of the specific directive |
| `manual_override` | `true` to place an order the gate blocked |
| `override_reason` | **required** when `manual_override` is true; recorded in the response |

An order with neither `run_id` nor a reasoned override is rejected: the gate
will not place a trade it cannot attribute.

**New status code — 409 Conflict.** Distinct from 422 on purpose:

| Status | Meaning | UI should |
|---|---|---|
| 422 | the request is malformed | show a validation error; do not retry unchanged |
| **409** | the request is well-formed but the **state** forbids the trade | show `detail.risk.hard_failures`; the numbers to explain it are in `detail.risk.checks[].values` |
| 502 | Alpaca failed | show the error; retry is reasonable |
| 200 | accepted (`risk.allowed: true`) | proceed |

409 body:

```json
{
  "detail": {
    "message": "order blocked by the pre-trade risk gate",
    "risk": {
      "allowed": false,
      "hard_failures": ["NAKED CALL: 500 short call(s) on GME need 50000 shares (0 contract(s) already short); portfolio holds 0"],
      "warnings": [],
      "checks": [
        {
          "name": "coverage",
          "passed": false,
          "severity": "BLOCK",
          "detail": "NAKED CALL: 500 short call(s) on GME need 50000 shares ...",
          "values": {"underlying": "GME", "shares_held": 0, "shares_required": 50000}
        }
      ],
      "evaluated_at": "2026-08-29T14:32:01.123456+00:00",
      "snapshot_hash": "9f2c1ab77e0d4c31",
      "mode": "live",
      "override_applied": false
    }
  }
}
```

`checks` always contains **all nine entries, passing ones included** — render
them as a checklist, not just the failures. `severity` is `BLOCK` (rejects),
`WARN` (allowed, worth showing) or `INFO`.

The nine checks, in evaluation order:

| Check | Blocks when |
|---|---|
| `state_available` | portfolio state could not be read — **fails closed**, never overridable |
| `kill_switch` | the agent kill-switch is engaged — **never overridable** |
| `contract_sanity` | contract expired or expires today (BLOCK); DTE outside the config band (WARN) |
| `coverage` | short call without `qty × 100` shares, counting shares already committed to existing short calls |
| `collateral` | short put without cash ≥ strike × 100 × qty after the `min_cash_reserve_pct` floor |
| `concentration` | a short put's collateral would breach `max_concentration_pct`. A covered call adds no exposure — an already-overweight holding is a WARN, not a block |
| `duplicate` | already short this exact contract (WARN — scaling in is legitimate) |
| `price_sanity` | market order on an option (BLOCK); limit >50% from the quote (BLOCK); no quote available (WARN) |
| `provenance` | no `run_id` and no reasoned `manual_override` |

**A successful response now also carries `risk`.** `200` bodies gain the same
decision object, so an accepted order records what it was checked against:

```json
{ "mode": "mock", "submitted": false, "order": {...}, "risk": {"allowed": true, ...} }
```

#### Idempotency (2026-08-30): a repeated submission does not place a second order

An identical order inside a **5-minute window** returns the *original* response
and never reaches the broker. Two new response fields:

| Field | Meaning |
|---|---|
| `duplicate` | `true` when this response is a replay of an earlier submission |
| `idempotency_key` | the key this order was filed under; stable, safe to log |

A duplicate response also carries `original_submitted_at`. The status is **200,
not an error** — a client retrying after a network timeout must be able to
converge on the original outcome, so an error here would defeat the purpose.

The key is derived from `symbol`, `side`, `qty`, `type`, `limit_price` and the
UTC date. Non-economic fields such as `extended_hours` do not affect it. Passing
`client_order_id` overrides the derivation entirely — the client is asserting its
own request identity, so the same id with a different payload is still treated as
the same request.

Two cases deliberately *are* retryable:

* **A blocked order (409) is not a duplicate.** Nothing was placed, so once the
  portfolio allows it the same order goes through normally.
* **A broker failure is not retryable.** It is ambiguous — the order may already
  exist — so the retry is suppressed and a `failed` row is left in the ledger for
  an operator to reconcile.

`POST /api/trade/preflight` never writes to the ledger, so checking an order does
not make the real submission look like a duplicate.

If the ledger is unavailable (see `degraded` on `/api/trade/ledger`) trading
still works, but **the idempotency guarantee does not hold** — persistence is an
audit improvement, not a new single point of failure.

### POST `/api/trade/preflight` (new)

Identical request body, runs the identical gate, **submits nothing**. Use it to
disable a submit button and show why *before* the user clicks:

```json
{ "mode": "live", "submitted": false, "risk": {"allowed": false, "hard_failures": ["..."], ...} }
```

Returns 200 even when `risk.allowed` is false — the preflight itself succeeded.
`run_id` is not required here, so the UI can preflight before attaching one; the
`provenance` check simply reports as failing.

Without Alpaca credentials:

```json
{
  "mode": "mock",
  "submitted": false
}
```

No broker request is made in mock mode — **but the gate still runs**, and a
blocked order returns 409 in mock mode too. A demo that skips the gate proves
nothing about the gate.

Timeouts, connection failures, non-2xx responses, invalid JSON, and unexpected
Alpaca response shapes are normalized by the client and surfaced as HTTP 502 by
the trade/order routes.

### GET `/api/trade/orders`

Returns live Alpaca orders when configured, otherwise bundled mock orders. This
is the order-history source; portfolio data does not embed broker orders.

### GET `/api/trade/ledger` (new)

Every order this backend attempted — blocked, simulated, submitted or failed.
The audit answer to "what did the system do at 14:32?".

```json
{
  "degraded": false,
  "degraded_reason": null,
  "schema_version": 1,
  "pending": [],
  "intents": [
    {
      "id": 12,
      "idempotency_key": "auto:9f2c1ab7…",
      "created_at": "2026-08-29T14:32:01.123456+00:00",
      "status": "submitted",
      "mode": "live",
      "symbol": "AAPL260929C00250000",
      "side": "sell",
      "qty": 1.0,
      "run_id": "run-f1a12436422144e1",
      "broker_order_id": "b1e2…",
      "payload": {"...": "the exact order sent"},
      "risk": {"allowed": true, "checks": ["..."]},
      "response": {"...": "what was returned"},
      "error": null
    }
  ]
}
```

`status` is one of `pending`, `submitted`, `simulated`, `rejected`, `failed`.

**`pending` is surfaced separately and matters.** A pending row means the intent
was written, the broker call never resolved, and an order may exist at Alpaca
whose outcome this system never learned. Reconcile those against
`/api/trade/orders` — do not assume either way.

`limit` is clamped to 1–500.

### GET `/api/trade/audit` (new)

Route-level event log: `{"degraded": false, "events": [{"created_at", "route",
"action", "outcome", "detail"}]}`. `outcome` is `blocked`, `duplicate`,
`simulated`, `submitted` or `broker_error`.

## 4. Frontend data flow

### Dashboard and Assets

1. Request `/api/portfolio`.
2. Backend returns Alpaca or mock account and positions.
3. Request `/api/strategy/screen` for option opportunities.
4. Request `/api/trade/orders` for order history.

### Terminal / agent feed

1. Request `/api/strategy/screen`.
2. Backend runs screening and DecisionEngine enrichment.
3. Frontend renders risk score, action, rationale, and reasoning trace.

### Council page

1. Request `/api/council/assess` for persona verdicts.
2. Request `/api/council/cycle` for the autonomous daily decision cycle.
3. Render consensus, dissent, volatility tier, and policy data.

### Settings

1. GET `/api/strategy/config`.
2. Edit validated strategy values.
3. PUT `/api/strategy/config`.
4. Backend applies valid values to the running process.

## 5. Mock and live behavior

||| Condition | Behavior ||
||---|---|
||| Alpaca credentials absent | Safe mock account, screening, council, and order behavior ||
||| Alpaca credentials present | Calls configured Alpaca paper/data APIs ||
||| Invalid request | HTTP 422; no broker call ||
||| Trade in mock mode | Validated only; `submitted: false` ||
||| Option snapshot fails for one symbol | That symbol is skipped from screening ||
||| Non-finite input | Rejected/sanitized into a safe validation response ||
||| Strategy screen live failure | Returns `mode: "live"` plus `live_error` instead of mock fallback ||
||| Council cycle live failure | Returns HTTP 502 instead of silently using mock portfolio ||
||| Agent run | Returns `order_intents` for `INITIATE` directives, but never submits orders ||

### Auth (session + CSRF, 2026-09-01)

The backend enforces authentication on mutating routes and the agent endpoint:

| Route | Auth Required | Method |
|-------|---------------|--------|
| `POST /api/trade` | Yes (session + CSRF) | Double-submit cookie |
| `POST /api/trade/preflight` | Yes (session + CSRF) | Double-submit cookie |
| `PUT /api/strategy/config` | Yes (session + CSRF) | Double-submit cookie |
| `POST /api/agent/run` | Yes (session + CSRF) | Double-submit cookie |

**Login flow:**
1. `POST /api/auth/login` with `{ username, password }` → returns `200` with `csrf_token` in body, sets `ao_session` cookie (HttpOnly, 24h).
2. Client stores `csrf_token` and includes it as `X-CSRF-Token` header on mutating requests.
3. `GET /api/auth/me` returns user info if session valid, `401` if not.
4. `POST /api/auth/logout` clears the session.

**CSRF protection:** Double-submit pattern — the login response body carries the token; the cookie is HttpOnly so JS cannot read it. Mutating endpoints reject with `403` if the header is missing or mismatched.

**Rate limiting:** `5` login attempts per minute per IP (in-process counter, 60s sliding window). Excess returns `429` with "Too many login attempts".

**Dev credentials (hackathon scope, hardcoded in `backend/app/auth.py`):**
- Username: `DitJiZak_IT_BOYS`
- Password: `alpacaitboys`

Credentials must never be committed or placed in documentation.

## 6. Current gaps

1. Response model coverage is partial but expanding.
2. Alpaca retry/backoff and structured request logging are not complete.
3. Duplicate order/idempotency protection needs review.
4. CORS currently allows all origins for local development.
5. Strategy PUT values are process-local without PostgreSQL persistence.
6. Live Alpaca verification still requires a paper account and explicit
   authorization; no real order should be submitted during tests.
7. Frontend order-history wiring remains outside the current backend-only scope.

## 7. Verification checklist

- `GET /health` returns 200.
- `/api` routes return expected mock responses without credentials.
- Legacy routes without `/api` return 404.
- Invalid config and trade inputs return 422.
- Valid OCC option mock order returns 200 with `submitted: false`.
- Council assess and cycle routes return valid mock responses.
- Full backend/agent tests pass.
- Council-cycle chaos tests cover Alpaca rate-limit, timeout, and mid-flight failure paths.
- Live tests use Alpaca paper trading only.

## 8. Source of truth

Backend:

- `backend/app/main.py`
- `backend/app/alpaca_client.py`
- `backend/app/routes/portfolio.py`
- `backend/app/routes/strategy.py`
- `backend/app/routes/council.py`
- `backend/app/routes/trade.py`
- `agent/decision_engine.py`
- `agent/council/`

Frontend integration:

- `frontend/lib/api.ts`
- `frontend/app/components/StrategyConfigCard.tsx`
- `frontend/app/components/AgentControl.tsx`
