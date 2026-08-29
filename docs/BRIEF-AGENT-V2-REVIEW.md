# BRIEF-AGENT-V2 — REVIEW, CRITICISM, RISK REGISTER

**Companion to** [`BRIEF-AGENT-V2.md`](BRIEF-AGENT-V2.md). Read this first.
**Issued by:** Orchestrator / CTO · 29 Aug 2026
**Audience:** AI engineering (`agent/**`) + hedge-fund council (`agent/council/**`)

---

## 0 · Summary — the brief was wrong about where to start

Before writing this review I probed the running code rather than reading the
docs. Four findings came back, and the first two invalidate the sequencing in
`BRIEF-AGENT-V2.md`.

**The kill-switch is largely inoperative in live operation.** Of its three
triggers, the drawdown check is dead twice over, the consecutive-stop-loss check
is never fed by the backend, and single-day loss is the only one that actually
fires. `RISK-MANAGEMENT.md` describes this as "Layer 1" and the whole
defence-in-depth chain rests on it.

Every workstream in the original brief adds surface area — 3 new strategies, a
7th persona, debate rounds — on top of a safety floor with holes in it. That is
the wrong order. **A new workstream W0 is inserted ahead of everything.**

Evidence for each finding is reproducible below. None of it is inferred from
reading; all of it was executed.

---

## 1 · Finding A — `overlay_only_drawdown` silently disables the drawdown halt

**Severity: CRITICAL.** File: `agent/council/risk_mitigation.py:58-74`.

The overlay-only branch computes overlay equity and then assigns it to *both*
sides of the drawdown ratio:

```python
if overlay_equity > 0:
    dd_equity = overlay_equity
    dd_peak   = overlay_equity      # ← same value
```

`dd = (dd_equity / dd_peak - 1) * 100` is therefore **always exactly 0.0**. The
drawdown comparison can never be true. The source comment says it plainly —
`# Use overlay equity as both current and peak (no separate peak yet)` — so this
is a known placeholder that shipped as a live safety control.

The trigger condition is `overlay_only=True` (the default) **and** a non-empty
positions list. Every real Alpaca position carries `market_value`, so
`overlay_equity > 0` on any live account.

Verified, `-72.5%` drawdown on an Alpaca-shaped book:

```
positions = [{"symbol":"NVDA","qty":100,"current_price":300.0,"market_value":30000.0},
             {"symbol":"MSFT","qty":100,"current_price":250.0,"market_value":25000.0}]
peak_equity = 200000.0     # equity 55000 → -72.5%

run_daily_cycle(...)  →  halted = False   reasons = []
```

Three aggravating factors.

**A1 · The positions list is not filtered to overlay positions.** The sum runs
over whatever it is handed. `daily_cycle` passes `positions` — the *equity* book.
So plain long stock is counted as "overlay collateral", which is what makes
`overlay_equity > 0` fire on every live account. The docstring claims it uses
"short-option positions with a collateral or market_value field"; it filters
nothing.

**A2 · The documented escape hatch does not work.** `RISK-MANAGEMENT.md` says
"Set it to `False` for the stricter interpretation." It cannot be set to `False`:

```python
def _cfg_get(config, name, default) -> float:
    val = getattr(config, name, default)
    return val if isinstance(val, (int, float)) and not isinstance(val, bool) else default
```

`_cfg_get` explicitly rejects bools and returns the default. Verified:

```
raw attr : False        # config.overlay_only_drawdown = False
_cfg_get : True         # ← default returned
bool()   : True         # overlay-only branch stays on
```

The helper was written for numeric thresholds and hardened against bools
(reasonably — `True` would be a nonsense threshold). Reusing it for a boolean
flag makes that flag permanently unsettable. So the only documented mitigation
for A is unreachable, and `overlay_only_drawdown` is dead config.

**A3 · The test passes for the wrong reason, which is why nobody caught this.**
`test_daily_cycle.py::test_drawdown_breach_halts` is green. Its fixture position
is `{"symbol":"AAPL","qty":50,"current_price":100.0}` — **no `market_value`
key**. So `overlay_equity` sums to `0.0`, the branch falls through to full NAV,
and the halt fires:

