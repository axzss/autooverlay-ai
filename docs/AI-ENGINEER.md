# AI-ENGINEER — The Agent Layer

Everything under `agent/`. This is the part that decides what to trade, when to
exit, and what to refuse.

Design principle throughout: **every output must be explainable**. No
recommendation leaves this layer without a `reasoning_trace` listing the checks
it passed, and no directive leaves `daily_cycle` without `provenance` naming the
rule that produced it.

---

## Module map

```
agent/
├── config.py                  StrategyConfig — every tunable parameter
├── strategies/
│   ├── covered_call.py        Screen covered-call candidates
│   └── cash_secured_put.py    Screen CSP candidates
├── decision_engine.py         Rank candidates, assign risk score, emit trace
├── exit_manager.py            Take-profit / stop-loss / roll on open positions
├── portfolio_analyst.py       Concentration, cash reserve, sector caps
├── orchestrator.py            Legacy single-pass runner
├── order_executor.py          Order construction (not auto-submitting)
└── council/
    ├── personas.py            6 investor personas
    ├── engine.py              Consensus + dissent
    ├── graham_principles.py   Ch.14 tests, Ch.20 margin of safety
    ├── mr_market.py           Ch.8 market-mood regime
    ├── fundamentals.py        Free fundamentals provider + cache
    ├── handoff.py             Report HANDOFF → TierPolicy
    ├── risk_mitigation.py     Kill-switch
    ├── report.py              Council report rendering
    ├── daily_cycle.py         The orchestrator that ties it all together
    └── run_full_assessment.py Batch run over the 8-symbol universe
```

---

## `config.py` — StrategyConfig

Single source of truth for every tunable. Overridable at runtime via the
`STRATEGY_CONFIG_JSON` env var, and editable through `PUT /api/strategy/config`
from the Settings UI.

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

# Portfolio guards
max_concentration_pct:  float = 25.0   # max % of portfolio per ticker
min_cash_reserve_pct:   float = 10.0   # min % cash after collateral

# Sector guard
max_sector_concentration_pct: float = 40.0
sector_cap_group: tuple = ("AAPL", "MSFT", "NVDA", "QQQ")

