# BRIEF-FRONTEND-V2 — CRITIQUE

**Reviewer:** Orchestrator / CTO · **Date:** 29 Aug 2026
**Subject:** [`BRIEF-FRONTEND-V2.md`](BRIEF-FRONTEND-V2.md)
**Method:** every factual claim in the brief re-checked against the working tree.
Verdicts are CONFIRMED / **FALSE** / UNVERIFIED with the command or file:line that
settled it. No claim in this document is asserted without evidence.

---

## 0 · Verdict

The brief is built on one premise that was true a week ago and is false today:
that the frontend has no tests and has never been opened in a browser. Vitest and
Playwright are both installed, 105 unit tests and 20 E2E assertions exist, and
three of the E2E specs are *regression tests for bugs a human found by opening the
app*. F6 as written orders work that is already done, while missing the two things
that are actually broken right now: **2 unit tests fail on `main`** and **one
Playwright spec fails**.

Second finding, worse for planning: the brief requests 8 new backend endpoints
from a teammate whose own brief opens with 10 verified defects, 4 of them
CRITICAL, in the code paths those endpoints would be built on. Frontend has been
sequenced as if backend has spare capacity. It does not.

Severity-ordered findings below. F1's premises survive scrutiny; F6's do not.

---

## 1 · False or unverified premises

| # | Claim in brief | Status | Evidence |
|---|---|---|---|
| 1 | "Add Vitest" (F6a) — implies no unit runner exists | **FALSE** | `frontend/vitest.config.ts` exists (environment `node`, `include: ['tests/**/*.test.ts']`, `@` → `./app`); `package.json` script `"test": "vitest run"`; `vitest ^4.1.11` in devDependencies |
| 2 | "Tests: 0 frontend tests" (§1 end-state table) | **FALSE** | `tests/api.test.ts` 46 cases, `tests/reasoning.test.ts` 41, `tests/utils.test.ts` 6 — **105 tests total**, verified by running `npx vitest run` |
| 3 | "Target ≥ 40 assertions" (F6a) | **FALSE as a target** | Already at 105. The brief sets a goal the repo passed before the brief was written |
| 4 | "nobody has ever opened this UI in a browser" (F6) | **FALSE** | `e2e/bug1-api-origin.spec.ts`, `bug2-health-endpoint.spec.ts`, `bug3-cold-load-visibility.spec.ts` — `playwright.config.ts:6-18` states all three "shipped past `tsc --noEmit` AND `next build` and were caught only when a human opened the app in a browser" |
| 5 | "one Playwright spec" needed (F6b) | **FALSE** | 7 spec files exist: navigation (5 tests), console-hygiene (3), agent-run (2), bug1 (4), bug2 (3), bug3 (3) — 20 tests, plus `e2e/global-setup.ts` and `e2e/helpers.ts` |
| 6 | `npm run test` green is the acceptance bar (F6) | **FALSE at baseline** | `npx vitest run` → **`Tests 2 failed | 103 passed`**, both in `tests/reasoning.test.ts:222` and `:229`, deliberately documenting a live defect in `lib/reasoning.ts` |
| 7 | E2E suite passes | **FALSE at baseline** | `frontend/test-results/agent-run-.../error-context.md`: `agent-run.spec.ts:15` `TimeoutError: locator.waitFor: Timeout 30000ms exceeded` waiting for Agent status to render `OK|ERROR|UNKNOWN` |
| 8 | `@tanstack/react-query` is unused | CONFIRMED | `grep -rn "QueryClient\|useQuery\|useMutation" app lib` → zero matches |
| 9 | Four per-route `Providers.tsx` are dead | CONFIRMED | `app/{assets,dashboard,settings,terminal}/Providers.tsx` each export a passthrough; only `app/layout.tsx:2` imports `@/components/Providers` |
| 10 | `GET /api/trade/orders` exists and is uncalled | CONFIRMED | `backend/app/routes/trade.py:114`; `grep -rn "trade/orders\|getOrders" app lib` → zero matches |
| 11 | `lib/api.ts` holds the only `fetch()` | **FALSE** (already corrected in brief) | `app/components/StrategyConfigCard.tsx:43` and `:69` — the second is a mutating write with no timeout |
| 12 | KNOWN-ISSUES #7 / #10 / #10b / #13 numbering | CONFIRMED | lines 185, 243, 271, 320 of `docs/KNOWN-ISSUES.md` — but see finding 13 |
| 13 | KNOWN-ISSUES #10 text is current | **STALE** | `KNOWN-ISSUES.md:249` still reads "Playwright is not installed in any venv". `@playwright/test ^1.62.1` is in devDependencies and 7 specs exist. The issue was partly fixed and never updated |

**Why this matters more than a documentation nit.** Findings 1–7 mean F6 as
written spends D-1 building a test harness that exists, against a target already
exceeded, while the two genuinely red signals on `main` — 2 failing unit tests and
1 failing E2E — are not mentioned anywhere in the brief. A workstream that orders
completed work and omits the actual breakage is worse than no workstream: it
consumes the day *and* leaves the repo red.

