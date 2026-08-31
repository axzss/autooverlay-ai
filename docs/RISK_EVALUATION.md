# Risk Management Evaluation & Architecture

## System Overview
AutoOverlay AI manages options overlay trading (Cash-Secured Puts and Covered Calls) with a layered risk mitigation structure.

---

## 1. Risk Evaluation & Criticism

### A. State Persistence & Memory Liquidation
- **Issue:** Prior implementations stored consecutive stop-loss counters and high-water marks in ephemeral storage (`/tmp`).
- **Mitigation:** Persistent SQLite WAL state engine (`docs/.cache/agent_state.db`) stores `cycle_run`, `directive`, `exit_event`, and `peak_equity` records across process restarts.

### B. Execution Contract Resolution
- **Issue:** Abstract strategy directives emitted policy parameters without concrete OCC option symbols, causing fallback to market order executions.
- **Mitigation:** Contract resolution layer maps target DTE/Delta to valid OCC option symbols, capping execution strictly to mid-price limit orders. Market orders are explicitly blocked for options.

### C. Quant Realities & Asymmetric Risk
- **Issue:** Fixed 60% take-profit / 200% stop-loss creates an asymmetric risk profile where 1 loss erases 3.3 wins.
- **Mitigation:** Monte Carlo Value-at-Risk (VaR) simulation integrated into strategy screening, along with portfolio-level Net Delta ($\le 0.30 \times \text{NAV}$) and Vega ($\le 0.15 \times \text{NAV}$) caps.

---

## 2. Layered Risk Architecture

1. **Layer 1: Pre-Trade Kill-Switch (`risk_mitigation.py`)**
   - Evaluates NAV / Overlay Drawdown, Single-Day Loss, and Consecutive Stop-Loss counters before any cycle execution.
2. **Layer 2: State Persistence & Ledger (`agent/state/`)**
   - SQLite WAL state store tracking cross-cycle events and high-water marks.
3. **Layer 3: Council & Fallback Engine (`agent/council/`)**
   - Deterministic 7-point Benjamin Graham defensive checks combined with Monte Carlo simulation.
4. **Layer 4: Execution Contract Resolver (`backend/app/routes/agent.py`)**
   - Exact OCC symbol matching and mid-price limit order enforcement.