# Kill-switch
kill_max_drawdown_pct:        float = 5.0
kill_max_single_day_loss_pct: float = 2.0
kill_consecutive_stop_losses: int   = 3
overlay_only_drawdown:        bool  = True
```

### Why 60% take-profit but 200% stop-loss

This asymmetry looks backwards and is the most-questioned parameter in the
project. It is correct for **premium selling**, which has an inverted payoff
compared to directional trading:

- You collect a small credit up front with a high probability of keeping it.
- Theta decay means most of the profit arrives early — the last 40% of premium
  takes disproportionately long and carries gamma risk into expiry. Closing at
  60% frees capital and removes tail risk.
- A loss is only meaningful relative to the credit received. A stop at 200% of a
  $1.00 credit is a $2.00 loss — real, but it takes a sharp adverse move to get
  there, and stopping earlier would cut winners that are merely noisy.

Net effect: many small wins, occasional larger losses, positive expectancy from
the volatility risk premium. Both numbers are configurable from the UI.

### Validation is about values, not just types

`StrategyConfig` rejects NaN, ±Infinity, and out-of-magnitude values. This is
not defensive padding — it is security finding **S1**. A NaN threshold does not
raise; it makes every `>` and `<` comparison return `False`, which silently
disables the kill-switch and every risk cap while the UI still displays them as
active. Type validation alone would have let it through.

---

## `strategies/` — candidate screening

Both strategies share a shape: take a list of option-chain opportunities plus
current positions, filter by delta band and DTE window, compute annualised
premium yield, score risk 0–100, and return ranked candidates each carrying a
rationale.

### `covered_call.py`
Sells calls against shares already held. Requires ≥ 100 shares per contract —
this is not optional, it is what makes the position *covered* rather than naked.
Contract count is `floor(shares / 100)`.

`screen(opportunities, positions, tier_policy=None)`.

### `cash_secured_put.py`
Sells puts with cash set aside to buy the shares if assigned. Collateral is
`strike × 100 × contracts`, checked against available cash and the cash-reserve
floor.

### Tier policy override
Both accept an optional `tier_policy`. Precedence is:

```
explicit argument  >  tier policy  >  config default
```

`_normalize_policy()` accepts either a `TierPolicy` dataclass or a plain dict, so
the strategies work whether policy comes from `handoff.py` or from a test
fixture.

---

## `decision_engine.py`

`DecisionEngine(account_cash, config=...)` with `evaluate(...)`. Takes screened
candidates plus portfolio context and produces recommendations with:

- `action` — `INITIATE` / `HOLD` / `MONITOR`
- `risk_score` — 0–100, higher is riskier
- `reasoning_trace` — `list[str]`, one entry per check performed
- `portfolio_context` — concentration and cash-reserve status

`_assess_portfolio_health()` folds in the analyst's view, so a candidate that is
attractive in isolation can still be downgraded because the portfolio is already
concentrated.

`_normalize_trace(trace)` coerces any trace to `list[str]`. Some code paths
returned a bare string, which meant consumers had to handle
`Union[str, list[str]]` or crash on iteration.

---

## `exit_manager.py`

`ExitManager(config=...)`, then `evaluate_position(position, ...)` or
`evaluate_positions(positions, ...)`.

| Trigger | Condition | Action |
|---|---|---|
| Take profit | ≥ 60% of premium captured | `TAKE_PROFIT` |
| Stop loss | loss ≥ 200% of initial premium | `STOP_LOSS` |
| Roll — delta | \|delta\| > 0.40 | `ROLL` |
| Roll — time | DTE < 7 | `ROLL` |
| Otherwise | — | `HOLD` |

`_dte_of(position)` parses the OCC option symbol to recover expiry, so DTE works
even when the broker payload omits it.

**Known gap:** none for `premium <= 0` — `initial <= 0` is guarded at
`exit_manager.py:102`; the P&L rules are skipped with a trace line and roll rules
still apply. `KNOWN-ISSUES.md` #9 claimed an unguarded `ZeroDivisionError`; that
claim was verified false on 29 Aug and the item is closed.


---

## `portfolio_analyst.py`

- `check_concentration()` — no single ticker above 25% of portfolio value
- `check_cash_reserve()` — at least 10% cash remaining after collateral
- `check_sector_cap()` — the tech complex (AAPL, MSFT, NVDA, QQQ) capped at 40%
  of deployed overlay capital
- `deployed_overlay_capital()` — denominator for the sector cap

The sector cap is deliberately measured against **deployed overlay capital**, not
whole-portfolio value. The council's concern is correlated overlay exposure: four
tech names moving together would breach several short calls at once regardless of
how much unrelated equity is also held.

---

## `council/daily_cycle.py` — the orchestrator

`run_daily_cycle(portfolio_positions, cash, open_option_positions=None, ...)`
executes in a fixed order. **The order is the safety property.**

```
1. Kill-switch check          ← FIRST. If halted, return immediately.
2. Snapshots + fundamentals   ← wall-clock budget, fallback to bundled snapshots
3. Mr. Market mood            ← from SPY price series and volatility
4. Council assessments        ← per held underlying and per candidate
5. Exit evaluation            ← on open overlay positions
5b. Kill-switch RE-CHECK      ← consecutive stop-losses observed this cycle
6. New-entry screening        ← tier policy + concentration + sector caps
7. DailyDirective queue       ← prioritised, each with trace + provenance
```

Step 1 is first so that a halted portfolio cannot have any later step produce a
new entry. If the kill-switch fires, the function returns with halt reasons and
**every subsequent step is skipped** — verified by
`agent/tests/test_daily_cycle.py`.

Step 5b exists because the stop-loss count is a *product* of step 5. Checking it
only at step 1 meant a cycle that generated three stop-losses would still screen
new entries with that cycle's own evidence of trouble in hand. The re-check
short-circuits before screening and returns a `kill-switch:post-exit` directive.


### DailyDirective

```json
{
  "action": "INITIATE",
  "symbol": "MSFT",
  "priority": 2,
  "params": { "strategy_allowed": ["CSP"], "delta_min": 0.10, "delta_max": 0.25 },
  "reasoning_trace": ["tier mid: delta band 0.10-0.25", "sector cap 40% not breached"],
  "provenance": [
    { "source": "tier:mid", "detail": "30.5% annualised vol" },
    { "source": "council §6", "detail": "consensus HOLD, size x0.5" }
  ]
}
```

Actions: `EXIT`, `ROLL`, `INITIATE`, `HOLD`, `MONITOR`.

### Resilience
`fetch_timeout_seconds` (default 5.0) and `fetch_retries` (default 2) set an
**overall wall-clock budget** for the snapshot step:
`per_symbol × attempts × len(missing)`. One `ThreadPoolExecutor` handles the
whole batch, `as_completed(timeout=remaining)` enforces the deadline, stragglers
are cancelled, and `shutdown(wait=False)` prevents an in-flight socket read from
re-imposing the stall. On persistent failure it falls back to
`docs/market_snapshots.json` so the cycle completes with stale-but-real data.

**Until 29 Aug this bound did not exist.** The old code wrapped each fetch in
`with ThreadPoolExecutor(...) as pool`, and `__exit__` calls
`shutdown(wait=True)` — which joins the worker *before* the `except` clause
runs. The `TimeoutError` was raised on schedule and then blocked on the very
fetch it was meant to abandon. Measured: **60.4s against a 1.0s budget.** Worst
case over the 8-symbol universe was ~16 minutes, inside the
`POST /api/agent/run` request path. Regression test:
`test_daily_cycle.py::test_snapshot_step_honours_its_wall_clock_budget`.


---

## `council/handoff.py` — the fragile seam

Parses the HANDOFF section of `docs/council_report.md` into a `TierPolicy`.

| Tier | Annualised vol | Delta band | Max DTE | Strategies | Size |
|---|---|---|---|---|---|
| low | < 20% | 0.15–0.30 | config | all | 1.0× |
| mid | 20–35% | 0.10–0.25 | 45 | all | 0.5× |
| high | > 35% | 0.05–0.15 | 30 | covered call only | 0.5× |

Plus per-symbol overrides — TSLA is restricted to delta ≤ 0.10 at half size until
its annualised volatility falls below 45%.

`get_tier_for_symbol(symbol, vol_pct)` maps volatility to tier.
`effective_policy_for_symbol()` returns the policy plus human-readable notes that
end up in the reasoning trace.

**This is the weakest link in the system.** It parses markdown with regular
expressions. If the report format changes, the policy silently falls back to
defaults and the council's intent is lost with no error raised. It was also
security finding **S5**: a crafted report could inject `delta 0.99`. That is now
clamped (delta ≤ 0.95, DTE ≤ 365) — but clamping an injection is mitigation, not
trust. The correct fix is a structured side-channel: emit machine-readable JSON
alongside the human-readable report. Still open.

---

## `council/risk_mitigation.py` — kill-switch

Halts all new entries when any of:

- Portfolio drawdown from peak > 5%
- Single-day loss > 2%
- 3 consecutive stop-loss exits

All three thresholds are in `StrategyConfig`.

`overlay_only_drawdown` (default `True`) measures drawdown from overlay
positions' collateral/market value rather than whole-portfolio NAV, falling back
to full NAV when no overlay collateral is present. Without this, a large equity
portfolio moving normally could trip a halt that has nothing to do with the
overlay. Note the trade-off: this makes the kill-switch **less** sensitive than
the whole-NAV reading, by design.

---

## Verification scripts

Not tests — manual proof scripts, runnable directly:

| Script | Proves |
|---|---|
| `agent/verify_council_consumption.py` | Decision engine actually consumes council tier policy |
| `agent/verify_end_to_end.py` | Full pipeline runs end to end |
| `agent/verify_intelligence.py` | Reasoning traces are populated and coherent |
| `agent/council/sample_run.py` | Council on a single synthetic symbol |
| `agent/council/run_full_assessment.py` | Council on all 8 symbols, appends report addendum |

---

## Tests

```bash
pytest agent/tests -q
```

| File | Covers |
|---|---|
| `test_config.py` | Config validation, NaN/Infinity rejection, bounds |
| `test_strategies.py` | Covered call and CSP screening, tier policy precedence |
| `test_exit_and_portfolio.py` | Exit triggers, concentration, cash reserve |
| `test_council.py` | Consensus, dissent detection per persona |
| `test_graham_persona.py` | The seven Ch.14 tests against book thresholds |
| `test_council_handoff.py` | HANDOFF parsing, tier mapping, sector cap |
| `test_risk_mitigation.py` | Kill-switch thresholds |
| `test_daily_cycle.py` | Step ordering, kill-switch short-circuit, provenance |
| `test_fundamentals.py` | Cache hit/expiry, graceful degradation (offline) |
| `test_security_regression.py` | All 7 red-team findings |

No test touches the network. Fundamentals tests use monkeypatched fetchers.

---

## Open work in this layer

1. **Fundamentals cache is ephemeral and world-writable** — lives at a fixed
   `/tmp` path, so a restart silently drops the council from HIGH to LOW
   confidence, and any process on the box can pre-create or overwrite it. The
   loader validates nothing beyond JSON parse + TTL, and fundamentals feed
   persona scoring, which drives the HANDOFF tier policy — the same trust
   boundary as security finding S5, one step earlier. `KNOWN-ISSUES.md` #1.
2. **Mr. Market has no hysteresis** — regime is classified per call, so it can
   flip on noise between two requests.
3. **INCONCLUSIVE Graham tests count as neutral** — biases the council bullish on
   names with thin data. Should be a half-fail.
4. **Consecutive stop-losses are within-cycle only** — the count resets every
   cycle. Three stops across three cycles never halt. Needs the W1 `exit_event`
   ledger. `KNOWN-ISSUES.md` #11.
5. **Handoff is unauthenticated** — see above.