---

## 2 · Scope realism

Measured `frontend/**` churn (`git log --numstat`, 25–29 Aug):

| Date | + | − | Reading |
|---|---|---|---|
| 25 Aug | 11,296 | 51 | initial scaffold — not repeatable output |
| 26 Aug | 1,101 | 11 | components landing |
| 27 Aug | 178 | 0 | a quiet day |
| 28 Aug | 336 | 47 | a quiet day |
| 29 Aug | 2,031 | 1,575 | correction pass — half of it deletion |

Two of the last three days produced **under 400 lines**. The brief's mandatory
scope is four new routes, ~25 components, a data-layer migration touching all
five existing pages, plus F6. Against a 300–2,000 line/day baseline where the
recent trend includes heavy deletion, F1–F6 is **not deliverable in six days**,
and the sequencing table that assigns one workstream per day is fiction dressed
as a plan.

What the table also ignores: D-6 is already gone. This critique is being written
on 29 Aug, the day the table assigns to F1. Nothing in F1 exists.

**Cut recommendation, in order:**

1. **F6b/F6c as specified → replace with "fix the 3 failing tests".** The harness
   is built; the suites are red. Turning them green is a half-day and it is the
   only version of F6 that changes the repo's actual state. Keep the screenshot
   requirement, drop the "build an E2E suite" framing entirely.
2. **F4 (backtest lab) → cut to a static artefact viewer or drop.** It depends on
   agent W2, which is itself the largest item in the agent brief and not started.
   A sweep heatmap with no sweep is an empty page in the demo path.
3. **F2 ExposureMatrix + ThetaLadder → cut, keep GreeksCockpit + CapBreachList.**
   The four numbers and the breach list answer the judge's question; a sortable
   per-symbol matrix is polish on data that may arrive as `null` anyway.

Not cuttable, and the brief is right about this: **F1**, because every other
workstream consumes it and a second fetching pattern is worse than none.

---

## 3 · Dependency deadlocks

The brief's §9 requests 8 endpoints. What it does not say is what those endpoints
are being built on top of. `docs/BRIEF-BACKEND-V2.md` opens with 10 verified
defects, and the CRITICAL ones sit directly under the frontend's asks:

- **D1** `get_option_snapshots` "cannot parse Alpaca's actual response" — CRITICAL
- **D2** `_candidate_from_snapshot` "reads field names Alpaca does not send" — CRITICAL
- **D4** `POST /api/trade` "has zero coupling to the risk system" — CRITICAL
- **D5** blocking I/O inside `async def` serialises the whole process — HIGH
- **D8** no auth, no logging, no correlation IDs, no rate limiting — HIGH

Consequences the frontend brief does not acknowledge:

| Deadlock | Mechanism | What frontend actually has |
|---|---|---|
| F2 ↔ W3 ↔ D1/D2 | `/api/risk/greeks` needs portfolio Greeks (W3, unbuilt) which need option snapshots parsed correctly (D1/D2, CRITICAL broken) | `/risk` renders its empty state. Acceptable — but only if the empty state is built first |
| F5 ↔ D4 | The approval UI's entire value is that nothing submits unreviewed. D4 says the endpoint will submit anything it is given | A disabled button is a UX affordance, not a control. F5 must say so in the panel, or it is theatre |
| F4 ↔ W2 | Sweep artefact does not exist; W2 is the agent brief's own largest item | Empty page. Cut from demo path |
| F3 ↔ W5 | Debate/red-team/calibration fields do not exist in any payload | Today's six-verdict board still renders — **if and only if** every new field is optional. That is the single most important requirement in F3 |
| F7 ↔ W1 | Ledger tables unbuilt | No `/ledger`. Already optional, correctly ranked |
| All 8 endpoints ↔ one person | Backend owner is simultaneously fixing 4 CRITICAL defects on a 6-day clock | Assume **zero** new endpoints ship. Every panel must be demo-able without them |

The planning error is structural: the brief treats §9 as a request queue with
implied delivery. It should be treated as **a list of things that will not exist
on demo day**, with the empty states as the primary deliverable and the wired
version as the upside.

---

## 4 · Internal contradictions and unfalsifiable requirements

**4.1 · ThetaLadder vs the layer's founding rule.** F2 lists
`ThetaLadder` — "daily theta decay over the next 30 sessions from open positions"
— while the same section demands "never render a number the backend did not
produce" and W3 exposes `net_theta` as a single scalar `$/day`. Thirty forward
sessions from one scalar is a client-side model: it assumes theta is constant,
that no position closes, and that no expiry lands inside the window. All three
assumptions are false in an options overlay by construction. Either label it a
projection with those assumptions printed on the panel, or cut it. The brief does
neither, which makes it the one panel guaranteed to violate the rule it sits under.

