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

Canonical routes use no prefix. Backend compatibility aliases are also exposed
under `/api` for portfolio, strategy, and trade clients.

Supported compatibility paths include:

- `/api/portfolio`
- `/api/strategy/screen`
- `/api/strategy/config`
- `/api/trade`
- `/api/trade/orders`

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

Tests must not contact Alpaca or depend on real credentials. Current verification baseline after the latest changes: `109 passed, 1 skipped` with one Starlette/httpx deprecation warning.

## Frontend integration notes

- Shared frontend API calls are in `frontend/lib/api.ts` and use `NEXT_PUBLIC_API_BASE_URL`.
- `StrategyConfigCard.tsx` currently calls `/api/strategy/config` directly; the backend now supports this compatibility alias, although the shared API client remains preferable for consistency.
- `/portfolio` returns account and positions, while `/trade/orders` returns orders. The frontend portfolio type currently declares orders inside the portfolio snapshot, so this contract should be aligned later.
- `AgentControl.tsx` currently has a Run Agent button without a dedicated backend execution endpoint.

## Changes completed

### Strategy configuration startup

- Changed strategy route initialization from `StrategyConfig()` to
  `StrategyConfig.from_env()`.
- Backend now reads `STRATEGY_CONFIG_JSON` at startup.
- Added a regression test proving environment overrides appear through
  `GET /strategy/config`.

### Frontend/API compatibility

- Added backend-only `/api` aliases without changing frontend files.
- Registered portfolio, strategy, and trade routers both at canonical paths and
  under the `/api` prefix.
- `/api/strategy/config` returns the same contract as `/strategy/config`.
- `/api/trade` still validates bad payloads before any broker call.
- Added route tests for `/api/portfolio`, `/api/trade`, and
  `/api/trade/orders`.

### Documentation

- Added `specials/BACKEND_FRONTEND_API.md` with endpoint contracts, frontend
  consumers, data flow, mock/live behavior, known gaps, and verification steps.
- Added this `backend/MEMORY.md` as the backend-specific project memory.

### Verification and delivery

- Created and ran focused `hermes-verify-` scripts for the changed API behavior.
- Verified API status codes and canonical/alias strategy-config parity.
- Ran the complete backend and agent test suite successfully.
- Latest commit for API aliases: `8b93d40 fix(backend): expose api compatibility routes`.
- No frontend files were modified by the alias change.

## Not finished / remaining work

### Backend/API integration

1. Add a typed frontend orders method and connect order history to
   `/trade/orders` when frontend work is allowed.
2. Decide and implement an explicit backend agent-run endpoint. The current
   `AgentControl` button has no execution endpoint behind it.
3. Add response models and consistent structured error responses.
4. Add request correlation IDs and structured logging.
5. Add safe retry/backoff policy for transient Alpaca failures.
6. Review order idempotency and duplicate-submission protection.
7. Restrict CORS for deployment instead of allowing every origin.
8. Add a readiness check separate from the basic `/health` endpoint if needed.

### Persistence

9. PostgreSQL is not implemented and is not required for the current stateless
   MVP. Add it only when persistent strategy configuration, recommendations,
   screening history, council reports, risk events, or audit logs are required.
10. If persistence is added, keep Alpaca as the source of truth for live account,
    positions, and broker orders; PostgreSQL should store application history and
    audit data.

### Live verification

11. Live Alpaca API verification has not been performed in this work because no
    credentials were required. It must use a paper account and local environment
    variables only.

### Known non-blocking warning

12. The test suite still reports a Starlette/httpx deprecation warning. It does
    not currently fail tests, but dependency compatibility should be reviewed
    later.

## Change discipline

- Read and trace existing code before editing.
- Use tests for behavior changes.
- Run focused tests and the full backend/agent suite after changes.
- Stage only intended files.
- Do not commit secrets, generated files, or scratch artifacts.
- Do not submit paper orders during tests.
