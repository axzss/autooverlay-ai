# RISK-MANAGEMENT

In a trading system this is the part that matters. Everything else decides what
to buy; this decides what not to, and when to stop entirely.

All thresholds live in `agent/config.py::StrategyConfig` and are editable from
the Settings UI or via `PUT /api/strategy/config`.

---

## Layer 1 — Kill-switch

`agent/council/risk_mitigation.py`. Halts all new entries when **any** of:

| Trigger | Threshold | Config key |
|---|---|---|
| Drawdown from peak | > 5% | `kill_max_drawdown_pct` |
| Single-day loss | > 2% | `kill_max_single_day_loss_pct` |
| Consecutive stop-losses | ≥ 3 | `kill_consecutive_stop_losses` |

### It is checked first, and that is the design

In `daily_cycle.py`, the kill-switch is **step 1 of 7**. If it fires, the function
returns immediately with halt reasons and `steps_run: ["kill_switch"]` — no
snapshot fetch, no council, no screening. A halted portfolio cannot produce a new
entry through any code path, because no code path executes.

Verified live:

```json
{
  "halted": true,
  "steps_run": ["kill_switch"],
  "halt_reasons": ["single-day loss -12.96% breaches kill threshold -2.00%"]
}
```

Tested in `agent/tests/test_daily_cycle.py`.

### `overlay_only_drawdown` — a deliberate loosening

Default `True`. Drawdown is measured from **overlay positions' collateral/market
value**, not whole-portfolio NAV, falling back to full NAV when no overlay
collateral exists.

Reason: a $500k equity portfolio having a normal −6% week would trip a 5% halt
that has nothing to do with the options overlay. The overlay might be performing
perfectly.

**Stated honestly:** this makes the kill-switch *less* sensitive than a whole-NAV
reading. Set it to `False` for the stricter interpretation. Changing a safety
control's sensitivity deserves to be visible, so it is documented here rather
than buried.

### Why NaN validation belongs in this section

Security finding **S1**: `PUT /api/strategy/config` accepted NaN. A NaN threshold
does not raise an exception — it makes every `>` and `<` comparison return
`False`. So:

```python
drawdown_pct > config.kill_max_drawdown_pct   # NaN → always False
```

The kill-switch and every risk cap turn **off silently**, while the Settings UI
still displays them as active. That is the worst failure mode available in a
trading system: a safety control that reports itself healthy while doing nothing.

`StrategyConfig` now rejects NaN, ±Infinity, and out-of-magnitude values.
Validating type without validating value was the gap.

---

## Layer 2 — Portfolio caps

`agent/portfolio_analyst.py`. Evaluated before any new position.

| Cap | Limit | Config key |
|---|---|---|
| Per-ticker concentration | 25% of portfolio value | `max_concentration_pct` |
| Cash reserve floor | 10% remaining after collateral | `min_cash_reserve_pct` |
| Tech-complex sector cap | 40% of deployed overlay capital | `max_sector_concentration_pct` |

Sector group: `("AAPL", "MSFT", "NVDA", "QQQ")`.

### Why the sector cap uses deployed overlay capital

The denominator is **deployed overlay capital**, not total portfolio value. The
risk being managed is correlated *overlay* exposure: four tech names tend to move
together, so a single tech selloff can push several short calls in-the-money
simultaneously. That correlation is a property of the overlay book, not of how
much unrelated equity happens to sit alongside it.

QQQ is in the group deliberately even though it is an ETF — it is heavily
tech-weighted, so treating it as diversification would be self-deception.

### Cash reserve exists for assignment

Cash-secured puts require `strike × 100 × contracts` set aside. The 10% floor is
on top of that: if a put is assigned you buy the shares, and being fully deployed
at that moment means forced liquidation elsewhere.

---

## Layer 3 — Exit rules

`agent/exit_manager.py`. Evaluated on every open overlay position each cycle.

| Trigger | Condition | Action | Config key |
|---|---|---|---|
| Take profit | ≥ 60% of premium captured | `TAKE_PROFIT` | `take_profit_pct` |
| Stop loss | loss ≥ 200% of initial premium | `STOP_LOSS` | `stop_loss_mult` |
| Roll — delta | \|delta\| > 0.40 | `ROLL` | `roll_delta` |
| Roll — time | DTE < 7 | `ROLL` | `roll_min_dte` |

### The 60/200 asymmetry, explained properly

This is the most-questioned pair of numbers in the project. It looks like the
inverse of a sane 2:1 reward-to-risk ratio. For **premium selling** it is correct:

- You collect a small credit with high probability of keeping it. The payoff is
  inverted relative to directional trading — many small wins, occasional larger
  losses.
- Theta decay is front-loaded. Most of the premium decays early; the last 40%
  takes disproportionately long while gamma risk rises into expiry. Closing at
  60% captured frees capital and removes tail risk at the point where remaining
  reward is smallest.
- A loss is only meaningful relative to the credit. A stop at 200% of a $1.00
  credit is a $2.00 loss. Stopping tighter would cut positions that are merely
  noisy rather than genuinely wrong.

Expectancy comes from the volatility risk premium — implied volatility exceeding
realised volatility on average.

