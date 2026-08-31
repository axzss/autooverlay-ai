# Risk Management Evaluation & Architecture

AutoOverlay AI manages options overlay trading (cash-secured puts and covered
calls) behind a layered risk structure.

**Every claim below is marked BUILT, PARTIAL or PLANNED.** An earlier revision of
this file described planned infrastructure in the present tense: it cited a
SQLite WAL ledger at `docs/.cache/agent_state.db`, Monte Carlo VaR "integrated
into strategy screening", and Net Delta / Vega caps. None of the three existed
when it was written. A risk document that overstates its controls is worse than
no document, because it is the thing a reviewer trusts instead of reading the
code.

Verification commands are given so any claim here can be checked in seconds.

---

## 1. Risk Evaluation & Criticism

### A. State persistence — PARTIAL

**Issue.** Consecutive stop-loss counters and high-water marks lived in
ephemeral storage. On restart the counter reset to `0` and `peak_equity`
collapsed to current equity, blinding multi-day drawdown evaluation.

**Built.** `agent/state/peak.py` persists NAV and overlay high-water marks
across cycles and restarts — `docs/.cache/peak_equity.json`, atomic write,
`/tmp` fallback, gitignored. The design rule matters more than the file: **a
caller may raise the mark, never lower it, and never supply it outright.** Reads
report `tracked` and `source`, so an absent mark is `"absent"` rather than a
silent 0% drawdown. 21 tests in `agent/tests/test_peak_store.py`.

This closes a bug that reached production three times by three different routes:

| Route | Symptom |
|---|---|
| finding A | overlay equity compared against itself → drawdown always `0.00%` |
| finding B | backend passed **current** equity as `peak_equity` → same |
| `8fc3928` | an `equity` override made both sides `account["equity"]` → same |

**Still open.** The `cycle_run` / `directive` / `exit_event` ledger is **not
built**. Without `exit_event`, `consecutive_stop_losses` is computed within a
single cycle only — three stops spread across three cycles do not halt. The
fundamentals cache is still at a world-writable `/tmp` path. See
`KNOWN-ISSUES.md` #11 and #1.

```bash
ls agent/state/                 # peak.py — present
ls docs/.cache/agent_state.db   # absent: the ledger is not built
```

### B. Execution contract resolution — BUILT, backend-owned

**Issue.** Directives emitted policy parameters (`delta_min/max`,
`strategy_allowed`) without concrete OCC symbols, so order handlers fell back to
market orders. Market orders on options cross the full spread — 3–10% of premium
lost on entry.

**Built.** `_pick_option_contract` in `backend/app/routes/agent.py` resolves the
contract from the live option chain using the tier's delta band and DTE window.
`backend/app/risk/gate.py` runs nine pre-trade checks before the broker is
contacted, and `backend/app/store/` records every attempt with the intent row
written *before* the broker call.

This is `backend/**`, owned by AjiNurAji, not an agent-layer deliverable.
Residual gap: the resolver returns `None` when `is_configured()` is false, so
order preview is invisible in mock mode — `KNOWN-ISSUES.md` #2.

### C. Quant realities and asymmetric risk — PLANNED

**Issue.** The fixed 60% take-profit / 200% stop-loss means one loss erases 3.3
wins. Below roughly a 77% win rate, expectancy turns negative.

**Not mitigated.** `agent/monte_carlo.py` exists and runs, but:

1. **Nothing imports it.** `git grep monte_carlo -- agent backend` returns only
   the module and its own test. It is a standalone tool, not part of screening.
2. **It contains no options.** Account equity is modelled as one GBM/jump
   process; there are no strikes, deltas, assignment or per-contract theta, only
   a flat `overlay_yield / 252` credit. It therefore **cannot** evaluate the
   60/200 asymmetry, whose entire justification is the implied-minus-realised
   volatility premium — and there is no implied volatility in the model.
