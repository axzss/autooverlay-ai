# AutoOverlay AI — Backend / Frontend API Contract

Status: Working contract for the current hackathon MVP

## 1. System relationship

```text
Frontend (Next.js)
        |
        | HTTP JSON requests
        v
Backend (FastAPI)
        |
        +--> DecisionEngine / strategy modules
        |
        +--> Alpaca Trading API (paper account)
        |
        +--> Mock data fallback when Alpaca is not configured
```

The backend is the application API. Alpaca is the source of truth for live account,
positions, option snapshots, and broker orders. The current backend does not use a
database; strategy configuration is held in process memory.

## 2. Endpoint map

| Backend endpoint | Method | Frontend purpose | Current source |
|---|---:|---|---|
| `/health` | GET | Backend and Alpaca availability check | `backend/app/main.py` |
| `/portfolio` | GET | Account summary and holdings | `backend/app/routes/portfolio.py` |
| `/strategy/screen` | GET | Find and rank covered-call candidates | `backend/app/routes/strategy.py` |
| `/strategy/screen` | POST | Screen with symbols and filters | `backend/app/routes/strategy.py` |
| `/strategy/config` | GET | Load strategy parameters | `backend/app/routes/strategy.py` |
| `/strategy/config` | PUT | Update strategy parameters | `backend/app/routes/strategy.py` |
| `/trade` | POST | Validate and submit an order | `backend/app/routes/trade.py` |
| `/trade/orders` | GET | Load broker orders | `backend/app/routes/trade.py` |

The FastAPI app currently registers these routes without an `/api` prefix.

## 3. Endpoint details

### GET `/health`

Response:

```json
{
  "status": "ok",
  "alpaca_configured": false
}
```

`alpaca_configured` is `true` only when the required trading environment values
are available. This endpoint does not make a network request to Alpaca.

### GET `/portfolio`

Response shape:

```json
{
  "mode": "mock",
  "account_info": {},
  "positions": []
}
```

Live mode reads the Alpaca account and positions. Mock mode returns bundled data
so the frontend can run without credentials. A live API failure returns `mode:
error` and includes a safe error detail plus any data already loaded.

Frontend target: dashboard portfolio cards, account summary, and assets/holdings
views. The shared frontend client defines this call in `frontend/lib/api.ts` as
`api.getPortfolio()`.

### GET or POST `/strategy/screen`

The screening route supports covered-call screening over held US-equity positions.

GET query parameters:

- `symbols`: comma-separated ticker symbols
- `min_open_interest`: minimum option open interest
- `top_n`: maximum candidates, from 1 to 25
- `full`: whether to run DecisionEngine enrichment

POST body:

```json
{
  "symbols": ["AAPL"],
  "min_open_interest": 0,
  "max_annualized_return": 10.0,
  "top_n": 5,
  "full": true
}
```

Response shape:

```json
{
  "mode": "mock",
  "strategy": "covered_call",
  "count": 1,
  "candidates": [
    {
      "symbol": "AAPL",
      "option_symbol": "AAPL...",
      "strike_price": 190.0,
      "expiration_date": "2026-09-18",
      "annualized_return_rate": 0.18,
      "risk_score": 35,
      "action": "INITIATE_POSITION",
      "rationale": "...",
      "reasoning_trace": []
    }
  ],
  "portfolio_context": {}
}
```

The route combines Alpaca option snapshots with `DecisionEngine`. The engine
adds risk score, action, rationale, reasoning trace, and portfolio context.

Frontend target: dashboard strategy cards and terminal agent feed. The shared
client defines `api.screenStrategies()` and `normalizeScreenings()` in
`frontend/lib/api.ts`.

### GET `/strategy/config`

Returns the active strategy configuration:

```json
{
  "config": {
    "take_profit_pct": 0.6,
    "stop_loss_mult": 2.0,
    "roll_delta": 0.4,
    "roll_min_dte": 7,
    "delta_min": 0.15,
    "delta_max": 0.35,
    "dte_min": 7,
    "dte_max": 45,
    "max_concentration_pct": 25.0,
    "min_cash_reserve_pct": 10.0
  },
  "valid": true
}
```

The initial value is loaded from `STRATEGY_CONFIG_JSON` when the backend module
starts. A successful PUT changes the in-process value until the process restarts.

### PUT `/strategy/config`

Accepts the same configuration object as the GET response. Invalid ranges return
HTTP 422 with a list of validation errors. Valid updates affect future strategy
screening requests in the current process.

Frontend target: strategy settings panel. Current component:
`frontend/app/components/StrategyConfigCard.tsx`.

Integration note: this component currently calls `/api/strategy/config` directly,
while the backend route is `/strategy/config` and the shared API client uses the
configured backend base URL. This path should be unified before production use.

### POST `/trade`

Request:

```json
{
  "symbol": "AAPL",
  "qty": 1,
  "side": "sell",
  "type": "market",
  "time_in_force": "day"
}
```

The endpoint validates quantity, side, order type, time-in-force, limit price,
and OCC option symbols. Option orders require `day` time-in-force.

Without Alpaca credentials it returns a validated simulated order and does not
submit anything. With credentials it submits to Alpaca paper trading and returns
selected broker order fields.

Frontend target: trade/overlay controls. The shared client defines
`api.placeTrade()` in `frontend/lib/api.ts`.

### GET `/trade/orders`

Returns open broker orders in live mode or bundled mock orders without credentials.
This endpoint exists in the backend but is not currently exposed as a dedicated
method in `frontend/lib/api.ts`; frontend order-history components should use this
endpoint instead of assuming orders are included in `/portfolio`.

## 4. Frontend-to-backend data flow by UI area

### Dashboard

1. Frontend requests `/portfolio`.
2. Backend loads Alpaca account/positions or mock data.
3. Dashboard renders account value, cash, holdings, and portfolio metrics.
4. Strategy widgets request `/strategy/screen` when connected to the API.

### Assets

1. Frontend uses portfolio/position data.
2. Positions come from `/portfolio` in live mode.
3. Option opportunities come from `/strategy/screen`.
4. Trade history should come from `/trade/orders`.

### Terminal / agent feed

1. Frontend calls `/strategy/screen`.
2. Backend calls the strategy engine.
3. Candidate records receive risk and reasoning fields.
4. Frontend normalizes candidates through `normalizeScreenings()` and
   `toFeedEntry()` before rendering the activity feed.

### Settings

1. Settings loads `/strategy/config`.
2. User edits risk and entry parameters.
3. Settings sends a PUT to `/strategy/config`.
4. Backend validates and updates the in-process configuration.

## 5. Mock and live behavior

| Condition | Backend behavior |
|---|---|
| Alpaca credentials absent | Portfolio, screening, and orders use safe mock behavior |
| Alpaca credentials present | Backend requests Alpaca paper-trading/data APIs |
| Live account request fails | Portfolio returns an error mode with safe partial data |
| Live option snapshot fails for one symbol | That symbol is skipped during screening |
| Trade validation fails | FastAPI returns HTTP 422; no broker call |
| Trade credentials absent | Order is validated but not submitted |

Never place real credentials in source control or documentation.

## 6. Current contract gaps

1. `StrategyConfigCard.tsx` uses `/api/strategy/config` directly instead of the
   configured backend base URL and `/strategy/config` path.
2. `PortfolioSnapshot` declares `orders`, but `/portfolio` currently returns only
   account information and positions. Orders should be loaded from `/trade/orders`.
3. The frontend has `api.placeTrade()`, but individual UI execution wiring should
   be verified before enabling real paper submissions.
4. `AgentControl` currently displays a Run Agent button but does not call a
   backend execution endpoint. Screening and execution are separate flows today.
5. The backend strategy configuration is process-local. Restarting the backend
   resets PUT changes unless `STRATEGY_CONFIG_JSON` is supplied.
6. CORS currently allows every origin. This is acceptable for local hackathon
   development but should be restricted for deployment.

## 7. Recommended implementation order

1. Unify the strategy-config frontend path with `API_BASE_URL`.
2. Add a typed `getOrders()` method and connect order-history UI.
3. Add an explicit agent-run endpoint only when the desired execution workflow is
   confirmed.
4. Add structured API error responses and request correlation IDs.
5. Add persistence later for configuration, recommendations, reports, and audit
   history. PostgreSQL is not required for the current stateless MVP.
6. Restrict CORS and add deployment-specific settings before production.

## 8. Verification checklist

- Backend tests run with no real Alpaca credentials.
- `/health` returns HTTP 200.
- `/portfolio` works in mock mode.
- `/strategy/screen` returns candidates and engine enrichment.
- Invalid `/strategy/config` updates return HTTP 422.
- Valid strategy configuration updates affect screening in the running process.
- Invalid trade payloads are rejected before any Alpaca call.
- Mock trade submissions clearly report `submitted: false`.
- Frontend uses the same paths and response fields documented here.
- Live Alpaca testing is performed only with a paper account.

## 9. Source of truth

Backend implementation:

- `backend/app/main.py`
- `backend/app/alpaca_client.py`
- `backend/app/routes/portfolio.py`
- `backend/app/routes/strategy.py`
- `backend/app/routes/trade.py`
- `agent/decision_engine.py`
- `agent/config.py`

Frontend integration:

- `frontend/lib/api.ts`
- `frontend/app/components/StrategyConfigCard.tsx`
- `frontend/app/components/AgentControl.tsx`
- `frontend/app/components/terminal/TerminalClient.tsx`
- `frontend/app/components/TradeLog.tsx`
- `frontend/app/components/trading/TradeHistory.tsx`
