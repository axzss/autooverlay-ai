# BRIEF-AGENT-V2 — Scale-Up Mandate for AI Engineering + Hedge-Fund Council

**Issued by:** Orchestrator / CTO
**Owners:** AI engineering (`agent/**`) + hedge-fund council (`agent/council/**`), docs (`docs/**`)
**Out of scope for this brief:** `frontend/**`, `backend/**` — do not edit. New surface is exposed by *adding* callable functions and JSON artefacts that backend can wrap later.
**Window:** D-6 (29 Aug) → D0 (4 Sep, 15:00 UTC submission)

> **SUPERSEDED IN PART — read [`BRIEF-AGENT-V2-REVIEW.md`](BRIEF-AGENT-V2-REVIEW.md) first.**
> A code audit found the kill-switch is largely inoperative in live operation:
> the drawdown check is dead twice over, and nothing produces the
> consecutive-stop-loss signal. The review inserts a blocking **W0** ahead of
> everything here, demotes W4 to optional, promotes W8 to mandatory, retitles
> W2's deliverable, and moves the freeze to D-1 18:00 UTC. Where the two
> documents disagree, the review wins.


---

## 0 · Why this brief exists

The agent layer today is *correct but small*. It screens two strategies, runs six
personas once, decides, and forgets everything on restart. A judge probing depth
will reach the floor in three questions:

1. "Does it prove the 60/200 asymmetry works?" — no backtest exists.
2. "What happens on restart?" — kill-switch counter and fundamentals cache vanish.
3. "How does the committee handle being wrong?" — it doesn't; personas vote once
   and never argue back.

This brief closes those three and adds five layers of depth on top. It is
deliberately larger than 6 days of comfortable work: **W1–W6 are mandatory, W7–W12
are ranked spend-if-you-have-it.** Ship mandatory-complete rather than
everything-half-done.

Standing constraint, unchanged: **no output leaves this layer without a
`reasoning_trace`, and no directive without `provenance`.**

---

## 1 · Target end-state

| Dimension | Today | Target D0 |
|---|---|---|
| Strategies | 2 (CC, CSP) | 5 (CC, CSP, put credit spread, collar, wheel state machine) |
| Personas | 6, single pass | 7 (+ red-team), 2-round debate |
| State | in-process, lost on restart | SQLite ledger, survives restart |
| Evidence of edge | none | replay backtest over ≥ 250 sessions |
| Greeks | per-position delta | portfolio net Δ/Θ/Ⅴ/Γ with caps |
| Handoff | markdown + regex | signed JSON, regex as fallback only |
| Cadence | runs when called | market-calendar-aware scheduler |
| Tests | 161 | ≥ 260, all offline |

---

## MANDATORY WORKSTREAMS

### W1 · Persistent state ledger — `agent/state/`
**Owner:** AI engineering · **Closes:** KNOWN-ISSUES #1, #11 · **Blocks:** W2, W5

SQLite at `docs/.cache/agent_state.db` (gitignored), WAL mode, schema-versioned.

```
agent/state/
├── store.py        open_store(path) -> StateStore ; migrate() ; schema_version
├── ledger.py       append-only decision ledger
└── cache.py        fundamentals cache, TTL-aware, replaces /tmp path
```

Tables:

| Table | Purpose |
|---|---|
| `cycle_run` | one row per `run_daily_cycle`: ts, halt flag, mood, symbols seen, config hash |
| `directive` | every DailyDirective ever emitted, FK to cycle_run, full trace + provenance as JSON |
| `exit_event` | realised exits with trigger type — **this is what feeds the consecutive-stop-loss counter** |
| `fundamentals` | symbol, payload JSON, fetched_at, ttl_seconds |
| `peak_equity` | running high-water mark for drawdown, per account |

Hard requirements:
- Every write atomic; a crash mid-cycle must not leave a partial cycle readable.
- `StateStore` must be constructible in-memory (`:memory:`) so tests never touch disk.
- Merged snapshots gain `data_age_hours: float` and `stale: bool`. Any persona
  consuming a stale field must say so in its bullet — silent staleness is the
  failure mode that got this ranked HIGH.
- `/tmp` fallback if `docs/.cache/` is read-only, with a warning in the trace.

Acceptance: kill the process mid-cycle, restart, and the stop-loss counter, peak
equity and fundamentals are all still there. Test: `test_state_store.py`,
`test_killswitch_persistence.py`.

