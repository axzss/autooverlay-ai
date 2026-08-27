# Backend Project Memory

## Project purpose

AutoOverlay AI is an agentic options-income overlay for the Alpaca AI Trading Agents Hackathon Track 04. The backend exposes portfolio, strategy-screening, configuration, council, and trade APIs for the Next.js frontend.

## Current architecture

- Framework: FastAPI
- Python runtime: 3.11
- Broker integration: Alpaca paper-trading and options-data REST APIs through `httpx`
- Agent integration: `agent.decision_engine.DecisionEngine` and `agent.council`
- Persistence: none; the MVP is stateless
- Strategy configuration: in-process singleton, initialized from `STRATEGY_CONFIG_JSON` when provided
- Safe fallback: mock account, positions, candidates, council assessments, and orders when Alpaca credentials are absent

## Main backend endpoints

Public API routes use the `/api` prefix exclusively:

- `GET /health` — backend status and Alpaca configuration status
- `/api/portfolio`
- `/api/strategy/screen` (GET/POST)
- `/api/strategy/config` (GET/PUT)
- `/api/council/assess` (GET/POST)
- `/api/council/cycle` (POST)
- `/api/agent/run` (POST) — recommendation-only agent cycle
- `/api/trade` (POST)
- `/api/trade/orders` (GET)

There are no duplicate application routes without the `/api` prefix. Legacy paths
such as `/portfolio` or `/trade` intentionally return HTTP 404.

## Important behavior

- Alpaca credentials are read from environment variables only.
- Required trading variables are `ALPACA_KEY`, `ALPACA_SECRET`, and `ALPACA_BASE_URL`.
- The correct Alpaca secret header is `APCA-API-SECRET-KEY`.
- Option orders must use `day` time-in-force and valid OCC symbols.
- Valid OCC symbols such as `AAPL240621C00175000` are accepted for covered-call/CSP order flows.
- Alpaca timeout, network, HTTP, invalid JSON, and invalid response shapes use `AlpacaAPIError` (a `RuntimeError` subtype).
- Live trade/order endpoint failures are exposed as HTTP 502 instead of being simulated as mock data.
- Invalid strategy configuration and trade payloads are rejected with HTTP 422.
- Non-finite values such as NaN/Infinity are sanitized in validation errors.
- Mock trade responses clearly indicate that no broker order was submitted.
- Never put Alpaca credentials in source code, tests, documentation, or commits.

## Strategy and council flow

1. Load held US-equity positions.
2. Retrieve option snapshots for each eligible underlying in live mode.
3. Build covered-call candidates from option quotes and metadata.
4. Apply open-interest and annualized-return filters.
5. Run council personas and calculate consensus, dissent, volatility tier, and policy.
6. Enrich candidates with `DecisionEngine` risk score, action, rationale, and reasoning trace.
7. Return normalized JSON for the frontend terminal and strategy views.

Supported decision actions:

- `INITIATE_POSITION`
- `HOLD_POSITION`
- `MONITOR_CLOSELY`

## Changes completed

### Strategy configuration startup

- Changed strategy route initialization from `StrategyConfig()` to `StrategyConfig.from_env()`.
- Backend now reads `STRATEGY_CONFIG_JSON` at startup.
- Added a regression test proving environment overrides appear through `GET /strategy/config`.

### API compatibility

- Added backend-only `/api` aliases without changing frontend files.
- Standardized the public backend contract on `/api` routes without changing frontend files.
- Removed duplicate portfolio, strategy, council, and trade routes without the `/api` prefix.
- Added tests for public routes and 404 responses for removed legacy paths.

### Council and security integration

- Integrated the council assessment and daily-cycle routes from the merged PR.
- Preserved NaN/Infinity validation hardening and request validation handling.
- Added security regression coverage for malformed symbols, quantities, prices, strategy values, and screening inputs.

### OCC option order validation

- Fixed order validation so a valid OCC option symbol is parsed before the shorter equity ticker rule.
- Option orders continue to require `day` time-in-force and bounded limit prices.
- Added a regression test for a valid mock covered-call option order.

### Documentation and delivery

