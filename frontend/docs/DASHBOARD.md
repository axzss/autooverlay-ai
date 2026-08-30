# Frontend Dashboard Documentation

AutoOverlay AI frontend is a Next.js app in `frontend/`. This file explains what each dashboard element does, what was changed, and what remains purely visual/interactive.

## Pages

- `/dashboard` — main workspace: portfolio, agent control, reasoning trace, charts.
- `/assets` — portfolio holdings and Recent History.
- `/terminal` — screening feed, Daily Cycle, agent run preview, Manual Trade.
- `/council` — council assessment board.
- `/settings` — live strategy parameters.

## Dashboard elements and functions

### Header
- Brand + link to dashboard.
- Status pills: `VPS: ONLINE` and `PAPER TRADING`.
- Mobile nav trigger.

Removed decorative icons: Deploy, Layout, User.

### Sidebar / MobileSidebar
- Primary nav: Dashboard, Assets, Terminal, Council, Settings.

Removed non-functional items: Docs, Support, Deploy Logic.

### Metric cards
- TOTAL VALUE: `account_info.portfolio_value`
- DAILY P&L: `equity - last_equity`
- BUYING POWER: `account_info.cash`

### AgentStatusCard
- Backend health check via `/api/health`.
- Alpaca connection status.
- Auto-refresh every 30s.

### AgentControl
- Run agent: `POST /api/agent/run`
- Shows directives, order intents, kill-switch HALT reasons.
- Approve order: sends `POST /api/trade` for selected intent.

### ThoughtProcess
- Renders reasoning trace grouped by symbol.
- Raw/grouped toggle.

### UnderlyingAssets
- Equity positions from `/api/portfolio`.
- Columns: ASSET, SHARES, AVG PRICE, CURRENT.

### ActiveOverlayContracts
- Option positions from `/api/portfolio`.
- Parses OCC symbol, shows CALL/PUT, strike, expiry, DTE, qty, market value.

### PortfolioStats
- Total assets from live portfolio value.
- Diversification score badge.

### RecentHistory
- Order history from `/api/portfolio` -> `orders`.
- Columns: Date, Action, Ticker, Status, Realized P&L.

### ManualTradePanel
- Form to submit trades to `POST /api/trade`.
- Fields: symbol, side, qty, order type, TIF, limit price.

### StrategyConfigCard
- Editable strategy parameters.
- Persists via `/api/strategy/config`.

## Notes
- Health endpoint used by frontend is `/api/health`; backend exposes `/health`.
- `/api/portfolio` now includes `orders` from Alpaca for Recent History.