---

### W2 · Replay backtest harness — `agent/backtest/`
**Owner:** AI engineering + council jointly · **Closes:** ROADMAP #16 · **Depends:** W1

This is the single highest-value item in the brief. It converts every parameter
in `StrategyConfig` from an assertion into a measurement.

```
agent/backtest/
├── replay.py       ReplayEngine — feeds historical bars/chains through the real cycle
├── synth_chain.py  synthesise option chains from underlying + vol when history is absent
├── metrics.py      PnL, win rate, avg premium capture, max DD, Sharpe, assignment count
└── sweep.py        parameter sweep over take_profit_pct × stop_loss_mult × delta band
```

Non-negotiable design rule: **`ReplayEngine` must call the production
`run_daily_cycle`, not a reimplementation.** A backtest that runs different code
than the live path proves nothing. Inject a clock and a data source; change
nothing else.

`synth_chain.py` exists because free option history is unavailable: price
contracts with Black-Scholes from realised vol, add a spread proportional to
moneyness. **Label this clearly as synthetic in every output** — an overstated
backtest is worse than no backtest, and a judge will ask where the chain data
came from.

Deliverable: `docs/BACKTEST.md` containing a sweep table and one honest
paragraph on what the synthetic chain does and does not establish. If the sweep
shows 60/200 is *not* optimal, publish that and change the default. Finding the
default wrong is a win, not a failure.

Acceptance: sweep of ≥ 27 parameter combinations over ≥ 250 sessions on ≥ 8
symbols, results reproducible from a seed.

---

### W3 · Portfolio Greeks engine — `agent/greeks.py`
**Owner:** AI engineering · **New capability**

Current risk view is per-position. A portfolio can pass every individual check
and still be catastrophically short vega into an earnings week.

```python
@dataclass
class PortfolioGreeks:
    net_delta: float          # share-equivalent, equities + options
    net_theta: float          # $/day
    net_vega: float           # $ per 1 vol point
    net_gamma: float
    beta_weighted_delta: float # normalised to SPY
    per_symbol: dict[str, dict[str, float]]
    breaches: list[str]
```

New config caps: `max_net_vega_pct_nav`, `max_beta_weighted_delta_pct_nav`,
`min_net_theta` (an overlay collecting no theta is not doing its job).

Wire into `daily_cycle` as **step 6.5** — after entry screening, before the
directive queue. A candidate that individually passes but pushes portfolio vega
past the cap is downgraded `INITIATE → MONITOR` with a trace line naming the
breached Greek and the resulting exposure.

Missing greeks must yield `None`, never `0.0`. Zero is a claim of flatness;
`None` is an admission of ignorance, and the difference matters when a cap is
evaluated.

Acceptance: `test_greeks.py` — aggregation across mixed long equity + short
calls + short puts, cap breach downgrades a candidate, `None` propagation.

---

### W4 · Strategy expansion — `agent/strategies/`
**Owner:** AI engineering · **New capability**

Three additions, each following the existing `screen(opportunities, positions,
tier_policy=None)` contract so nothing downstream changes shape.

**`put_credit_spread.py`** — defined-risk CSP alternative. Short put + long
lower-strike put. Config: `spread_width_min/max`, `min_credit_to_width_ratio`
(reject anything below 0.20 — you are risking the width to collect the credit).
Collateral is `width × 100 × contracts`, not the full strike, so it unlocks the
overlay on accounts too small for cash-secured puts. Say that in the rationale.

**`collar.py`** — short call + long protective put against held shares. This is
the *only* strategy in the system that caps downside, so it must be selectable
when Mr. Market is `euphoric` and `daily_cycle` is otherwise blocking entries.
Score on net cost: prefer zero-cost or credit collars, and reject any collar
whose put cost exceeds the call credit by more than
`max_collar_net_debit_pct`.

**`wheel.py`** — not a screener, a **state machine**. CSP → (assigned) → hold
shares → CC → (called away) → CSP. Persist state per symbol in the W1 ledger.

```
CASH → SHORT_PUT → ASSIGNED_LONG → SHORT_CALL → CALLED_AWAY → CASH
                ↘ EXPIRED_WORTHLESS ↗
```

Illegal transitions must raise, not warn. The wheel is where a silent state bug
turns into a naked position, and "covered" is the property the entire risk model
depends on.

