# Backend Project Memory

## Project purpose

AutoOverlay AI is an agentic options-income overlay for the Alpaca AI Trading Agents Hackathon Track 04. The backend exposes portfolio, strategy-screening, configuration, and trade APIs for the Next.js frontend.

## Current architecture

- Framework: FastAPI
- Python runtime: 3.11
- Broker integration: Alpaca paper-trading and options-data REST APIs through `httpx`
- Agent integration: `agent.decision_engine.DecisionEngine`
- Persistence: none yet; the MVP is stateless
- Strategy configuration: in-process singleton, optionally initialized from `STRATEGY_CONFIG_JSON`
- Safe fallback: mock account, positions, candidates, and orders when Alpaca credentials are absent

## Main backend endpoints

- `GET /health` — backend status and Alpaca configuration status
- `GET /portfolio` — account and positions
- `GET /strategy/screen` — covered-call screening
- `POST /strategy/screen` — filtered covered-call screening
- `GET /strategy/config` — active strategy parameters
- `PUT /strategy/config` — validate and update strategy parameters
- `POST /trade` — validate and submit or simulate an order
- `GET /trade/orders` — list live or mock orders

The FastAPI routes currently do not use an `/api` prefix.

## Important behavior

- Alpaca credentials are read from environment variables only.
- Required trading variables are `ALPACA_KEY`, `ALPACA_SECRET`, and `ALPACA_BASE_URL`.
- The correct Alpaca secret header is `APCA-API-SECRET-KEY`.
- Option orders must use `day` time-in-force and valid OCC symbols.
- Invalid strategy configuration and trade payloads are rejected with HTTP 422.
- Mock trade responses must clearly indicate that no broker order was submitted.
- Never put Alpaca credentials in source code, tests, documentation, or commits.

## Strategy flow

1. Load held US-equity positions.
2. Retrieve option snapshots for each eligible underlying in live mode.
3. Build covered-call candidates from option quotes and metadata.
4. Apply open-interest and annualized-return filters.
5. Enrich candidates with `DecisionEngine` risk score, action, rationale, and reasoning trace.
6. Return normalized JSON for the frontend terminal and strategy views.

Supported decision actions:

- `INITIATE_POSITION`
- `HOLD_POSITION`
- `MONITOR_CLOSELY`

## Testing

Use the project virtual environment:

```bash
source .venv/Scripts/activate
python -m pytest backend/tests agent/tests -q
```

Tests must not contact Alpaca or depend on real credentials. Current verification baseline after the latest changes: `104 passed, 1 skipped` with one Starlette/httpx deprecation warning.

## Frontend integration notes

- Shared frontend API calls are in `frontend/lib/api.ts` and use `NEXT_PUBLIC_API_BASE_URL`.
- `StrategyConfigCard.tsx` currently calls `/api/strategy/config` directly; this does not match the backend's `/strategy/config` route and should be unified later.
- `/portfolio` returns account and positions, while `/trade/orders` returns orders. The frontend portfolio type currently declares orders inside the portfolio snapshot, so this contract should be aligned later.
- `AgentControl.tsx` currently has a Run Agent button without a dedicated backend execution endpoint.

## Current changes

- Strategy routes now initialize configuration with `StrategyConfig.from_env()` so environment overrides work at backend startup.
- A regression test verifies startup configuration overrides through `GET /strategy/config`.
- Endpoint relationship documentation is in `specials/BACKEND_FRONTEND_API.md`.

## Future work order

1. Unify frontend strategy-config URL handling.
2. Add a typed frontend orders method and connect order history.
3. Decide and implement an explicit agent-run endpoint.
4. Add structured error responses, request IDs, and restricted deployment CORS.
5. Add PostgreSQL only when persistent audit history, reports, recommendations, or configuration is required.

## Change discipline

- Read and trace existing code before editing.
- Use tests for behavior changes.
- Run focused tests and the full backend/agent suite after changes.
- Stage only intended files.
- Do not commit secrets, generated files, or scratch artifacts.
- Do not submit paper orders during tests.