```
TEST fixture keys: ['symbol','qty','current_price']
  overlay_equity = 0.0   → kill: halted=True   ← passes

REAL Alpaca keys : ['symbol','qty','current_price','market_value']
  overlay_equity = 5000.0 → kill: halted=False  ← production
```

The test and production take opposite branches. A green suite has been reporting
that the drawdown kill-switch works, for a code path production never executes.
This is worse than an untested control, because it actively suppressed suspicion.

---

## 2 · Finding B — the backend feeds `peak_equity` the current equity

**Severity: HIGH.** File: `backend/app/routes/council.py:269-273`.

```python
state_overrides = {
    "peak_equity": _f(account.get("equity")) or None,       # ← current equity
    "prev_equity": _f(account.get("last_equity")) or None,  # ← correct
    **(req.portfolio_state_overrides or {}),
}
```

`peak_equity` is set from Alpaca's **current** equity, not a historical
high-water mark. So `dd = (equity / equity - 1) = 0` — the drawdown check is
neutralised a second time, independently of Finding A. Fixing A alone changes
nothing in production; both must be fixed.

`prev_equity ← last_equity` is genuinely correct, which is why single-day loss
is the one trigger that works.

**`consecutive_stop_losses` is never populated by the backend at all.**
`_build_portfolio_state` reads it only from overrides, and the sole live caller
does not set it. Its only path is a manually crafted
`portfolio_state_overrides` in a request body — i.e. the demo, or a test.

Live status of Layer 1, measured:

| Trigger | Live status |
|---|---|
| Drawdown from peak | **Dead** — Finding A *and* Finding B, independently |
| Single-day loss | **Works** |
| Consecutive stop-losses | **Never fed** — dead outside manual override |

Verified on an Alpaca-shaped book with honest history supplied:

```
drawdown -72% from 200k peak   halted=False  reasons=[]
single-day loss -72%           halted=True   ['single-day loss -72.50% ...']
5 consecutive stop-losses      halted=True   ['5 consecutive stop-losses ...']
```

The middle two only halt because the probe hand-fed overrides the backend never
sends.

This reframes `KNOWN-ISSUES.md` #11 — *"Kill-switch state is not persisted —
LOW"*. Persistence is the smaller half. The counter is not merely lost on
restart; it is **never computed at all**. Reclassify as HIGH and restate: there
is no producer for the consecutive-stop-loss signal anywhere in the system.
W1's `exit_event` table is that producer, which makes W1 a correctness fix, not
a durability improvement.

**Ownership note.** The `peak_equity` line is in `backend/**`, which per
`JOBDESK.md` belongs to Aji. Do not edit it. The agent-layer fix is to stop
trusting a caller-supplied peak: derive the high-water mark from the W1
`peak_equity` table and treat any override as a *candidate* max, never as truth.
That fixes it from inside our boundary and removes the class of bug rather than
one instance. Tell Aji regardless.

---

## 3 · Finding C — the snapshot timeout does not time out

**Severity: HIGH (demo-fatal).** File: `agent/council/daily_cycle.py:129-140`.

```python
def _fetch_one(sym):
    for attempt in range(_FETCH_RETRIES):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_provider_fetch_snapshot, sym)
                return fut.result(timeout=_FETCH_TIMEOUT)
        except (_FuturesTimeoutError, Exception):
            _time.sleep(0.2 * (attempt + 1))
    return None
```

`fut.result(timeout=...)` raises `TimeoutError` on schedule, but the exception
propagates **out of the `with` block**, and `ThreadPoolExecutor.__exit__` calls
`shutdown(wait=True)`. That joins the still-running worker. The `except` clause
does not begin executing until the fetch it was supposed to abandon has
finished. The timeout is advisory.

Measured with a 6-second task and a 1-second timeout:

```
TimeoutError raised at t=6.00s (inside with-block)
control returned to caller at t=6.00s
```

