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
PYTHONPATH=.. uvicorn app.main:app --reload

# 3. Frontend
cd frontend && npm install && npm run dev
```

Open http://localhost:3000/dashboard

## MCP server

This repo now installs the Alpaca MCP server into the backend virtualenv.

- Added to `backend/requirements.txt`: `alpaca-mcp-server>=2.0`
- Project-local entrypoint: `backend/.venv/Scripts/alpaca-mcp-server.exe`

### VS Code

Configure VS Code’s MCP client (`C:\Users\<you>\AppData\Roaming\Code\User\mcp.json`) to use the venv entrypoint and load `backend/.env`:

```json
{
  "servers": {
    "alpaca": {
      "command": "C:/path/to/autooverlay-ai/backend/.venv/Scripts/alpaca-mcp-server.exe",
      "args": [
        "--env-file",
        "C:/path/to/autooverlay-ai/backend/.env"
      ]
    }
  }
}
```

Restart VS Code, then try: “What is my Alpaca account balance and buying power?”

Note: the MCP server is a development helper, not required by the web app itself.

```bash
# Tests — run both suites (agent + backend)
pytest agent/tests backend/tests -q     # 248 passed, 1 skipped

# Frontend gates
cd frontend && npx tsc -p tsconfig.json --noEmit && npm run build
```

## Repo layout

```
agent/          strategies, decision engine, exit manager, portfolio analyst, monte_carlo
  council/      6 personas, Graham principles, Mr. Market, handoff, risk_mitigation,
                daily-cycle orchestrator
backend/        FastAPI app, routes, Alpaca client, tests
frontend/       Next.js UI, typed API client
docs/           full documentation — start at docs/README.md
```
