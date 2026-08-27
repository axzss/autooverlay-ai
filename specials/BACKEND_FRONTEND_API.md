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

### GET/PUT `/api/strategy/config`

The configuration includes entry, exit, delta, DTE, concentration, and cash
reserve parameters. Initial values can come from `STRATEGY_CONFIG_JSON`.
Valid PUT changes remain in process memory until restart. Invalid values return
HTTP 422 and do not replace the active configuration.

### GET/POST `/api/council/assess`

Runs the council personas for requested symbols. Without Alpaca credentials it
uses bundled snapshots. The response contains mode, assessment count, symbol
tier/policy, consensus score, recommendation, persona verdicts, and dissent.

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
  "symbol": "AAPL240621C00175000",
  "qty": 1,
  "side": "sell",
  "type": "limit",
  "time_in_force": "day",
  "limit_price": 2.5
}
```

Validation covers quantity, side, order type, time-in-force, limit price, equity
symbols, and OCC option symbols. Valid OCC symbols are supported for covered
calls/CSP flows. Option orders require `day` time-in-force.

Without Alpaca credentials:

```json
{
  "mode": "mock",
  "submitted": false
}
```

No broker request is made in mock mode. With credentials, the backend submits to
the configured Alpaca paper-trading endpoint.

Timeouts, connection failures, non-2xx responses, invalid JSON, and unexpected
Alpaca response shapes are normalized by the client and surfaced as HTTP 502 by
the trade/order routes.

### GET `/api/trade/orders`

Returns live Alpaca orders when configured, otherwise bundled mock orders. This
is the order-history source; portfolio data does not embed broker orders.

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

|| Condition | Behavior ||
|---|---|
|| Alpaca credentials absent | Safe mock account, screening, council, and order behavior ||
|| Alpaca credentials present | Calls configured Alpaca paper/data APIs ||
|| Invalid request | HTTP 422; no broker call ||
|| Trade in mock mode | Validated only; `submitted: false` ||
|| Option snapshot fails for one symbol | That symbol is skipped from screening ||
|| Non-finite input | Rejected/sanitized into a safe validation response ||
|| Strategy screen live failure | Returns `mode: "live"` plus `live_error` instead of mock fallback ||
|| Council cycle live failure | Returns HTTP 502 instead of silently using mock portfolio ||
|| Agent run | Returns `order_intents` for `INITIATE` directives, but never submits orders ||

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