Acceptance: `test_put_credit_spread.py`, `test_collar.py`,
`test_wheel_state_machine.py` (every legal transition + every illegal one
raising). Tier policy precedence identical to the existing two strategies.

---

### W5 · Council v2 — debate, red team, calibration
**Owner:** Hedge-fund council · **Closes:** KNOWN-ISSUES #6 · **Depends:** W1

Four changes, in this order.

**5a · INCONCLUSIVE as half-fail.** `FAIL(0) < INCONCLUSIVE(0.5) < PASS(1)`. Each
affected bullet must state the penalty came from *unverifiable data*, not a
failed criterion. Known effect: SPY/QQQ −1.2, NVDA 68.0 → 67.6, JPM 52.0 → 51.6.
This was written once and lost in a reverted batch — redo it.

**5b · Two-round debate — `council/debate.py`.** Round 1 is today's independent
verdicts. Round 2 shows each persona the *dissent* against consensus and lets it
revise once, emitting `revised: bool` and `revision_reason: str`.

Guard against the obvious failure: **a persona that revises toward consensus
every round is worthless.** Track `revision_rate` per persona in the ledger; if
one exceeds 0.7 across a full run it is broken, not agreeable, and that must
surface in the report. Cathie Wood exists to disagree — if debate silences her,
the committee has become one voice with six names.

