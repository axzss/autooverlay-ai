# BRIEF-FRONTEND-V2 — Scale-Up Mandate for the Frontend Team

**Status note 2026-09-02:** `BotActivityPanel` log viewer now renders structured log fields with HTTP status/level colors, thin/transparent autoscrolling scroll, and the dashboard bot card exposes an explicit `Auto execute` toggle backed by `POST /api/bot/config`.

**Issued by:** Orchestrator / CTO
**Owner:** Frontend — `frontend/**` (`axzss`)
**Out of scope:** `agent/**`, `backend/**`, `docs/**` except this file's status log.
New backend surface is requested through §9 (Contract Requests), never edited directly.
**Window:** D-6 (29 Aug) → D0 (4 Sep, 15:00 UTC submission). Freeze 06:00 UTC on D0.
**Companion brief:** [`BRIEF-AGENT-V2.md`](BRIEF-AGENT-V2.md) — the agent layer is
growing from 2 strategies / 6 personas / no memory to 5 strategies / 7 personas
with debate, a red team, a SQLite ledger, a backtest sweep and portfolio Greeks.
**None of that is visible today.** This brief is the surface that makes it real.

---

## 0 · Why this brief exists

The frontend is honest and it compiles. That is where the compliments end.

Five pages render a portfolio, one screening list, one council board and one
agent run. A judge who clicks through reaches the floor in about forty seconds,
because the UI answers exactly one question — *what did the agent just say?* —
and none of the questions a trading-bot demo lives or dies on:

1. **Is it alive?** Everything is request/response on mount. Nothing streams,
   nothing ticks, nothing updates while you watch. A trading bot that only moves
   when you press a button reads as a form, not an agent.
2. **What is the risk right now?** Two boolean chips (`concentration_ok`,
   `cash_reserve_ok`). No net delta, no theta, no vega, no beta-weighted
   exposure, no cap-breach surface.
3. **Did anyone argue?** `CouncilBoard` shows six verdicts and a dissent list.
   Round 2 revisions, revision rates and red-team `BLOCK`/`DOWNGRADE` challenges
   have nowhere to render.
4. **Does the edge exist?** The backtest sweep lands as a markdown table in
   `docs/`. Judges will not read a markdown table.
5. **What happened before now?** The ledger will hold every cycle, directive and
   exit event ever emitted. The UI has no concept of history.

**One correction to the framing above, verified 29 Aug.** An earlier draft of this
brief claimed the frontend had no tests and had never been opened in a browser.
Both are false: 105 vitest tests and 20 Playwright tests exist, and three E2E
specs are regression tests for bugs a human found by opening the app. What is
true and worse is that **three of those tests fail on `main` right now** — see F6,
which was rewritten accordingly. The lesson for everyone reading: check the tree
before you believe a brief, including this one.

Standing rule for this layer, unchanged and non-negotiable: **never render a
number the backend did not produce.** An empty state is information. A plausible
placeholder is a lie that survives into the demo. Every new panel below must
degrade to an explicit "not reported by backend" state, not to zero.

Second rule, new: **this brief is deliberately larger than six comfortable days.**
F1–F6 are mandatory. F7–F12 are ranked spend-if-you-have-it. Ship
mandatory-complete rather than everything half-done.

---

## 1 · Target end-state

| Dimension | Today | Target D0 |
|---|---|---|
| Data flow | fetch-on-mount, manual refresh | live polling + SSE stream, per-panel staleness |
| Pages | 5 (dashboard, assets, terminal, council, settings) | 9 (+ risk, lab, ledger, blotter) |
| Risk surface | 2 boolean chips | net Δ/Θ/V/Γ cockpit, per-symbol matrix, cap breaches |
| Council view | 6 verdicts, flat dissent | 7 personas, 2 rounds, revision deltas, red-team challenges |
| Evidence of edge | none in UI | backtest lab: sweep heatmap, equity curve, synthetic-data banner |
| Strategy support | covered call / CSP shapes | 5 strategies incl. multi-leg spread, collar, wheel machine |
| Order path | intent list, no approval UX | approve/reject queue, guarded submit, blotter with fills |
| History | none | ledger timeline, cycle replay, calibration scoreboard |
| Motion | full framer-motion pass, unverified | verified, reduced-motion honoured, lazy-loaded |
| Tests | 105 unit + 20 E2E, **3 failing** | all green + coverage on new panels |
| Verification | 3 bugs already caught in-browser; no committed evidence | screenshot evidence per route at 2 widths |

