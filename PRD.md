# Product Requirements Document (PRD)
## AutoOverlay AI — Alpaca AI Trading Agents Hackathon

**Owner:** axzss  
**Team:** AjiNurAji, zmdinata  
**Date:** 2026-08-25  
**Status:** Draft / Work In Progress

---

## 1. Problem Statement
Individual investors want income from existing equity portfolios without selling shares. Covered calls and cash-secured puts are effective, but screening, risk evaluation, and execution are manual and error-prone.

## 2. Solution
AutoOverlay AI is an agentic overlay that:
- Evaluates existing holdings
- Screens overlay opportunities (CSP / covered call)
- Produces actionable recommendations with risk scoring
- Executes via Alpaca paper trading API
- Logs activity and results in a clear UI

## 3. Target Track
AI Trading Agents Hackathon — focused on agentic trading workflow, oversight, and execution on Alpaca.

## 4. User Stories
- As a trader, I want to see portfolio value and overlay opportunities on Dashboard.
- As a trader, I want an Assets view showing holdings and past overlay trades.
- As a trader, I want a Terminal showing agent reasoning and status.
- As a trader, I want Settings for risk/strategy configuration.

## 5. Scope
### In Scope
- Next.js App Router frontend with Tailwind CSS
- FastAPI backend routes for portfolio/trade/strategy
- Python strategy stubs: cash-secured put, covered call
- Decision engine: INITIATE_POSITION / HOLD_POSITION / MONITOR_CLOSELY
- Alpaca paper trading integration

### Out of Scope (Initial)
- Live brokerage trading
- Real-time options greeks feed
- Mobile native app

## 6. Architecture
- Frontend: Next.js + Tailwind + lucide-react icons
- Backend: FastAPI
- Agent runtime: Python orchestrator + strategy modules
- Data: Alpaca REST API, mock fallbacks

## 7. Risks & Mitigations
- API key exposure → .env ignored, no secrets in repo
- Complex options data → start with mock data, wire API later
- UI mismatch → browser-automation verification

## 8. Milestones
1. Repo hygiene + clean GitHub state
2. Frontend 4 pages functional
3. Backend API scaffolded
4. Strategy/decision engine implemented
5. End-to-end paper trading flow

---

*This PRD is maintained outside the project subfolders.*