> **Resolved, against this reviewer's recommendation.**
> [`SPEC-F2-RISK-COCKPIT.md`](SPEC-F2-RISK-COCKPIT.md) §4 chose *keep, labelled as
> a projection*, and the argument holds: the founding rule forbids presenting an
> unproduced number **as a reading**, not stating a model — and this project
> already ships W2's synthetic chains labelled rather than suppressed. The panel is
> now bound to requirement R8: persistent `PROJECTION — NOT BACKEND DATA` badge
> (not a tooltip), four assumptions printed verbatim, `#fbbf24` series so it cannot
> be mistaken for a measured panel, unknown-card when `net_theta` is `null`. The
> contradiction is closed either way; what mattered was that the brief pick one,
> and it now has.

**4.2 · "No fabricated data" vs building panels before endpoints exist.** F2 and
F4 must be built against payloads that do not exist. Fixtures are unavoidable;
the brief never says where they live or what stops one being imported by app code.
Without a stated enforcement mechanism this is the exact failure mode that put
`app/data/mock_portfolio.json` into the shipped bundle — a mock that is *correctly*
labelled today, but only because someone remembered. Requirement needed:
fixtures under `frontend/tests/fixtures/` only, plus a grep gate in the pre-push
checklist. The `tests/fixtures/realTrace.ts` file already establishes the
convention; the brief should have cited it.

**4.3 · F6 orders a harness that exists.** Covered in §1. The contradiction is
that the brief's own "Definition of done" requires "new behaviour has tests that
fail against the previous commit" — a rule the repo already follows
(`tests/reasoning.test.ts:222` and `:229` are literally two failing tests
documenting a real defect, exactly as the rule prescribes). The brief did not
notice its own standard being met.

**4.4 · "Screenshots for nine routes" vs the documented environment.** The brief
demands committed screenshots while `KNOWN-ISSUES.md:248-250` documents that every
headless attempt failed. But #10 is itself stale (finding 13) — Playwright now
runs and produced `test-results/.../test-failed-1.png`, so screenshot capture
demonstrably works on this box. The requirement is achievable; the brief cites a
blocker that no longer applies and misses that the tooling is already proven.

**4.5 · Freshness dot on "every data panel" is unfalsifiable as written.** No
definition of "data panel" is given, so nobody can say when F1 is done. Needs an
enumerated list of components.

---

## 5 · Weakest demo claims

Of the 8 rows in "What this buys us with judges", four collapse under one
follow-up:

| Row | The follow-up that breaks it |
|---|---|
| "Is it actually running?" — *live polling + event stream* | "Is that stream real?" `/api/agent/stream` does not exist and is behind a backend fighting 4 CRITICAL defects. Honest answer: polling, degraded, labelled. Say that first and the row survives; claim SSE and it does not |
| "Does the edge exist?" — *`/lab` sweep heatmap* | "Where did the option prices come from?" Synthetic Black-Scholes off realised vol. The brief handles this well *if* the banner ships — but the whole row is contingent on W2, which is unstarted |
| "Can I stop it?" — *approval queue, halt disables submit* | "What stops a POST to `/api/trade` directly?" Nothing. D4 and D8: no risk coupling, no auth. The UI guard is real but it is not the control, and a judge who knows the stack will ask |
| "Has anyone checked this works?" — *screenshots, E2E, reduced-motion* | "Is the suite green?" No — 2 unit + 1 E2E failing right now. This is the row most likely to be checked live and it is the one the brief is most confident about |

The rows that hold: risk cockpit (once `null` handling is right), red-team panel,
revision-rate meter, ledger timeline. Those four are the demo. Note what they have
in common — each is *an honest presentation of a limitation* rather than a claim
of capability. That is the differentiator worth protecting.

---

## 6 · The three changes that would most improve the brief

1. **Rewrite F6 from "build a test harness" to "get the existing suites green and
   keep them green."** Concretely: fix `tests/reasoning.test.ts:222`/`:229` (a real
   defect in `lib/reasoning.ts` where a pre-group mood line is swallowed by
   `current?.raw` and lands in neither `preamble` nor any group), fix the
   `agent-run.spec.ts:15` Agent-status timeout, then add coverage for new panels.
   *Justification: the brief currently spends its most expensive day rebuilding
   what exists while the repo sits red.*

2. **Invert §9 from a request queue into a contingency table.** For each of the 8
   endpoints state the empty state, whether that state is demo-acceptable, and
   which panels get cut if it never ships — then build the empty states first.
   *Justification: backend has 4 CRITICAL defects on the same six-day clock;
   planning for delivery is planning to be blocked.*

3. **Resolve ThetaLadder and state the fixture enforcement mechanism.** Pick
   projection-with-assumptions or cut, and write the `frontend/tests/fixtures/`
   + grep-gate rule into the brief's non-negotiable rules list.
   *Justification: these are the only two places where the brief's own founding
   rule — never render a number the backend did not produce — can be violated by
   an engineer following the brief correctly.*

