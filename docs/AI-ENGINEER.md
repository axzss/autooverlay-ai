# AI-ENGINEER — The Agent Layer & Risk Infrastructure

Everything under `agent/`. This is the core engine that decides what to trade, when to exit, and what to reject.

Design principle throughout: **Every output must be explainable, auditable, and backed by verifiable risk metrics**. No recommendation leaves this layer without a `reasoning_trace` listing the checks it passed, and no directive leaves `daily_cycle` without `provenance` naming the rule that produced it.

---

## Module map

```
agent/
├── config.py                  StrategyConfig — every tunable parameter
├── monte_carlo.py             Monte Carlo simulation engine (Merton Jump Diffusion, VaR 95%, Sortino)
├── strategies/
│   ├── covered_call.py        Screen covered-call candidates
│   └── cash_secured_put.py    Screen CSP candidates
├── decision_engine.py         Rank candidates, assign risk score, emit trace
├── exit_manager.py            Take-profit / stop-loss / roll on open positions
├── portfolio_analyst.py       Concentration, cash reserve, sector caps
├── orchestrator.py            Execution runtime orchestrator
├── order_executor.py          Order construction (mid-price limit orders only)
└── council/
    ├── personas.py            6 investor personas
    ├── engine.py              Consensus + dissent aggregation
    ├── graham_principles.py   Ch.14 defensive tests, Ch.20 margin of safety
    ├── mr_market.py           Ch.8 market-mood regime classifier
    ├── fundamentals.py        Free fundamentals provider + TTL cache
    ├── handoff.py             Report HANDOFF → TierPolicy
    ├── risk_mitigation.py     Pre-Trade Kill-Switch
    ├── report.py              Council report rendering
    ├── daily_cycle.py         Unified orchestrator tying all 7 steps together
    └── run_full_assessment.py Batch run over the 8-symbol universe
```

---

## 1. Technical Evaluation & System Criticisms

### A. Ephemeral State Storage & Reset Vulnerability
- **Criticism:** Storing consecutive stop-loss counters and high-water marks in transient memory or `/tmp` creates severe vulnerabilities upon process restart.
- **System Impact:** Reboots wipe the `consecutive_stop_losses` counter back to `0` and reset `peak_equity` to current equity, effectively blinding multi-day drawdown evaluation.
- **Risk Mitigation:** SQLite WAL persistent state store (`docs/.cache/agent_state.db`) records `cycle_run`, `directive`, `exit_event`, and `peak_equity` across session restarts.

### B. Unresolved Contract Executions & Market Order Drag
- **Criticism:** Abstract strategy directives outputting policy parameters (`delta_min/max`, `strategy_allowed`) without concrete OCC option symbols cause backend order handlers to fall back to market orders.
- **System Impact:** Market orders on options cross the full bid-ask spread, destroying **3–10% of total premium** instantaneously on entry.
- **Risk Mitigation:** Strict OCC symbol builder (`resolve_option_contract()`) maps DTE/Delta policy guidelines to concrete strikes and locks execution strictly to **Mid-Price Limit Orders** ($\text{Limit} = \frac{\text{Bid} + \text{Ask}}{2}$). Market orders are explicitly blocked for options.

### C. Asymmetric Expectancy Realities (60% Profit / 200% Stop-Loss)
- **Criticism:** The 60% take-profit / 200% stop-loss asymmetry means 1 losing trade erases 3.3 winning trades.
- **System Impact:** If win rates drop below 77%, net expected return turns negative.
- **Risk Mitigation:** Monte Carlo VaR simulation engine (`monte_carlo.py`) integrates Merton Jump Diffusion to stress-test 1,000 multi-day portfolio paths under non-Gaussian tail-risk shocks, enforcing portfolio-level Net Delta ($\le 0.30 \times \text{NAV}$) and Vega ($\le 0.15 \times \text{NAV}$) caps.

---

## 2. Config & Tuning (`config.py`)

Single source of truth for every tunable parameter. Editable at runtime via `PUT /api/strategy/config` or environment variables.

```python
# Exit rules
take_profit_pct: float = 0.60        # close at >= 60% of premium captured
stop_loss_mult:  float = 2.0         # stop at loss >= 2x initial premium
roll_delta:      float = 0.40        # roll when |delta| > 0.40
roll_min_dte:    int   = 7           # roll when DTE < 7

# Entry filters
delta_min: float = 0.15
delta_max: float = 0.35
dte_min:   int   = 7
dte_max:   int   = 45

# Portfolio & Sector guards
max_concentration_pct:        float = 25.0   # max % portfolio per ticker
min_cash_reserve_pct:         float = 10.0   # min % cash reserve after collateral
max_sector_concentration_pct: float = 40.0   # tech-complex sector cap
sector_cap_group:             tuple = ("AAPL", "MSFT", "NVDA", "QQQ")

# Kill-switch thresholds
kill_max_drawdown_pct:        float = 5.0
kill_max_single_day_loss_pct: float = 2.0
kill_consecutive_stop_losses: int   = 3
overlay_only_drawdown:        bool  = True
```

---

## 3. Four-Layer Risk Architecture

1. **Layer 1: Pre-Trade Kill-Switch (`risk_mitigation.py`)**
   - Checked *first* before any cycle step. Halts new position generation immediately if drawdown, single-day loss, or stop-loss limits are breached.
2. **Layer 2: Persistent State Engine (`agent/state/`)**
   - SQLite WAL state store tracking cross-cycle events and high-water marks.
3. **Layer 3: Hedge Fund Council & Fallback Engine (`agent/council/`)**
   - Six investor personas, Benjamin Graham Chapter 14 defensive checks, Mr. Market regime classification, and Monte Carlo VaR risk assessment.
4. **Layer 4: Execution Contract Resolver (`order_executor.py`)**
   - Exact OCC symbol parsing and mandatory mid-price limit order guard rails.