`fetch_timeout_seconds=5.0` bounds nothing. The real bound is
`FundamentalsProvider(timeout=15.0)` × the HTTP calls per symbol (cookie, crumb,
quoteSummary, chart ≈ 4) = **up to 60s per symbol per attempt**. With
`fetch_retries=2` over the 8-symbol universe in a serial loop:

```
8 symbols × 2 retries × 4 calls × 15s = 960s = 16 minutes
```

`RISK-MANAGEMENT.md` and `AI-ENGINEER.md` both advertise this as "timeout +
retry ... so the cycle completes rather than hanging". Under a network stall it
hangs — for up to sixteen minutes, in the request path of
`POST /api/agent/run`, with a judge watching.

Two secondary defects in the same function:

**C1 · `except (_FuturesTimeoutError, Exception)` catches everything**, including
`KeyboardInterrupt`-adjacent programming errors — a typo inside
`_provider_fetch_snapshot` is silently retried and then reported as a clean
"symbol unavailable". `Exception` alone already subsumes the first member; the
tuple is decorative.

**C2 · A fresh `ThreadPoolExecutor` is constructed per attempt per symbol** —
16 thread pools for a cold 8-symbol run. Harmless in isolation, wasteful, and a
sign the block was written without the shutdown semantics in mind.

Correct shape: **one** executor for the whole batch, `submit()` all symbols,
`as_completed(timeout=budget)`, cancel the remainder, and enforce an overall
wall-clock budget for the step in addition to any per-symbol timeout. Set
`FundamentalsProvider(timeout=...)` from the same budget so the inner bound is
never larger than the outer.

---

## 4 · Finding D — the fundamentals cache is world-writable

