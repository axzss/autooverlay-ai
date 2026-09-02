# AutoOverlay AI

Agentic options-income overlay for existing equity portfolios — built for the
**Alpaca AI Trading Agents Hackathon, Options Alpha Agents track**.

Most investors hold equity that generates nothing while it sits there. Running an
options overlay against it by hand is time-consuming and easy to get wrong.
AutoOverlay AI does the analysis autonomously — but every recommendation has to
survive a six-person investment committee first, and **no order is ever submitted
without explicit approval and mid-price limit order verification**.

## What makes it different

**1 · Investment Council.** Six investor personas — Warren Buffett, Charlie
Munger, Ray Dalio, Benjamin Graham, Peter Lynch, Cathie Wood — each score a stock
against their own philosophy. Their verdicts combine into a consensus, and
**disagreement is shown, not smoothed over**. When the committee is split, that
is information.

**2 · Graham from the actual book.** The Graham persona implements the seven
defensive tests from Chapter 14 of *The Intelligent Investor*, plus Margin of
Safety (Ch. 20) and Mr. Market psychology (Ch. 8). Every verdict names the test
it passed or failed — e.g. *"fails test 4 (dividend record): 15y coverage only"* —
so the reasoning is auditable rather than asserted.

**3 · Monte Carlo & Pre-Trade Risk Engine.** Monte Carlo simulation engine (`agent/monte_carlo.py`) featuring Merton Jump Diffusion, 95% Value-at-Risk (VaR), and Sortino ratio downside risk stress-testing across 1,000 multi-day portfolio paths.

**4 · Institutional Risk Mitigation.** Persistent SQLite state store (`docs/.cache/agent_state.db`), Layer 1 Pre-Trade Kill-Switch, and strict OCC option contract resolution preventing market order slippage.

## Technical Architecture & Risk Control

- **Kill-switch** halts all new entries on >5% drawdown, >2% daily loss, or 3
  consecutive stop-losses — checked **first** in every cycle.
- **Concentration & Sector Guards:** Concentration cap 25% per ticker · cash reserve floor 10% · tech-complex sector cap 40% of deployed overlay capital.
- **Exit Rules:** Take profit at 60% of premium captured · stop loss at 200% of initial premium · roll on |delta| > 0.40 or DTE < 7.
- **Execution Safety:** Mandatory Mid-Price Limit Orders ($\text{Limit} = \frac{\text{Bid} + \text{Ask}}{2}$) on concrete OCC symbols (`[ROOT][YYMMDD][C/P][STRIKE]`). Market orders on options are strictly blocked.

Full details: [`docs/RISK-MANAGEMENT.md`](docs/RISK-MANAGEMENT.md) and [`docs/RISK_EVALUATION.md`](docs/RISK_EVALUATION.md).

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js App Router + Tailwind — Dashboard, Assets, Terminal, Council, Settings |
| Backend | FastAPI — 11 routes, all under `/api` except `/health` |
| Agent | Python — strategies, decision engine, exit manager, portfolio analyst, council, Monte Carlo engine, daily-cycle orchestrator |
| Broker | Alpaca paper trading API, real market data |
| Fundamentals | Free public sources, 24h cache, degrades to `INCONCLUSIVE` rather than guessing |

## Quick start

```bash
# 1. Credentials — never commit .env
cp .env.example .env        # ALPACA_KEY, ALPACA_SECRET, ALPACA_BASE_URL

# 2. Backend (works without credentials — falls back to mock data)
cd backend
pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --reload

# 3. Frontend
cd frontend && npm install && npm run dev
```

Open http://localhost:3000/dashboard

## AI router

This repo uses an OpenRouter-backed AI router for model access.

Configure these in `backend/.env`:
## AI Trading Bot & Autonomous Scheduler

AutoOverlay AI includes a background autonomous trading bot and scheduler (`backend/app/scheduler.py` via APScheduler):

- **1-Hour Autonomous Cycle**: Evaluates the 7-step investment cycle every 1 hour (configurable via `BOT_SCHEDULE_INTERVAL_HOURS`).
- **Market Hours Guard**: Checks Alpaca `/v2/clock` (with NYSE 9:30 AM - 4:00 PM EST fallback). Scheduled cycles auto-skip when markets are closed to prevent invalid rejections.
- **Atomic Concurrency Lock**: Thread-safe execution lock (`_execution_lock`) with `max_instances=1, coalesce=True` to eliminate overlapping cycles or double-order submissions.
- **Working Order De-duplication**: Queries live working orders on Alpaca before evaluating new intents, ensuring contracts already active on the exchange are never duplicated.
- **REST Endpoints**:
  - `GET /api/bot/status` — Live scheduler status, next run time, and last execution metrics.
  - `POST /api/bot/start` — Start/resume background autonomous scheduler.
  - `POST /api/bot/stop` — Stop/pause background scheduler.
  - `POST /api/bot/config` — Reconfigure interval hours or toggle live order execution.
  - `POST /api/bot/cycle` — Trigger an immediate autonomous cycle on-demand.
  - `GET /api/bot/history` — Audit trail of autonomous runs.
  - `GET /api/bot/mcp/tools` — Native MCP tool manifest exposing agent capabilities.

## MCP Server Integration

This repo supports both local VS Code MCP tooling and native backend MCP tool descriptors.

- Added to `backend/requirements.txt`: `alpaca-mcp-server>=2.0`
- Project-local entrypoint: `backend/.venv/Scripts/alpaca-mcp-server.exe`
- Web app MCP tool manifest: `GET /api/bot/mcp/tools`

```bash
AI_ROUTER_BASE_URL=https://openrouter.ai/api/v1
AI_ROUTER_API_KEY=your_openrouter_api_key
AI_ROUTER_MODEL=openai/gpt-4o-mini
```

Example:

```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AI_ROUTER_API_KEY" \
  -d "{\"model\":\"$AI_ROUTER_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hello in one sentence.\"}]}"
```

Note: the AI router is an integration point for agent features; the web app still functions without it using local/mock paths.

### Fallback LLM

If the primary AI router returns a model-not-found error or is unavailable, the backend can fall back to another OpenAI-compatible provider.

Configure in `backend/.env`:

```bash
LLM_FALLBACK_BASE_URL=https://openrouter.ai/api/v1
LLM_FALLBACK_API_KEY=your_fallback_llm_api_key
LLM_FALLBACK_MODEL=openai/gpt-4o-mini
```

Note: the fallback provider is used when the primary endpoint rejects the configured model or is unreachable.

```bash
# Tests — backend suite
pytest backend/tests -q     # 513 passed, 1 skipped

# Frontend gates
cd frontend && npx tsc -p tsconfig.json --noEmit
```

## Repo layout

```
agent/          strategies, decision engine, exit manager, portfolio analyst, monte_carlo
  council/      6 personas, Graham principles, Mr. Market, handoff, risk_mitigation,
                daily-cycle orchestrator
backend/        FastAPI app, routes, scheduler, bot API, Alpaca client, tests
frontend/       Next.js UI, typed API client
docs/           full documentation — start at docs/README.md
```