- Added `specials/BACKEND_FRONTEND_API.md` with endpoint contracts, frontend consumers, data flow, mock/live behavior, known gaps, and verification steps.
- Added `backend/app/routes/agent.py` with recommendation-only `POST /api/agent/run`.
- The agent-run endpoint delegates to the existing council daily cycle, returns recommendations, risk summary, and reasoning, and never submits broker orders.
- This file records backend-specific implementation status and remaining work.
- No frontend files were modified during the API alias or OCC validation changes.

## Verification status

The latest local verification used the project virtual environment:

```bash
source .venv/Scripts/activate
python -m pytest backend/tests agent/tests -q
```

Latest result after Alpaca hardening, overlay wiring, order intents, live-error surfacing, and CORS config:

```text
233 passed, 1 skipped, 1 warning
```

The warning is a non-blocking Starlette/httpx deprecation warning. Python compilation also passed with `python -m compileall -q backend agent`.

### Backend hardening and contracts
14. Added `AlpacaAPIError` and normalized Alpaca timeout, network, HTTP, invalid JSON, and response-shape failures into safe backend errors.
15. Added reusable response envelopes in `backend/app/responses.py` for portfolio, screening, council, and agent-run responses.
16. Added configurable CORS via `CORS_ORIGINS`; defaults to localhost origins instead of `*`.
17. Added approval-gated `order_intents` to `POST /api/agent/run` from `INITIATE` directives. `orders_ready` remains `false`; this endpoint still never submits broker orders.
18. Live `POST /api/council/cycle` now passes normalized short option positions into `run_daily_cycle()`, so `EXIT`/`ROLL` directives can use real Alpaca overlay state instead of only mock data.
19. Live `GET /api/strategy/screen` now returns `mode: "live"` with optional `live_error` instead of silently falling back to mock data when credentials exist but Alpaca data fails.
20. Added regression coverage for Alpaca client failures, option-position normalization, council-cycle overlay wiring, order-intent generation, and live strategy error surfacing.

## Not finished / remaining work

### Backend/API integration

1. Add response models and consistent structured error responses.
3. Add request correlation IDs and structured logging.
4. Add safe retry/backoff policy for transient Alpaca failures.
5. Review order idempotency and duplicate-submission protection.
6. Restrict CORS for deployment instead of allowing every origin.
7. Add a readiness check separate from the basic `/health` endpoint if needed.

### Frontend/API integration

8. Add a typed frontend orders method and connect order history to `/trade/orders` when frontend work is allowed.
9. Keep the frontend portfolio/order response contract aligned with the backend when frontend work is allowed.

### Persistence

10. PostgreSQL is not implemented and is not required for the current stateless MVP. Add it only when persistent strategy configuration, recommendations, screening history, council reports, risk events, or audit logs are required.
11. If persistence is added, keep Alpaca as the source of truth for live account, positions, and broker orders; PostgreSQL should store application history and audit data.

### Live verification

12. Live Alpaca API verification has not been performed because no credentials were required. It must use a paper account and local environment variables only. No paper order should be submitted without explicit authorization.

### Known warning

13. The test suite still reports a Starlette/httpx deprecation warning. It does not currently fail tests, but dependency compatibility should be reviewed later.

## Change discipline

- Read and trace existing code before editing.
- Use tests for behavior changes and verify RED before implementation when practical.
- Run focused tests and the full backend/agent suite after changes.
- Stage only intended files.
- Do not commit secrets, generated files, or scratch artifacts.
- Do not submit paper orders during tests.
- Keep frontend changes out of backend-only work.
- Push only after tests and compilation are green.

## Recent commits

- `23c9531 fix(backend): accept valid OCC option symbols`
- `dba0a04 fix(backend): expose council api aliases`
- `75f3352 Merge branch 'master' into master`
- `34aecde docs(backend): record implementation status`
- `8b93d40 fix(backend): expose api compatibility routes`
- `20dbf70 fix(backend): harden Alpaca API failure handling`
- `<next-commit-hash> feat(backend): wire live option overlays, order intents, live error surfacing, and configurable CORS`