**5c · Red-team persona — `council/red_team.py`.** A seventh member that does not
score the stock; it attacks the *directive*. For each `INITIATE` it asks: what
market move makes this the worst trade in the book, what does assignment cost
here, what correlated position amplifies it, what data underpinning it is stale
(now answerable via W1's `stale` flag). Output:

```python
@dataclass
class RedTeamChallenge:
    directive_id: str
    severity: str          # BLOCK / DOWNGRADE / NOTE
    attack: str
    evidence: list[str]
```

`BLOCK` removes the directive. `DOWNGRADE` halves size. Both must appear in the
directive's provenance so the audit trail shows the trade was challenged before
it shipped. **A directive nobody argued against is not a vetted directive** —
this is the layer that makes "AI committee" mean something in a demo.

**5d · Calibration record.** Every assessment writes score + recommendation to
the ledger with the forward realised outcome stamped on later cycles. Six days
will not produce a statistically meaningful sample, and you must say so in
`docs/COUNCIL-V2.md`. Build the mechanism anyway: it is the honest answer to
"how do you know the personas are any good?" — *we measure, here is the
instrument, here is why the sample is still thin.*

Acceptance: `test_debate.py`, `test_red_team.py`, `test_calibration.py`,
`test_graham_half_fail.py`. `test_council.py::test_contrarian_bearish_dissent_detected_on_value_trap`
must still pass — if debate kills that test, debate is wrong, not the test.

---

### W6 · Signed structured handoff
**Owner:** Council · **Closes:** KNOWN-ISSUES #4

`run_full_assessment.py` emits `docs/council_handoff.json` alongside the markdown
report: tier table, per-symbol overrides, sector caps, red-team blocks, plus
`generated_at`, `config_hash`, and an HMAC over the canonical JSON body keyed by
`COUNCIL_HANDOFF_KEY` (env; absent ⇒ unsigned + loud warning in the trace).

`handoff.py` load order: **JSON + valid signature → JSON unsigned (warn) →
markdown regex (warn) → defaults (warn)**. Every fallback must be visible in the
reasoning trace. The existing clamps (delta ≤ 0.95, DTE ≤ 365) stay — signing
authenticates the source, it does not make the values sane.

Acceptance: `test_handoff_json.py` — signature valid/invalid/absent, malformed
JSON falls through to markdown, tampered delta rejected. Keep every existing
`test_council_handoff.py` test green; the markdown path is now a fallback, not
deleted.

---

## RANKED OPTIONAL

**W7 · Mr. Market hysteresis** (KNOWN-ISSUES #5) — `previous_mood` param, require
margin to leave an established regime, read prior mood from the W1 ledger. Small
and visible; do it first if time appears.

**W8 · IV rank engine** — `agent/vol_surface.py`. Real IV percentile over a
trailing year instead of realised-vol proxy. The entry filter "don't sell cheap
premium" is currently unenforceable without this.

**W9 · Market-calendar scheduler** — `agent/scheduler.py`, APScheduler + Alpaca
calendar. Skip holidays and half-days; never fire in the first or last 15 minutes
of a session.

**W10 · Assignment handler** — `agent/assignment.py`. Detect assignment from
position deltas, reconcile to wheel state, emit a directive. Currently reasoned
about, never exercised.

**W11 · Correlation matrix** — replace the hardcoded four-ticker
`sector_cap_group` with a rolling correlation matrix. Generalises the cap beyond
the current universe.

**W12 · `premium <= 0` guard** (KNOWN-ISSUES #9) — two lines, `return MONITOR`.
Do it while waiting on a test run.

---

## Sequencing

| Day | AI engineering | Hedge-fund council |
|---|---|---|
| **D-6** Sat 29 | W1 store + schema + migrate | W5a half-fail, rerun 8-symbol assessment |
| **D-5** Sun 30 | W1 ledger + cache migration off `/tmp` | W5b debate rounds + revision-rate tracking |
| **D-4** Mon 31 | W2 ReplayEngine on real `run_daily_cycle` | W5c red-team persona + BLOCK/DOWNGRADE wiring |
| **D-3** Tue 1 | W2 synth chain + sweep → `BACKTEST.md` | W6 signed JSON handoff + fallback chain |
| **D-2** Wed 2 | W3 Greeks + step 6.5 wiring | W5d calibration record + `COUNCIL-V2.md` |
| **D-1** Thu 3 | W4 spread + collar + wheel machine | Full-suite run, doc reconciliation, W7/W12 |
| **D0** Fri 4 | Freeze 06:00 UTC. Demo rehearsal only. | Freeze 06:00 UTC. |

Freeze means freeze. Nothing merges inside the final nine hours except a fix for
something demonstrably broken on stage.

---

## Definition of done

A workstream is done when all four hold:

1. `pytest agent/tests backend/tests -q` green — **both suites**, per JOBDESK.
2. New behaviour has tests that fail against the previous commit. A test that
   passes before your change tests nothing.
3. No network in tests. Fundamentals and chains monkeypatched.
4. The layer doc is updated in the same commit — `AI-ENGINEER.md`,
   `HEDGE-FUND-COUNCIL.md`, `KNOWN-ISSUES.md`, `RISK-MANAGEMENT.md`.

Plus, per JOBDESK: **any modified existing test is called out explicitly in the
commit message.** A silently altered assertion is indistinguishable from a
weakened suite, and W5 touches persona tests by design.

---

## Rules that do not bend

- **Never naked.** Every short call is share-covered, every short put is cash- or
  spread-collateralised. W4's wheel is the highest-risk path here; its state
  machine raises rather than warns for exactly this reason.
- **Kill-switch stays step 1.** W3 inserts at 6.5. Nothing goes before 1.
- **Degrade to `None`, never to a number.** Missing data is not zero, and not a
  guess. This applies to greeks, fundamentals, and IV rank alike.
- **Synthetic data is labelled synthetic** everywhere it surfaces — in
  `BACKTEST.md`, in traces, in the demo.
- **No credentials, no `.env`, no keys.** Verify before every push:
  ```bash
  grep -rInE "PK[A-Z0-9]{15,}" . --exclude-dir=.git --exclude-dir=node_modules
  ```
- **Stay in `agent/**` and `docs/**`.** Backend consumes new capability by
  calling new functions; if a route needs changing, raise it with Aji.

---

## What this buys us with judges

| Question | Answer after this brief |
|---|---|
| "Is the edge real?" | Sweep table, 250+ sessions, synthetic chain declared |
| "What happens on restart?" | SQLite ledger; state survives, demonstrable live |
| "Is it just an LLM voting?" | 7 personas, 2 rounds, red team with BLOCK authority, revision rates published |
| "Can it be gamed?" | Signed handoff, clamped values, visible fallback chain |
| "Portfolio-level risk?" | Net Δ/Θ/Ⅴ/Γ with caps, beta-weighted delta |
| "Only covered calls?" | 5 strategies, defined-risk spread, downside-capping collar, wheel state machine |
| "How do you know the committee is right?" | Calibration ledger — with the sample-size caveat stated, not hidden |

The last row is the one that separates this from every other submission. Most
teams will claim their agent is good. Ours ships the instrument that would catch
it being bad, and says out loud that six days is not enough data to be sure.