### Why roll at delta 0.40 and DTE 7

- **Delta 0.40** — the short strike is approaching the money and assignment
  probability is rising materially. Rolling out and up re-establishes distance
  while collecting new credit.
- **DTE 7** — gamma accelerates in the final week. Small underlying moves produce
  large P&L swings, which is the opposite of what an income overlay wants.

### Known gap

There is **no guard for `premium <= 0`**. An illiquid option quoting zero would
divide by zero in the capture calculation. Unlikely, unhandled, tracked in
`KNOWN-ISSUES.md`.

---

## Layer 4 — Volatility tier policy

From `agent/council/handoff.py`, derived from the council report. Applied at
screening time.

| Tier | Annualised vol | Delta band | Max DTE | Strategies | Size |
|---|---|---|---|---|---|
| low | < 20% | 0.15–0.30 | config default | all | 1.0× |
| mid | 20–35% | 0.10–0.25 | 45 | all | 0.5× |
| high | > 35% | 0.05–0.15 | 30 | covered call only | 0.5× |

Per-symbol override: **TSLA** is restricted to delta ≤ 0.10 at half size until its
annualised volatility drops below 45%. TSLA measured 59% annualised — the highest
in the universe — and the council flagged it as the riskiest name.

Rationale: high implied volatility means richer premium, which is exactly what
tempts you into oversized positions in the names most likely to move against you.
The tier policy inverts that instinct — higher volatility buys you a *smaller*
position further out of the money, and no cash-secured puts (where assignment
means buying a falling knife).

Precedence: `explicit argument > tier policy > config default`.

### Enforcement is auditable

Blocked candidates are not silently dropped. They come back with a reason:

```json
{
  "symbol": "NVDA",
  "action": "BLOCKED",
  "reasoning_trace": [
    "tech complex at 42.1% of deployed overlay capital > 40% cap",
    "blocked per council §6 sector concentration guidance"
  ]
}
```

---

## Layer 5 — Market regime

`agent/council/mr_market.py`, from Ch.8 of *The Intelligent Investor*.

Classifies mood as `euphoric` / `indifferent` / `panicky` from SPY run-up and
realised volatility. When `euphoric`, `daily_cycle` **blocks new entries** —
Graham's rule that one should refrain after substantial advances.

Tested in `test_daily_cycle.py::test_euphoric_market_blocks_new_entries`.

**Limitation:** two inputs only, and no hysteresis — the mood is recomputed per
call, so it can flip between two consecutive requests on noise. Fix on roadmap.

---

## Layer 6 — Human approval

**The backend has no auto-submit path.** This is architectural, not a setting.

- `POST /api/agent/run` returns `orders_ready: false` — always
- Every order intent carries `requires_approval: true` and `submitted: false`
- `POST /api/trade` is the only route that submits, and it must be called
  explicitly with a fully specified order
- The Terminal UI labels the intent table "Preview only — nothing is sent to the
  broker"

An autonomous agent that can move money without a human in the loop is a
liability, not a feature. The agent's job is to do the analysis and prepare the
order; the decision to send it stays with a person.

---

## Defence in depth — how the layers interact

A hypothetical NVDA covered call must pass:

1. Kill-switch not halted
2. Mr. Market not euphoric
3. Council consensus not `AVOID`
4. NVDA position < 25% of portfolio
5. Tech complex < 40% of deployed overlay capital
6. Delta within the tier band for NVDA's volatility
7. DTE within tier limit
8. Cash reserve still ≥ 10% after collateral
9. Position size scaled by tier multiplier
10. **A human clicks approve**

Any one failure blocks the trade, and the trace records which one.

---

## Security posture

7 penetration-test findings, all fixed, 32 regression tests. Full detail in
[`security_review.md`](security_review.md).

The ones that mattered:

| ID | Why it was dangerous |
|---|---|
| S1 | NaN config silently disabled every threshold including the kill-switch |
| S3 | NaN/Infinity in trade payloads crashed the route with HTTP 500 |
| S5 | A crafted council report could inject `delta 0.99`, overriding tier policy |

S5's mitigation is a clamp (delta ≤ 0.95, DTE ≤ 365). Clamping an injection is
not the same as authenticating the channel. The red team's recommendation —
cryptographically sign the council report before trusting its HANDOFF section —
remains **open**.

---

## What is not protected

Stated plainly, because a risk document that only lists mitigations is marketing:

1. **No backend authentication.** Any local caller can hit `POST /api/trade`.
   Fine on localhost; **not fine** when exposed, and it has been exposed via
   Cloudflare tunnel during development.
2. **No backtest.** Nothing establishes that these parameters are profitable.
   The 60/200 rule is sound in theory and untested here in practice.
3. **No slippage or liquidity modelling.** Screening rejects thin chains but does
   not model execution cost.
4. **No overnight gap protection.** Options positions carry gap risk that no
   intraday rule can prevent.
5. **Kill-switch state is not persisted.** It is recomputed from portfolio state
   each cycle; a restart loses the consecutive-stop-loss counter.
6. **Assignment is not simulated.** The system reasons about assignment risk but
   has never been through an actual assignment.