---

## MANDATORY WORKSTREAMS

Each workstream below has a companion implementation spec. The brief says *what and
why*; the spec says *exactly how*, down to signatures, states and Tailwind tokens.
Read the spec before writing code — it resolves the ambiguities this brief leaves.

| Workstream | Spec | Lines |
|---|---|---|
| F1 live data layer | [`SPEC-F1-LIVE-DATA.md`](SPEC-F1-LIVE-DATA.md) | 1,387 |
| F2 risk cockpit | [`SPEC-F2-RISK-COCKPIT.md`](SPEC-F2-RISK-COCKPIT.md) | 953 |
| F3 council v2 | [`SPEC-F3-COUNCIL-V2.md`](SPEC-F3-COUNCIL-V2.md) | 1,266 |
| F5 blotter + approval | [`SPEC-F5-BLOTTER.md`](SPEC-F5-BLOTTER.md) | 883 |
| F4, F6 | no spec — F4 is conditional, F6 is defined inline below | — |

Supporting documents: [`BRIEF-FRONTEND-V2-CRITIQUE.md`](BRIEF-FRONTEND-V2-CRITIQUE.md)
(the red-team review that corrected this brief's false premises) and
[`FRONTEND-RISK-REGISTER.md`](FRONTEND-RISK-REGISTER.md) (22 risks, the demo-day
playbook, and the ranked cut list).

**Three findings from the specs that override this brief.** Each was verified
against the tree before being accepted:

1. **`ScoreGauge` must not be reused on `/risk`.** SPEC-F2 §2 rejects it, and it is
   right: `charts/ScoreGauge.tsx:26` reads
   `Math.max(0, Math.min(100, Number.isFinite(score) ? score : 0))`. It clamps a
   non-finite value **to zero** — precisely the lie the risk page exists to
   prevent. A `null` net vega passed through it would render `0.0`. Build the
   `CapGauge` sibling instead.
2. **`client_order_id` already exists server-side.** SPEC-F5 §4 builds idempotency
   on it, and `backend/app/routes/trade.py:29` accepts it
   (`Field(default=None, max_length=128)`), forwarding at `:77-78` and echoing at
   `:101`. Alpaca rejects duplicates itself. So the frontend's double-submit guard
   needs **no backend change at all** — only an added field on the `TradeRequest`
   interface in `lib/api.ts`, which currently omits it.
3. **KNOWN-ISSUES #2 is being fixed underneath us.** `backend/app/routes/agent.py:19`
   now has `_pick_option_contract()` — fix (a) from that issue. SPEC-F5 §3.3
   correctly keys every rule on the null *value* rather than on the issue's status,
   so it holds whether or not the fix lands. Do the same everywhere: a resolved
   contract must not become an assumption.

### F1 · Live data layer — `frontend/lib/live/`
**Owner:** frontend · **Closes:** the "is it alive?" gap · **Blocks:** F2, F3, F6

Today `lib/api.ts` is one `request()` helper plus a single `usePortfolio` hook
that fires once on mount. Every other page calls `api.*` inline in a `useEffect`
and owns its own loading/error booleans. That is why nothing on the screen ever
moves, and why five pages each reimplement the same three states slightly
differently.

Replace with a real data layer. `@tanstack/react-query` v5 is already a
dependency and currently unused — that is the tool.

```
frontend/lib/live/
├── queryClient.ts    single QueryClient, sane retry/stale defaults
├── keys.ts           typed query-key factory — no stringly-typed keys
├── hooks.ts          usePortfolioQuery, useHealthQuery, useScreenQuery,
│                     useAgentRun (mutation), useCouncilQuery, useRiskQuery
├── stream.ts         EventSource wrapper for the agent event stream
└── freshness.ts      per-query staleness → 'live' | 'stale' | 'offline'
```

Hard requirements:

- **One provider.** `app/components/Providers.tsx` mounts `QueryClientProvider`
  once. The four dead per-route `Providers.tsx` stubs (KNOWN-ISSUES #13) are
  deleted in this workstream, not left for later.
- **Polling intervals differ by cost.** Portfolio and health poll on a short
  interval; `/strategy/screen` is expensive and polls slowly or on demand;
  `/agent/run` is a mutation and never polls. Encode the intervals in one table
  in `keys.ts` so nobody has to grep for a magic number.
- **Pause when hidden.** `refetchIntervalInBackground: false` plus a
  `visibilitychange` guard. A demo laptop left on the council page for an hour
  must not have hammered Alpaca ten thousand times.
- **Staleness is rendered, not hidden.** Every panel gets a freshness dot fed by
  `freshness.ts`: green when the last successful fetch is inside the interval,
  amber when the data is older than its interval, red when the last attempt
  failed. `usePortfolio`'s current mock fallback must keep working and must be
  visibly labelled — it already is, do not regress it.
- **`AbortController` semantics stay.** The existing timeout split (30s for
  agent/council/screen, 8s for reads) is correct and hard-won; carry it over
  verbatim, including the distinction between "timed out" and "unreachable".
- **The old exports keep working during migration.** `usePortfolio`,
  `normalizeScreenings`, `toFeedEntry`, `riskBadgeClasses` and `actionLabel` are
  imported across five files; re-export them from `lib/api.ts` until every caller
  is migrated, then remove in one commit.

`stream.ts` is the piece that makes the bot look alive. `GET /api/agent/stream`
is requested in §9; until it exists, `stream.ts` must fall back to polling and
say so in the connection indicator — **not** fake events on a timer.

Acceptance: all five existing pages migrated, no `useEffect(() => { api.… })`
left in any page component, freshness dot visible on every data panel, and
`npx tsc --noEmit` clean.

**Verified defect this workstream must also close.** `FRONTEND.md` claims
`lib/api.ts` is "the only place `fetch()` appears". That is false:
`app/components/StrategyConfigCard.tsx:43` and `:69` call
`fetch('/api/strategy/config')` directly — a raw GET and a raw mutating write to
the live strategy config. Both bypass the `AbortController` timeout, the
`ApiError` typing, and the timed-out-vs-unreachable distinction that the rest of
the app depends on. `GET /api/strategy/config` is also absent from the `api`
object entirely. Add `getStrategyConfig` / `updateStrategyConfig` to the client,
migrate the component, and correct the claim in `FRONTEND.md` in the same commit.
A settings page that can silently hang while writing strategy parameters is a
worse bug than anything else in this workstream.

---

### F2 · Risk cockpit — `app/risk/page.tsx`
**Owner:** frontend · **Consumes:** BRIEF-AGENT-V2 W3 (portfolio Greeks)

The single biggest credibility gap. An options overlay whose UI cannot state its
net delta is not a risk-managed system, it is a screener with a nice font.

New route `/risk`, plus a compact summary strip pinned to the dashboard.

Components under `app/components/risk/`:

| Component | Renders |
|---|---|
| `GreeksCockpit` | net Δ / Θ / V / Γ as four gauges with cap bands and current value |
| `BetaWeightedDelta` | SPY-normalised delta vs `max_beta_weighted_delta_pct_nav` |
| `ExposureMatrix` | per-symbol × per-greek table, sortable, breach cells highlighted |
| `CapBreachList` | every entry in `PortfolioGreeks.breaches`, severity-ordered |
| `KillSwitchPanel` | halted state, each reason, and what clears it |

**`ThetaLadder` — permitted only as a labelled projection.** The first draft of
this brief listed it plainly; the critique cut it; [`SPEC-F2-RISK-COCKPIT.md`](SPEC-F2-RISK-COCKPIT.md)
§4 argued it back in and won. The argument that decided it: net theta is one
scalar, a judge's immediate next question is "how much of that decays before
expiry", and the honesty rule forbids rendering an unproduced number *as a
reading* — not stating a model. The precedent is already in this project: W2's
synthetic option chains ship **labelled**, not suppressed.

So it is allowed, bound to requirement R8 of that spec: a persistent
`PROJECTION — NOT BACKEND DATA` badge (never a tooltip), its four assumptions
printed verbatim under the chart, `secondary` `#fbbf24` series so it is
chromatically distinct from every measured panel, and the unknown-card when
`net_theta` is `null`. Ship it with every one of those or do not ship it.

Priority within F2, since the whole workstream is likely to be squeezed:
`KillSwitchPanel` first (it works off existing `/agent/run` data and needs no new
endpoint), then `GreeksCockpit`, then `CapBreachList`. `ExposureMatrix` is the
first thing to cut — polish on data that may arrive entirely `null` — and
`ThetaLadder` the second.

Non-negotiable rendering rules:

- **`null` is not `0`.** W3 specifies missing greeks degrade to `None`. A `null`
  net vega renders as `—` with the tooltip "not reported by backend", never as
  `0.00`. Zero is a claim of flatness; showing it when the backend admitted
  ignorance is the exact lie this layer exists to avoid.
- **Caps come from the backend, not the frontend.** Never hardcode a threshold.
  If `max_net_vega_pct_nav` is absent from the payload, the gauge renders the
  value without a band and labels the cap "not configured".
- **Breach severity is visual and textual.** Colour alone fails accessibility and
  fails a projector; every breach cell carries a text badge too.
- Kill-switch HALT must be impossible to miss: full-width banner, reasons listed,
  and every "run agent" affordance across the app disabled while halted.

Acceptance: renders correctly against a payload with all greeks present, one
greek `null`, no caps configured, and a HALT state. All four states screenshotted
into `docs/frontend-verification/`.

---

### F3 · Council v2 surface — debate, red team, calibration
**Owner:** frontend · **Consumes:** BRIEF-AGENT-V2 W5 · **File:** `app/council/`

`CouncilBoard.tsx` is 265 lines rendering six verdict cards and a flat dissent
list. W5 turns the council into a two-round debate with a seventh adversarial
member and a calibration ledger. Three new surfaces:

**3a · Debate timeline.** Round 1 verdict → round 2 revision, side by side per
persona. Show the score delta explicitly (`68.0 → 67.6`), the `revision_reason`,
and an unmistakable marker on personas that did **not** revise — holding a
position under pressure is a signal, not an absence of one.

**3b · Revision-rate meter.** W5b tracks `revision_rate` per persona and declares
anything above 0.7 broken rather than agreeable. Render that as a per-persona
bar with the 0.7 line drawn in. When a persona crosses it, the UI says
"capitulating — not independent", because a committee that becomes one voice with
six names is the failure mode this whole feature exists to detect.

**3c · Red-team challenge panel.** `RedTeamChallenge` has `severity`
(`BLOCK` / `DOWNGRADE` / `NOTE`), `attack`, and `evidence[]`. Requirements:

- A `BLOCK`ed directive still renders, struck through, with the attack that
  killed it. **Deleting it from the UI destroys the argument** — the fact that
  something was proposed and then vetoed is the most persuasive thing in the
  entire demo.
- `DOWNGRADE` shows the size before and after halving.
- Challenges attach to the directive they attacked, in both `/council` and
  `/terminal`, sourced from the directive's `provenance`.

**3d · Calibration scoreboard.** W5d writes score + recommendation + forward
outcome to the ledger and openly admits six days is not a meaningful sample. The
UI must carry that caveat *in the panel*, not in a doc nobody opens: render the
scoreboard with an explicit "n = 12 assessments — far below significance" header.
Honest small numbers beat impressive fake ones, and a judge who spots the caveat
before you say it out loud stops trusting everything else on screen.

Also fix while you are in here: `app/council/page.tsx` is 19 lines and does no
error handling of its own; it inherits whatever `CouncilBoard` does. Give it the
F1 hooks, a skeleton, an empty state and an error state like every other route.

Acceptance: a persona that revised, one that did not, one above the 0.7 revision
line, a `BLOCK`, a `DOWNGRADE`, and an empty-calibration state all render
correctly.

---

### F4 · Backtest lab — `app/lab/page.tsx`
**Owner:** frontend · **Consumes:** BRIEF-AGENT-V2 W2 · **Status: CONDITIONAL**

**Do not start this until the sweep artefact exists on disk.** W2 is the agent
brief's own largest workstream and is unstarted; a heatmap with no sweep is an
empty page, and per §9 an empty `/lab` is the one contingency this brief calls
demo-unacceptable — you do not walk a judge to a blank route. Check for the
artefact first; if it is absent on D-1, skip F4 entirely and leave `/lab` out of
the nav.

If it does exist, this page is where "is the edge real?" gets answered in ten
seconds, because judges will not read `docs/BACKTEST.md`.

Components under `app/components/lab/`:

| Component | Renders |
|---|---|
| `SweepHeatmap` | take_profit_pct × stop_loss_mult grid, cell colour = Sharpe or total return, selected cell highlighted |
| `EquityCurve` | replay equity vs buy-and-hold baseline for the selected cell |
| `MetricsPanel` | PnL, win rate, avg premium capture, max DD, Sharpe, assignment count |
| `ParamInspector` | the exact config of the selected cell, and whether it is the shipped default |
| `SyntheticDataBanner` | permanent, non-dismissible provenance banner |

Two rules that are not negotiable:

- **The synthetic-chain disclosure is permanent and non-dismissible.** W2 prices
  contracts with Black-Scholes off realised vol because free option history does
  not exist. Every chart on this page carries that banner. An overstated backtest
  is worse than no backtest, and the disclosure is what makes the number
  believable rather than suspicious.
- **If the sweep says the shipped default is not optimal, the UI says so.**
  `ParamInspector` marks the current default cell and the best-performing cell
  separately. When they differ, that is displayed as a finding, not buried.
  Finding your own default wrong and showing it is a stronger demo than a
  suspiciously clean grid.

Empty state matters here more than anywhere: until W2 lands, `/lab` must render
"no sweep artefact found — run `agent/backtest/sweep.py`", never a demo grid.

---

### F5 · Order approval queue + blotter — `app/blotter/page.tsx`
**Owner:** frontend · **Closes:** KNOWN-ISSUES #7

`AgentControl` and `TerminalClient` both call `POST /api/agent/run` and both
render `order_intents`. Nobody can approve one. `OrderIntent` carries
`requires_approval: boolean` and `submitted: boolean` and the UI currently treats
both as decoration.

Build the missing half:

- **Approval queue.** Each intent gets Approve / Reject / Modify-limit. Approving
  calls `POST /api/trade` with the intent's exact fields. Rejecting records a
  reason locally and greys the row.
- **Submit guard.** A confirmation step that restates symbol, side, contracts,
  option symbol and limit price before anything is sent. `POST /api/trade` places
  a real paper order — a mis-click must not be one click away.
- **Blocked while halted.** If the kill switch is halted or the red team `BLOCK`ed
  the directive, the approve button is disabled with the reason inline. The UI
  must never be the path that bypasses a risk control the agent layer enforced.
- **Blotter.** `GET /api/trade/orders` already exists and no page calls it. Render
  submitted orders with status, fills and timestamps, poll while any order is
  open, and reconcile against `order_intents` so an approved intent visibly
  becomes a live order.
- **Resolve the two-button problem.** [`SPEC-F5-BLOTTER.md`](SPEC-F5-BLOTTER.md) §7
  settles KNOWN-ISSUES #7 properly, and better than this brief originally proposed.
  The insight: the two buttons diverged because they were two *runs*. Both now read
  the existing `AgentRunProvider`, so they cannot show different results.
  `/dashboard` `AgentControl` = compact trigger + summary + a `Review N intents →`
  link. `/terminal` `TerminalClient` = detailed read-only view. `/blotter` = the
  only module in the app that calls `POST /api/trade`. **One endpoint, one writer**:
  a grep for `placeTrade` returning more than one call site is a review failure.
  The closing sentence for `FRONTEND.md` is written verbatim in that spec's §7.2.

Acceptance: approve → confirm → order appears in blotter with a real Alpaca paper
order id. Reject → row greyed, no request sent. Halted → approve disabled.

---

### F6 · Get the suites green and keep them green
**Owner:** frontend + QA · **Closes:** KNOWN-ISSUES #10 (partly stale), ROADMAP #2, #6, #14

**This workstream was rewritten after the critique.** The original version ordered
work that is already done. Verified state of the repo as of 29 Aug:

- `frontend/vitest.config.ts` exists — `environment: 'node'`,
  `include: ['tests/**/*.test.ts']`, `@` aliased to `./app`. `npm run test` = `vitest run`.
- **105 unit tests exist**: `tests/api.test.ts` (46), `tests/reasoning.test.ts` (41),
  `tests/utils.test.ts` (6). The old target of "≥ 40 assertions" was passed before
  this brief was written.
- **7 Playwright specs, 20 tests exist** under `frontend/e2e/`, with
  `global-setup.ts` and `helpers.ts`. Three of them — `bug1-api-origin`,
  `bug2-health-endpoint`, `bug3-cold-load-visibility` — are regression tests for
  bugs that `playwright.config.ts:6-18` records as "caught only when a human opened
  the app in a browser". So the claim that nobody has ever looked at this UI is
  **false**, and `KNOWN-ISSUES.md:249` ("Playwright is not installed in any venv")
  is stale — fix that line as part of this workstream.

So the real job is not building a harness. It is this:

**6a · Fix the three failing tests. Highest priority in the entire brief.**

- `tests/reasoning.test.ts:222` and `:229` fail on `main`. They are not bad tests —
  they document a real defect in `lib/reasoning.ts`, which promises in its own
  header comment that "anything it cannot classify is preserved verbatim in `other`
  so no line is ever silently dropped". It does not hold: a `Mr. Market mood:` line
  arriving **before the first group** is consumed by the `RE_MOOD` branch and pushed
  to `current?.raw` — an optional call on `null` — so it lands in neither `preamble`
  nor any group and vanishes. Same for every mood line after the first. Fix
  `lib/reasoning.ts`, not the tests. **If you change an assertion, say so
  explicitly in the commit message** per JOBDESK.
- `e2e/agent-run.spec.ts:15` fails: `TimeoutError` after 30s waiting for the Agent
  status card to render `OK|ERROR|UNKNOWN`. Evidence is committed at
  `frontend/test-results/agent-run-*/error-context.md` with a page snapshot and
  `test-failed-1.png`. Diagnose whether this is a dead backend, a selector that
  no longer matches, or a genuine render failure — then fix the cause.

A red suite makes every other quality claim in this project unverifiable. Nothing
else in F6 starts until these three are green.

**6b · Extend coverage to the new surfaces.** Add tests for whatever F1–F5 land —
`freshness.ts` transitions, the risk formatters' `null` path, the F3 payload type
guard, the F5 `OrderIntent → TradeRequest` mapping. Same suites, same runner. The
existing repo convention (a test that fails against the previous commit) is
already being followed; keep following it.

**6c · Visual evidence.** Screenshot every route at 1440px and 390px into
`docs/frontend-verification/`, committed. This is now known to be achievable —
Playwright already writes PNGs on this box (`test-results/.../test-failed-1.png`),
so the environment walls recorded in KNOWN-ISSUES #10 no longer apply. Also verify
the mobile drawer edge and that the `layoutId` sidebar marker glides rather than
jumps; neither is detectable by any type checker.

Acceptance: `npm run test` and `npm run test:e2e` both green, screenshots committed
for every route at both widths, and `KNOWN-ISSUES.md` #10 rewritten to reflect what
is actually true.

---

## RANKED OPTIONAL

**F7 · Ledger timeline — `app/ledger/page.tsx`.** W1 gives SQLite tables
`cycle_run`, `directive`, `exit_event`, `peak_equity`. Render a reverse-chron
timeline: every cycle, its mood, its halt flag, its directives, expandable to the
full reasoning trace and provenance. This is the answer to "what happened before
now?" and the visible proof that state survives restart. Do this first if time
appears — it is the highest-value optional by a wide margin.

**F8 · Multi-leg strategy rendering.** W4 adds put credit spread, collar and the
wheel state machine. Today's components assume one option leg. A spread needs
both strikes and the width; a collar needs the put and the call and its net
cost/credit; the wheel needs its state (`CASH → SHORT_PUT → ASSIGNED_LONG →
SHORT_CALL → CALLED_AWAY`) drawn as a machine with the current node lit. Without
this, three of five strategies render as a single mystery leg.

**F9 · Command palette + keyboard nav.** `Cmd+K` for route jump, run agent,
symbol search. Cheap, and it makes the demo look operated rather than clicked.

**F10 · Motion bundle mitigation** (KNOWN-ISSUES #10b). framer-motion adds ~34 kB
per route. `LazyMotion` with `domAnimation`, or split `motion/primitives.tsx` so
Reveal-only pages skip the full library.

**F11 · Vol-surface panel.** Consumes W8's IV rank engine: IV percentile per
symbol over a trailing year, with the "don't sell cheap premium" threshold drawn
in. Only build after W8 exists — an IV rank panel fed by a realised-vol proxy
would be a fabricated number wearing a real label.

**F12 · Alert toasts from the stream.** Kill-switch fires, cap breached, red team
`BLOCK`, order filled → transient toast plus a bell dropdown of recent events.
Depends on F1's `stream.ts` being real rather than polling.

---

## Sequencing

| Day | Frontend |
|---|---|
| **D-6** Sat 29 | F6a: fix the 3 failing tests (`lib/reasoning.ts` mood-line drop, `agent-run.spec.ts` status timeout). Then F1 data layer + delete dead Providers stubs |
| **D-5** Sun 30 | F1 finish (all five pages) + the `StrategyConfigCard` raw-fetch fix + tests for `freshness.ts` |
| **D-4** Mon 31 | F2: `KillSwitchPanel` → `GreeksCockpit` → `CapBreachList`, all against fixtures; dashboard risk strip |
| **D-3** Tue 1 | F3 council v2: debate timeline, revision meter, red-team panel — all field-optional against today's payload |
| **D-2** Wed 2 | F5 approval queue + blotter (`/api/trade/orders` already exists — no backend dependency) |
| **D-1** Thu 3 | F6c screenshots, `FRONTEND.md` + `KNOWN-ISSUES.md` reconciliation, F4 only if the sweep artefact actually exists |
| **D0** Fri 4 | Freeze 06:00 UTC. Demo rehearsal only. |

Note what moved: **fixing the red suite is now the first thing on the first day**,
and F4 dropped to conditional. Both changes come from the critique.

Backend and agent dependencies are not on your critical path by design: every
panel above must render a legitimate empty state before its data source exists.
Build the surface, wire it when the payload lands. **A page that cannot render
without live data is a page that will fail on stage** when the market is closed
or the key is rate-limited.

### Measured velocity — read this before you believe the table above

Actual `frontend/**` churn from `git log --numstat`:

| Date | Lines added | Lines removed |
|---|---|---|
| 25 Aug | +11,296 | −51 |
| 26 Aug | +1,101 | −11 |
| 27 Aug | +178 | 0 |
| 28 Aug | +336 | −47 |
| 29 Aug | +2,031 | −1,575 |

The 25 Aug figure is scaffolding, not sustained output. The honest recent baseline
is roughly **300–2,000 lines/day, and the last day was net-negative in places** —
1,575 lines removed while 2,031 landed, which is what a real correction pass looks
like. F1–F6 as specified is four new routes, ~25 components, a data-layer
migration touching all five existing pages, a test harness and an E2E suite.
That is not 300 lines/day work.

Therefore: **F1 and F6a are not cuttable.** F1 because every other workstream
consumes it and a second data-fetching pattern would be worse than none. F6a
because the pure functions in `lib/api.ts` are already load-bearing for five
pages and have never been executed by a test. Everything else is negotiable
against the cut list, and the cut list gets used — plan for it rather than
discovering it on D-1.

---

## 9 · Backend dependency contingency table

Per JOBDESK the frontend must not edit `backend/**`. These are the endpoints F1–F7
need — but read the framing carefully, because it changed after the critique.

**Plan for zero of these shipping.** `docs/BRIEF-BACKEND-V2.md` opens with ten
verified defects, four of them CRITICAL, sitting directly under these asks: **D1**
`get_option_snapshots` cannot parse Alpaca's actual response, **D2**
`_candidate_from_snapshot` reads field names Alpaca does not send, **D4**
`POST /api/trade` has zero coupling to the risk system. **D8 auth is now implemented** — session cookie + CSRF on mutating endpoints (see `backend/app/auth.py`). The backend owner is fixing the remaining defects on the same six-day clock. Treating
this as a request queue with implied delivery is how the frontend ends up with
four empty routes and no time to make them presentable.

So the primary deliverable for every row below is **the empty state**, built
first. The wired version is upside.

| Requested endpoint | Consumer | If it never ships | Demo-acceptable? |
|---|---|---|---|
| `GET /api/risk/greeks` | F2 | `/risk` renders "portfolio Greeks not yet exposed by backend" + the kill-switch panel, which works off existing `/agent/run` data | Yes — the honest empty state is itself a talking point |
| `GET /api/agent/stream` (SSE) | F1, F12 | `stream.ts` degrades to polling and the connection indicator says "polling — stream unavailable" | Yes, if labelled. Never fake events |
| debate rounds on `POST /api/council/assess` | F3 | Today's six-verdict board renders unchanged — **only if every new field is optional** | Yes. This is why field-optionality is F3's top requirement |
| red-team challenges | F3 | No challenge panel. Costs the demo's strongest argument | Painful but survivable |
| `GET /api/backtest/sweep` | F4 | `/lab` has literally nothing. **Cut from the demo path** | No — do not walk a judge to an empty page |
| `GET /api/ledger/cycles`, `/directives` | F7 | No `/ledger`. Already optional | Yes |
| `GET /api/council/calibration` | F3d | No scoreboard | Yes |
| `GET /api/strategy/wheel` | F8 | No wheel machine | Yes |

Shape rule to state in every request: **absent data must be `null`, never `0`,
never omitted-and-defaulted.** The frontend distinguishes "flat" from "unknown"
and cannot do that if the backend collapses them.

One thing the frontend can do unilaterally, today, with no backend cooperation:
`GET /api/trade/orders` already exists at `backend/app/routes/trade.py:114` and is
called by nothing. F5's blotter needs no new endpoint at all.

---

## Definition of done

A workstream is done when all five hold:

1. `npx tsc -p tsconfig.json --noEmit` clean — zero errors, not "only warnings".
2. `npm run build` compiles every route including the new ones.
3. New behaviour has tests that fail against the previous commit.
4. The page was **opened in a real browser**, console checked, screenshot
   committed. Per JOBDESK: `curl` returning 200 is not sufficient.
5. `FRONTEND.md` updated in the same commit — structure table, route list,
   component inventory.

Plus the layer's own standing rule: every new panel has an explicit empty state,
an error state and a loading skeleton. Three states, every panel, no exceptions.
"It looked fine with my data" is how a demo dies on a closed market.

---

## Rules that do not bend

- **Never render a number the backend did not produce.** No interpolation, no
  synthetic series, no filler. `null` renders as `—` with a reason.
- **One app root.** `frontend/app/**` only. No `src/app/`, ever.
- **Tailwind only.** No CSS-in-JS, no new styling system. Extend
  `tailwind.config.js` if a token is missing.
- **Mobile drawer stays a drawer**, `useState`-driven, no bottom nav.
- **Stay in `frontend/**`.** Backend or agent change needed? File it under §9.
- **Browser verification, not `curl`.** Every claim about rendering is backed by
  a screenshot or it is not a claim.
- **No credentials in the client.** `NEXT_PUBLIC_*` is public by definition;
  nothing secret goes near it. Verify before every push:
  ```bash
  grep -rInE "PK[A-Z0-9]{15,}|sk-[a-zA-Z0-9]{20,}" frontend \
    --exclude-dir=node_modules --exclude-dir=.next
  ```
- **Kill-switch authority is absolute.** If the agent layer says halted, no UI
  path submits an order. The frontend is never the bypass. And state it plainly in
  the panel: a disabled button is a UX affordance, not a security control — per
  backend defect D4, `POST /api/trade` has zero risk coupling, so the real gate
  belongs in backend B2/B3 and the UI must not imply otherwise.
- **Fixtures never reach app code.** Panels for unbuilt endpoints must be
  developed against fixtures, so the boundary needs enforcement, not discipline:
  fixtures live under `frontend/tests/fixtures/` only (the convention
  `tests/fixtures/realTrace.ts` already established), and nothing under `app/` or
  `lib/` may import from that directory. Add the grep to the pre-push checklist:
  ```bash
  grep -rn "tests/fixtures" frontend/app frontend/lib && echo "FIXTURE LEAK" && exit 1
  ```
  This is the same class of mistake as shipping a mock that looks real — the
  existing `app/data/mock_portfolio.json` is safe only because it is explicitly
  labelled at every render site.

---

## What this buys us with judges

| Question | Answer after this brief |
|---|---|
| "Is it actually running?" | Live polling + per-panel freshness, ticking blotter. **Say "polling" not "streaming"** unless `/api/agent/stream` actually shipped |
| "What is your risk right now?" | `/risk` cockpit: net Δ/Θ/V/Γ, beta-weighted delta, cap breaches — or an honest "backend does not expose this yet" |
| "Did anything push back on that trade?" | Red-team panel: the `BLOCK`ed directive still on screen with the attack that killed it |
| "Is the committee independent or just agreeable?" | Revision-rate meter with the 0.7 capitulation line drawn in |
| "Does the edge exist?" | `/lab` sweep heatmap + equity curve, synthetic-chain disclosure permanent — **only if W2 shipped**; otherwise do not raise the topic |
| "Can I stop it?" | Approval queue, submit guard, halt disables every submit path — and the panel says out loud that the real gate belongs server-side (D4) |
| "What did it do yesterday?" | Ledger timeline (F7) — proof state survived restart |
| "Has anyone checked this works?" | 105 unit + 20 E2E tests, three of them regressions for bugs found in a real browser, plus committed screenshots at two widths — **green, or do not claim it** |

The last row is the one most likely to be checked live, which is exactly why F6a
comes first. As of this brief's writing three of those tests fail; claiming
verification while the suite is red is the fastest way to lose a judge's trust in
every other row.

Note what the strongest four rows have in common — risk cockpit, red-team panel,
revision-rate meter, calibration scoreboard are each *an honest presentation of a
limitation* rather than a claim of capability. Every other team will demo a UI and
hope it renders. Ours will show the instrument that would catch it being wrong,
and say out loud where the instrument's own numbers stop.

