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
- **Mitigation — BUILT:** `agent/state/peak.py` persists NAV and overlay high-water marks across cycles and restarts (`docs/.cache/peak_equity.json`, atomic write, `/tmp` fallback, gitignored). A caller may raise the mark and never lower it, so the drawdown check no longer depends on a value the caller supplies. Reads report `tracked` / `source` — an absent mark is `"absent"`, never a silent 0% drawdown. 21 tests in `agent/tests/test_peak_store.py`.
- **Still open:** the wider ledger (`cycle_run`, `directive`, `exit_event`) is **not built**. Without `exit_event`, `consecutive_stop_losses` is still within-cycle only — see `KNOWN-ISSUES.md` #11. The fundamentals cache is still in `/tmp` — #1.

### B. Unresolved Contract Executions & Market Order Drag
- **Criticism:** Abstract strategy directives outputting policy parameters (`delta_min/max`, `strategy_allowed`) without concrete OCC option symbols cause backend order handlers to fall back to market orders.
- **System Impact:** Market orders on options cross the full bid-ask spread, destroying **3–10% of total premium** instantaneously on entry.
- **Mitigation — BACKEND-OWNED:** `_pick_option_contract` in `backend/app/routes/agent.py` resolves the contract from the live option chain, and `backend/app/risk/` gates every order before the broker is contacted. Not an agent-layer deliverable; see `KNOWN-ISSUES.md` #2 for the residual gap in mock mode.

### C. Asymmetric Expectancy Realities (60% Profit / 200% Stop-Loss)
- **Criticism:** The 60% take-profit / 200% stop-loss asymmetry means 1 losing trade erases 3.3 winning trades.
- **System Impact:** If win rates drop below 77%, net expected return turns negative.
- **Partial mitigation — `agent/monte_carlo.py` exists but is NOT wired in.** Nothing imports it: `git grep monte_carlo -- agent backend` returns only the module and its own test. It is a standalone stress tool, not part of screening, and the four claims below must be read before any number from it is quoted:
  1. It models **account equity as a single GBM/jump process**. There are no strikes, deltas, assignment or per-contract theta in it — only a flat `overlay_yield/252` credit. It therefore **cannot** evaluate the 60/200 asymmetry, whose justification is the implied-minus-realised volatility premium.
  2. `consecutive_stop_losses` is hardcoded to `0`, so the third kill-switch trigger is never exercised across any path.
  3. Its default parameters produce a **87.3% kill-switch halt rate over 30 days** (873/1000 paths, 755 single-day-loss breaches). Either the calibration or the 2% daily threshold is wrong; a live system halting 87% of the time would never trade. Unresolved.
  4. Portfolio **Net Delta ≤ 0.30 × NAV and Vega ≤ 0.15 × NAV caps do not exist.** `grep` finds no such fields in `config.py` or the strategies. They are W3 on the roadmap — planned, not enforced.


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

Marked BUILT / PARTIAL / PLANNED, because a risk document that describes intent
as though it were implementation is worse than no document.

1. **Layer 1: Pre-Trade Kill-Switch (`risk_mitigation.py`) — BUILT**
   - Checked *first* before any cycle step, and re-checked at step 5b after exit
     evaluation. Halts on NAV or overlay drawdown, single-day loss, or
     consecutive stop-losses. Returns `notes` and `drawdown_basis` so a NAV
     fallback is visible rather than silent.
2. **Layer 2: Persistent State (`agent/state/`) — PARTIAL**
   - `peak.py` persists NAV and overlay high-water marks across restarts. The
     `cycle_run` / `directive` / `exit_event` ledger is **not built**, so
     `consecutive_stop_losses` does not yet accumulate across cycles.
3. **Layer 3: Hedge Fund Council (`agent/council/`) — BUILT**
   - Six investor personas, Graham Ch.14 defensive checks, Mr. Market regime
     classification, tier policy handoff. Monte Carlo is **not** part of this
     path — see §1C.
4. **Layer 4: Execution Contract Resolver — BACKEND-OWNED, BUILT**
   - `backend/app/routes/agent.py` resolves OCC contracts; `backend/app/risk/`
     runs nine pre-trade checks and `backend/app/store/` records every attempt.
     `order_executor.py` in this layer constructs orders but never submits them.

**Not built, on the roadmap:** portfolio Greeks caps (W3), behavioural replay
(W2), IV rank (W8), signed council handoff (W6).

---

For the module-by-module reference — `strategies/`, `decision_engine.py`,
`exit_manager.py`, `portfolio_analyst.py`, `council/daily_cycle.py`,
`council/handoff.py`, the verification scripts and the test map — see
[`AI-ENGINEER-REFERENCE.md`](AI-ENGINEER-REFERENCE.md).