3. **Its own output contradicts the configuration.** Default parameters halt
   **87.3%** of 1000 paths within 30 days, with 755 single-day-loss breaches.
   A live system halting 87% of the time would never place a trade. Either the
   calibration or the 2% daily threshold is wrong. Unresolved.
4. **`consecutive_stop_losses` is hardcoded to `0`** at `monte_carlo.py:110`, so
   the third kill-switch trigger is never exercised on any path.
5. **Net Delta ≤ 0.30 × NAV and Vega ≤ 0.15 × NAV do not exist.** No such fields
   in `config.py` or the strategies. They are W3 on the roadmap.

```bash
git grep -l monte_carlo -- agent backend   # module + its test only
grep -c "net_vega\|net_delta" agent/config.py   # 0
python3 agent/monte_carlo.py               # kill_switch_halt_pct: 87.3
```

Genuine mitigation for the asymmetry requires a replay harness over real option
chains (W2) and a real IV percentile series (W8). Neither is built, so **the
60/200 parameters remain unvalidated** — sound in theory, untested here.

---

## 2. Layered risk architecture

| Layer | Component | Status |
|---|---|---|
| 1 | Pre-trade kill-switch — `agent/council/risk_mitigation.py` | **BUILT** |
| 2 | Persistent state — `agent/state/peak.py` | **PARTIAL** — marks yes, ledger no |
| 3 | Hedge-fund council — `agent/council/` | **BUILT** |
| 4 | Execution gate — `backend/app/risk/`, `backend/app/store/` | **BUILT** (backend) |


**Layer 1.** Evaluated first in `run_daily_cycle`, before any other step, and
re-checked at step 5b after exit evaluation — the stop-loss count is a *product*
of exit evaluation, so checking only at step 1 let a cycle screen new entries
while holding its own evidence of trouble. Returns `notes` and `drawdown_basis`
(`"nav"` or `"overlay"`) so a fallback is visible.

**Layer 2.** High-water marks persist, in **both** paths — `run_daily_cycle` and
the execution gate read the same store, so a halt cannot depend on which entry
point observed the account. Before this, the gate used `max(equity,
last_equity)`: a two-day window that gave the same book opposite verdicts
depending on which calendar day its peak fell on. The `cycle_run` / `directive` /
`exit_event` event ledger still does not exist.


**Layer 3.** Six personas, Graham's seven Ch.14 defensive tests, Mr. Market
regime classification, tier-policy handoff. Monte Carlo is **not** in this path.

**Layer 4.** Nine checks; `kill_switch` and `state_available` cannot be
overridden. Fails closed when portfolio state is unreadable. The gate calls the
agent layer's `evaluate_kill_switch` rather than reimplementing it.

**Layer 5, not in the table but real:** no auto-submit path exists.
`POST /api/agent/run` always returns `orders_ready: false`, and every intent
carries `requires_approval: true`. A human sends the order.

---

## 3. What is still not protected

Stated plainly, because a risk document listing only mitigations is marketing.

1. **No cross-cycle stop-loss accumulation** — needs the `exit_event` ledger.
2. **No validated parameters** — no backtest establishes that 60/200 is
   profitable, or that six personas beat one.
3. **No portfolio-level Greeks** — a book can pass every per-position check and
   still be catastrophically short vega into an earnings week.
4. **No IV rank** — "don't sell cheap premium" is currently unenforceable.
5. **Fundamentals cache is world-writable** — a trust boundary, not just a
   durability issue. Same class as security finding S5, one step earlier.
6. **Assignment is never simulated** — the system reasons about assignment risk
   but has never been through one.
7. **Mr. Market has no hysteresis** — the euphoric block can flicker on noise.

---

## 4. How to check this document against the code

```bash
pytest agent/tests backend/tests -q          # 586 passed, 1 skipped
python3 backend/tests/repro_live_defects.py  # 7/7
ls agent/state/ docs/.cache/                 # what persistence exists
git grep -l monte_carlo -- agent backend     # what actually imports it
```


If a claim here cannot be reproduced by one of those commands, the claim is
wrong and should be corrected rather than defended.
