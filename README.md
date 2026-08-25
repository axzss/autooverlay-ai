# AutoOverlay AI

Agentic options-income overlay for existing equity portfolios — built for the
**Alpaca AI Trading Agents Hackathon (Track 04)**.

AutoOverlay AI screens your holdings, evaluates covered calls and cash-secured
puts, produces reasoned recommendations with risk scoring, and executes or logs
actions through the Alpaca **paper trading** API.

## Stack

- **Frontend:** Next.js (App Router) + Tailwind CSS — Dashboard, Assets, Terminal, Settings
- **Backend:** FastAPI — portfolio / trade / strategy routes
- **Agent:** Python decision engine + strategy modules (CSP, covered call)
- **Broker:** Alpaca Trading API (paper environment, real market data)

## Quick Start

```bash
# 1. Configure credentials locally (never commit .env)
cp .env.example .env   # fill in your paper-trading keys

# 2. Backend
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload

# 3. Frontend
cd frontend && npm install && npm run dev
```

Or with Docker: `docker compose up --build`

## Repo Layout

```
agent/      decision engine, orchestrator, order executor, strategies/
backend/    FastAPI app + routes + tests
frontend/   Next.js UI
docs/       design notes
scripts/    deploy / monitoring helpers
```

## Team

- axzss — repo owner, frontend + backend + agent
- AjiNurAji — collaborator
- zmdinata — collaborator

## Security

- No secrets are committed. All credentials load from environment variables.
- `.env` is gitignored; `.env.example` documents required variables.
