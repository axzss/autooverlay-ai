# AutoOverlay AI — Project Descriptions

## Short Description

AutoOverlay AI is an autonomous options overlay system that turns equity portfolios into income machines. A six-persona council analyzes underlyings and selects covered calls or puts, executing through Alpaca with a kill switch and nine-check risk gate.

## Long Description

AutoOverlay AI is an autonomous options overlay system that turns existing equity portfolios into income-generating machines. At its core is a six-persona council engine — Buffett, Graham, Lynch, Munger, Dalio, and Your Humble Servant — that analyzes underlyings, evaluates options chains, and selects high-probability covered calls and cash-secured puts.

The system operates through a four-stage daily cycle:

1. **Kill-Switch Check**: Every cycle begins with a portfolio-wide risk assessment. If NAV drawdown exceeds 5%, single-day losses exceed 2%, or three consecutive stop-loss exits occur, trading halts immediately.

2. **Council Assessment**: For each underlying in the portfolio universe, the six personas vote BUY, HOLD, or SELL. Consensus scores, dissent notes, and Mr. Market’s mood feed into the final recommendation.

3. **Option Screening**: When INITIATE directives are generated, the system selects option contracts using tiered policies — delta ranges, max DTE limits, position sizing multipliers, and allowed strategies adapt to volatility regime. Concentration caps prevent overexposure to any single sector or underlying.

4. **Execution & Audit**: Approved orders are submitted to Alpaca’s paper-trading API with full idempotency. Every intent is recorded with a risk decision, broker response, and run ID. A persistent audit ledger enables full replay and accountability.

Architecture highlights:
- FastAPI backend with async event loop and worker-threaded Alpaca calls
- React + Tailwind frontend with Playwright E2E tests
- JSON-backed peak-equity store for kill-switch memory across restarts
- Environment-variable configuration for dry-run, mock, and live modes
- Systemd user service for automatic restart and journal logging

Built for hackathon speed without sacrificing production safety. Currently running in paper-trading mode with a live Alpaca account, and can switch to live execution via a single environment variable change.