**Severity: MEDIUM (elevated from `KNOWN-ISSUES` #1).**

`agent/council/fundamentals.py:26` — `CACHE_PATH = Path("/tmp/fundamentals_cache.json")`.

`KNOWN-ISSUES` #1 frames this as durability: a restart loses the cache and the
council silently drops to LOW confidence. Correct, and the demo-failure argument
stands. But there is a second dimension nobody logged.

`/tmp` is mode `0o41777`, sticky, shared. The path is fixed and predictable. Any
other process on the box can pre-create or overwrite that file, and the loader
does no validation beyond a JSON parse and a TTL check. **Fundamentals are an
input to persona scoring, and persona output drives the HANDOFF tier policy.**

That is the same trust boundary as security finding S5 — where a crafted council
report could inject `delta 0.99` — reached one step earlier in the pipeline. S5
was rated worth fixing and is still tracked as open. This is its sibling and it
is not tracked at all.

The sticky bit prevents *deleting* another user's file; it does not prevent
creating the file first, and it does not help at all against anything running as
the same user — which on this box is `root`.

Moving the cache to `docs/.cache/` (already planned in W1) fixes durability and
this simultaneously. Add: reject cache entries whose shape does not validate, and
record `source: "cache"` vs `"live"` on the merged snapshot so a persona bullet
can say where its P/E came from.

---

## 5 · Criticism of the original brief

Where `BRIEF-AGENT-V2.md` is wrong, in order of consequence.

### 5.1 · It sequences new capability ahead of a broken safety floor

The brief opens by claiming the agent layer is "correct but small" and that a
judge hits the floor on backtest, restart behaviour, and committee depth. That
was written from the docs. The floor is lower: Layer 1 does not work. W1–W6 all
add surface on top of it.

W0 (below) is inserted ahead of everything. W4 (three new strategies) is demoted
to optional — tripling strategy count while the kill-switch is holed is
indefensible, and 5 strategies with a broken halt is a worse submission than 2
with a working one.

### 5.2 · It trusted the documentation it should have audited

Three claims in `RISK-MANAGEMENT.md` are false in the running code, and the brief
repeated the framing of all three:

| Doc claim | Reality |
|---|---|
| "Set `overlay_only_drawdown` to `False` for the stricter interpretation" | Unsettable — `_cfg_get` rejects bools |
| Overlay drawdown uses "short-option positions with a collateral or market_value field" | No filtering; receives the equity book |
| "timeout + retry ... so the cycle completes rather than hanging" | Timeout does not interrupt; up to 16 min |

Lesson for every workstream below: **the acceptance criterion is executed
output, not a passing test and not a doc paragraph.** Finding A had a green test
for eighteen days.

### 5.3 · W2's central claim is undermined by its own data source

The brief calls the backtest "the single highest-value item" and requires
`ReplayEngine` to call production `run_daily_cycle` — both correct. But
`synth_chain.py` prices contracts with Black-Scholes from realised vol.

A premium-selling edge comes from **implied minus realised** volatility. If
implied is *derived* from realised, that spread is whatever the pricing
assumption inserts. The sweep will then "discover" the parameters that best
harvest an assumption. It cannot validate the 60/200 asymmetry, because the
asymmetry's justification is the volatility risk premium and the synthetic chain
has no volatility risk premium in it.

Not a reason to drop W2 — path-dependent behaviour is still worth measuring:
exit-trigger frequency, roll cadence, assignment counts, cap-breach rates,
drawdown shape. Those are real findings. But `BACKTEST.md` must state in its
first paragraph that **no conclusion about profitability follows**, and the sweep
table must not be presented as parameter validation. A judge who understands
options will ask where the IV came from, and the honest answer must already be
written down.

Retitle the deliverable **"Behavioural replay"**, not "Backtest".

### 5.4 · The optional tier is misordered

W8 (IV rank) sits at position 8, described as making the "don't sell cheap
premium" filter enforceable. But per 5.3, W2's sweep is uninterpretable without
a real IV series — and W8 is what supplies one. W8 is a **prerequisite for W2
meaning anything**, not an afterthought. Promoted.

W12 (`premium <= 0` guard) is two lines that prevent a `ZeroDivisionError` in the
exit path — the exit path being the one that closes losing positions. Two lines
guarding the loss-cutting code should not be item 12. Promoted into W0.

### 5.5 · W5b can quietly destroy the council's only real signal

The brief flags that a persona revising toward consensus every round is
worthless, and asks for `revision_rate` tracking with a 0.7 threshold. Good, but
the guard is a report field — it detects the failure after the fact and does not
prevent it.

Stronger requirement: `test_council.py::test_contrarian_bearish_dissent_detected_on_value_trap`
must pass **with debate enabled**, and a new test must assert that at least one
persona's post-debate stance still differs from the majority on a constructed
split case. If debate cannot preserve disagreement, ship round 1 only. Six
personas that always agree is a single scoring function with extra steps — the
exact black box the council was built to avoid.

### 5.6 · The schedule has no slack and the freeze is too late

Seven workstreams across six days, two owners, zero buffer, and W2 depends on W1
completing on time. One slip cascades to D0.

`ROADMAP.md` also records that the frontend "has run ahead of its verification
for three consecutive days" — that pattern is precisely what an unbuffered plan
produces. Revised schedule (§7) inserts a checkpoint on D-3: anything not
merged by then is cut, not compressed.

Freeze moves from 06:00 to **D-1 18:00 UTC**, ~21 hours before submission. A
06:00-on-deadline-day freeze leaves no room to discover that the freeze broke
something.

---

## 6 · W0 — Restore the safety floor · MANDATORY, BLOCKS EVERYTHING

**Owner:** AI engineering · **Nothing else merges until W0 is green.**

### W0.1 · Fix the overlay drawdown ratio

Track a genuine overlay high-water mark instead of comparing a value to itself.
Until W1's `peak_equity` table exists, take the peak from
`portfolio_state["overlay_peak_equity"]`; when W1 lands, read it from the ledger.

**If no overlay peak is available, do not fall back to a zero-drawdown result.**
Fall back to full-NAV drawdown and emit a trace line saying so. An unknown peak
must never read as "no drawdown" — that is the entire shape of Finding A.

### W0.2 · Filter to actual overlay positions

`overlay_equity` must sum only short-option positions. Detect by OCC symbol
format plus negative quantity; `exit_manager._dte_of` already parses OCC and can
be reused. Long stock is not overlay collateral.

### W0.3 · Make `overlay_only_drawdown` settable

Add `_cfg_flag(config, name, default) -> bool` alongside `_cfg_get` and use it
for boolean config. Do not loosen `_cfg_get` — its bool rejection is correct for
numeric thresholds and removing it would let `True` through as a threshold value.

### W0.4 · Test against production-shaped positions

`test_daily_cycle.py`'s fixture must include `market_value` on every position,
because live Alpaca positions always do. Then add:

- drawdown halt fires with `market_value` present and overlay positions present
- drawdown halt fires with overlay positions and no overlay peak (NAV fallback)
- `overlay_only_drawdown=False` actually reaches the NAV branch
- long-only equity book yields `overlay_equity == 0`
- overlay book down 60% against a real overlay peak halts

Per `JOBDESK.md`: **this modifies an existing fixture — say so explicitly in the
commit message.** Expect `test_drawdown_breach_halts` to fail once the fixture is
corrected. That failure is the bug becoming visible; fix the code, not the test.

### W0.5 · Bound the snapshot step for real

One executor for the batch, `as_completed(timeout=budget)`, cancel stragglers,
overall wall-clock budget for the step, `FundamentalsProvider(timeout=…)` derived
from the same budget. Narrow `except (_FuturesTimeoutError, Exception)` to
`Exception` and log the type. Test with a monkeypatched fetcher that sleeps 30s
and assert the step returns in under the budget.

### W0.6 · `premium <= 0` guard

`if premium <= 0: return MONITOR` in `exit_manager`. Two lines. Was W12.

### W0.7 · Consecutive-stop-loss producer

Nothing computes this signal. Derive it from the W1 `exit_event` table: count
trailing `STOP_LOSS` exits, reset on any non-stop exit. Until W1 lands, at least
compute it within a single cycle from exit evaluations. A caller-supplied
override stays supported for demos but must never be the only source.

### W0.8 · Correct the three false doc claims

Fix `RISK-MANAGEMENT.md` (§Layer 1, §Layer 3) and `AI-ENGINEER.md` (resilience
paragraph). Add all four findings to `KNOWN-ISSUES.md` and reclassify #11 from
LOW to HIGH with the restated cause.

**Acceptance for W0:** each of the four findings has a test that fails on the
current commit and passes after, plus a pasted terminal transcript in the commit
message showing the halt firing on an Alpaca-shaped book. `pytest agent/tests
backend/tests -q` green.

---

## 7 · Revised plan and schedule

| WS | Was | Now | Why |
|---|---|---|---|
| **W0** | — | **MANDATORY, blocking** | Layer 1 is not operational |
| W1 state ledger | mandatory | **mandatory** | Now also the producer for W0.7 |
| W2 replay | mandatory | **mandatory, retitled** | "Behavioural replay"; no profitability claim |
| W3 greeks | mandatory | **mandatory** | Unaffected |
| W4 strategies | mandatory | **optional** | Do not widen surface over a holed floor |
| W5 council v2 | mandatory | **mandatory, 5a+5c only** | 5b debate optional, must preserve dissent |
| W6 signed handoff | mandatory | **mandatory** | Unaffected |
| W8 IV rank | optional #8 | **promoted, mandatory** | W2 is uninterpretable without real IV |
| W7 hysteresis | optional | optional | Unchanged |
| W9–W11 | optional | optional | Unchanged |
| W12 premium guard | optional #12 | **folded into W0.6** | Two lines in the loss-cutting path |

| Day | AI engineering | Council |
|---|---|---|
| **D-6** Sat 29 | **W0.1–W0.4** — drawdown fix + fixture correction | W5a half-fail, rerun 8-symbol assessment |
| **D-5** Sun 30 | **W0.5–W0.8** — timeout, guard, producer, docs | W6 signed JSON handoff + fallback chain |
| **D-4** Mon 31 | W1 store + ledger + cache off `/tmp` | W5c red-team persona + BLOCK/DOWNGRADE |
| **D-3** Tue 1 | W8 IV rank series · **CHECKPOINT 18:00** | Calibration record · **CHECKPOINT 18:00** |
| **D-2** Wed 2 | W2 replay on production `run_daily_cycle` | `COUNCIL-V2.md`, doc reconciliation |
| **D-1** Thu 3 | W3 greeks + step 6.5 · **FREEZE 18:00 UTC** | Full-suite run · **FREEZE 18:00 UTC** |
| **D0** Fri 4 | Rehearsal only. No merges. | Rehearsal only. No merges. |

**D-3 18:00 checkpoint:** anything not merged is cut, not compressed. W4 and
W5b are the designated cut lines — they are already optional, so cutting them
costs nothing that was promised.

---

## 8 · Risk register

Likelihood × impact, highest first. Every row has a named mitigation, an owner,
and a trigger that says when to abandon the plan rather than push on.

### R1 · A judge asks about risk controls and the kill-switch is provably broken
**L: high (it is broken now) · I: fatal**

Direct contradiction between a demo and `RISK-MANAGEMENT.md`, in the one area
that matters most for a trading agent.

**Mitigation:** W0 first, nothing else merges before it. Demo script must include
a live halt on an Alpaca-shaped book, executed on stage, not a screenshot.
**Trigger:** not green by D-5 18:00 → stop all other work, both owners on W0.

### R2 · Replay results get read as proof of profitability
**L: high · I: severe (credibility)**

Synthetic IV derived from realised vol cannot demonstrate a volatility risk
premium. Presenting the sweep as validation is the kind of overclaim that gets
found out in Q&A.

**Mitigation:** retitle to "Behavioural replay". First paragraph of
`BACKTEST.md` states no profitability conclusion follows. Sweep table reports
behavioural metrics only — trigger frequency, roll cadence, assignment count,
cap breaches, drawdown shape. W8 supplies real IV percentile so at least the
entry filter is measured against something observed.
**Trigger:** W8 not landed by D-2 → publish behavioural metrics only and say
explicitly that parameter selection remains unvalidated.

### R3 · W0's fixture correction cascades into unrelated failures
**L: medium · I: medium**

Adding `market_value` to shared fixtures changes `_position_value` for every test
that consumes them. Other assertions may shift.

**Mitigation:** land W0.4 as its own commit. Run both suites before and after and
diff the pass list. Any newly failing test is triaged individually — a test that
starts failing because positions became realistic was probably asserting on
unrealistic input.
**Trigger:** more than 5 unrelated failures → add production-shaped fixtures
alongside the existing ones instead of mutating them, and migrate incrementally.

### R4 · Debate collapses the council into one voice
**L: medium · I: high (kills the differentiator)**

If every persona revises toward consensus, six named philosophies become one
scoring function with extra steps.

**Mitigation:** W5b is optional and gated on two tests — the existing value-trap
dissent test passing with debate on, and a new test asserting a surviving
minority stance on a constructed split. `revision_rate` per persona published in
the report.
**Trigger:** either test fails → ship round 1 only. This is a cut, not a fix
attempt.

### R5 · Scope overrun leaves several workstreams half-finished
**L: medium-high · I: high**

The original brief was deliberately oversized, W0 adds eight sub-items, and the
frontend has already shown this failure pattern three days running.

**Mitigation:** hard D-3 18:00 checkpoint. W4 and W5b pre-designated as cuts.
Freeze at D-1 18:00, ~21h of margin.
**Trigger:** at D-3, fewer than four mandatory workstreams green → cut to
W0 + W1 + W6 and spend the rest on the demo. A small, honest, working system
beats a large broken one.

### R6 · Live Alpaca credentials unavailable or rate-limited at demo time
**L: medium · I: high**

Order preview returns `None` when `is_configured()` is false, so the feature is
invisible in mock mode — `ROADMAP.md` item 3 already notes this. W8 also needs
market data.

**Mitigation:** mock option chain so order preview demos offline. Every
capability must be demonstrable in mock mode. Ship a seeded ledger snapshot so
W1 persistence is provable without live history.
**Trigger:** any capability that only works live is dropped from the demo script,
regardless of how good it looks.

### R7 · Fundamentals provider blocks or breaks during the demo
**L: medium · I: high (compounds R1)**

Yahoo endpoints are undocumented and unversioned. Under a stall, Finding C's
16-minute hang lands in the request path.

**Mitigation:** W0.5 caps the step. W1 persists the cache to `docs/.cache/` so a
cold start is not required. Snapshot carries `stale` + `data_age_hours`, and any
persona relying on stale data says so in its bullet.
**Trigger:** provider failing on D-1 → demo runs from the persisted cache and the
narration states the data age. Stale-and-labelled is fine; silently stale is not.

### R8 · Boundary violation into `backend/**` or `frontend/**`
**L: medium · I: medium**

Finding B is a backend line. The temptation to fix it directly is real, and
`JOBDESK.md` records two incidents already caused by exactly this.

**Mitigation:** derive the high-water mark inside the agent layer and treat any
caller override as a candidate max. Report Finding B to Aji with the reproduction
so he can fix his own line. Read the full diff before every commit.
**Trigger:** the fix genuinely cannot be contained in `agent/**` → raise with the
orchestrator, do not edit across the boundary unilaterally.

### R9 · Signed handoff locks out the demo
**L: low-medium · I: medium**

If `COUNCIL_HANDOFF_KEY` is unset or the report regenerates unsigned, the
fallback chain must degrade rather than fail.

**Mitigation:** fallback order JSON-signed → JSON-unsigned (warn) → markdown
(warn) → defaults (warn), every step visible in the trace. Test all four paths.
Never make an absent key fatal.
**Trigger:** signature verification blocks a legitimate report → run unsigned
with the warning and note it as future work.

### R10 · New Greeks caps block every trade in the demo
**L: low-medium · I: medium**

`min_net_theta` and vega caps are untuned. Set too tight, step 6.5 downgrades
everything to MONITOR and the demo shows an agent that never acts.

**Mitigation:** derive initial caps from the mock portfolio so at least one
candidate passes. Log the computed exposure next to every cap in the trace so a
block is explainable. Any cap breach that downgrades must name the Greek and
the resulting number.
**Trigger:** demo portfolio produces zero `INITIATE` directives → loosen caps and
document the loosening. A blocked-everything demo teaches a judge nothing.

### R11 · Persistence bugs corrupt state mid-demo
**L: low · I: high**

SQLite plus a crash mid-cycle is a new failure mode the system has never had.

**Mitigation:** WAL mode, atomic per-cycle transactions, schema versioning with
`migrate()`. `:memory:` construction for tests. Explicit crash-recovery test:
kill mid-cycle, restart, assert counters and peak intact.
**Trigger:** corruption reproduces even once → ship a read-only ledger for the
demo, keeping live counters in-process.

### R12 · Wheel state machine produces a naked position
**L: low · I: fatal if it happens**

The wheel is the only strategy that transitions between short-put and
short-call states. A bad transition means an uncovered short — the one thing the
entire risk model forbids.

**Mitigation:** W4 is already optional and should be cut under pressure. If
built: illegal transitions raise, never warn; assert share coverage at every
`SHORT_CALL` entry; exhaustive tests over legal and illegal transitions.
**Trigger:** any ambiguity about coverage in a transition → cut W4 entirely. Two
working strategies beat three with a hole.

---

## 9 · Standing rules, reinforced

Everything in `BRIEF-AGENT-V2.md` §"Rules that do not bend" still applies. Three
additions from these findings:

1. **Unknown must never read as safe.** A missing peak is not zero drawdown. A
   missing greek is not flat. A missing fundamental is not a pass. Every fallback
   in a safety path defaults to the *conservative* branch and says so in the
   trace.
2. **A green test is not evidence a control works.** Finding A had one for
   eighteen days. Acceptance is executed output against production-shaped input,
   pasted into the commit message.
3. **Test fixtures must match production payload shape.** Live Alpaca positions
   always carry `market_value`. A fixture that omits a field production always
   sends is testing a code path that never runs.

