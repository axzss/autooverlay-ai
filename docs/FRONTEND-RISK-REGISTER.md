# FRONTEND-RISK-REGISTER

**Scope:** delivery + demo risk for [`BRIEF-FRONTEND-V2.md`](BRIEF-FRONTEND-V2.md).
**Companion:** [`BRIEF-FRONTEND-V2-CRITIQUE.md`](BRIEF-FRONTEND-V2-CRITIQUE.md) —
every finding there that changed the plan is reflected here. Implementation specs:
[F1](SPEC-F1-LIVE-DATA.md) · [F2](SPEC-F2-RISK-COCKPIT.md) ·
[F3](SPEC-F3-COUNCIL-V2.md) · [F5](SPEC-F5-BLOTTER.md).
**Window:** D-6 (29 Aug) → D0 (4 Sep, 15:00 UTC). Freeze 06:00 UTC on D0.

Two kinds of failure are tracked. **Delivery risk**: the work does not land.
**Demo risk**: the work landed and still breaks on stage. The second is worse — a
missing panel is a scoping decision, a panel that throws in front of a judge is a
credibility event.

---

## 1 · Risk register

Likelihood / Impact: H / M / L. Owner is per [`JOBDESK.md`](JOBDESK.md).

| ID | Risk | Cat | L | I | Early warning | Mitigation | Fallback if mitigation fails | Owner |
|---|---|---|---|---|---|---|---|---|
| R1 | **3 tests already red on `main`**: `tests/reasoning.test.ts:222` + `:229` (pre-group `Mr. Market mood:` line swallowed by `current?.raw` in `lib/reasoning.ts`), `e2e/agent-run.spec.ts:15` (30s timeout on Agent status) | quality | **certain** | H | It is already true — `npx vitest run` → 2 failed / 103 passed | F6a is the first task on D-6, before any new code | Do not claim verification anywhere in the demo; state the known defect out loud | frontend |
| R2 | Judge runs `npm run test` or asks "is the suite green?" while R1 is unfixed | demo | M | H | R1 open past D-5 | Fix R1 | Answer honestly and show the failing test *documents* a real defect — that is a defensible position, a hidden red suite is not | frontend |
| R3 | F2 `/risk` blocked: agent W3 `PortfolioGreeks` unbuilt and `GET /api/risk/greeks` does not exist | integration | H | H | No `agent/greeks.py` on disk by D-3 | Build every panel against `tests/fixtures/`; `KillSwitchPanel` first because it works off existing `/agent/run` data | `/risk` ships with "portfolio Greeks not yet exposed by backend" + working kill-switch panel | frontend |
| R4 | W3 itself blocked by backend D1/D2 (`get_option_snapshots` cannot parse Alpaca's response; `_candidate_from_snapshot` reads fields Alpaca does not send — both CRITICAL in `BRIEF-BACKEND-V2.md`) | integration | H | H | Greeks arrive all-`null` even after W3 lands | `null`-first rendering everywhere; a fully-`null` cockpit must look deliberate | Present the all-`null` state as the honest answer: "the instrument exists, the feed is broken, and it says so" | backend + AI |
| R5 | Zero of the 8 requested endpoints ship — backend owner is fixing 4 CRITICAL defects on the same clock | integration | H | H | No new routes in `backend/app/routes/` by D-3 | §9 rewritten as a contingency table; empty states are the primary deliverable | Demo path = `/dashboard`, `/council`, `/terminal`, `/blotter` only | orchestrator |
| R6 | F5 approval UI implies a safety guarantee the stack does not provide — D4: `POST /api/trade` has **zero** risk coupling | security | H | H | Anyone describes the disabled button as "the safety control" | Panel copy states plainly that this is a UX affordance and the real gate belongs in backend B2/B3 | Never demo the halt-blocks-submit claim without that sentence | frontend |
|| R7 | **Backend fully unauthenticated (D8)** and has been exposed via public Cloudflare quick tunnels during development | security | **L** | H | Any tunnel pointing at :8000 | **MITIGATED**: Auth implemented — session cookie + CSRF on mutating endpoints (`backend/app/auth.py`). Only `/api/portfolio`, `/api/strategy/config`, `/api/council/assess`, `/api/agent/run` are public | Kill the tunnel. A public unauthenticated `POST /api/trade` is the single worst outcome in this project | backend |
| R8 | react-query migration regresses the hard-won request semantics in `lib/api.ts:112-144`: the 30s-vs-8s timeout split and the AbortError-vs-unreachable distinction | quality | M | H | "unreachable" appearing where a slow agent run is the real cause | F1 preserved-behaviour checklist; keep `request()` as the query fn rather than replacing it | Revert F1's `hooks.ts` and keep the old hook; a working slow path beats a fast broken one | frontend |
| R9 | New polling hits Alpaca rate limits — `/strategy/screen` fans out per symbol and takes ~2s | integration | M | M | 429s in backend logs; screen latency climbing | Per-cost interval table; `refetchIntervalInBackground: false`; `visibilitychange` guard | Raise intervals to on-demand only; a manual refresh button is not a demo failure | frontend |
| R10 | `usePortfolio`'s mock fallback (`lib/api.ts:422`, `455-464`) masks a dead backend during the demo | demo | M | H | Plausible numbers on screen with the backend down | Fallback banner already exists at `dashboard/page.tsx:100-104` — never remove it, and extend the same treatment to every new panel | Pre-demo check: kill the backend once and confirm the banner appears | frontend |
| R11 | `StrategyConfigCard.tsx:43` and `:69` call `fetch()` raw — the second is a **mutating write with no timeout** to live strategy config | quality | H | M | Settings page hangs with no error | Migrate both to the typed client in F1; add `getStrategyConfig`/`updateStrategyConfig` | Disable the settings write path for the demo rather than demo a hang | frontend |
| R12 | `FRONTEND.md` claims `lib/api.ts` is the only `fetch()` site — false, per R11 | quality | **certain** | L | It is already true | Correct the doc in the same commit as R11 | — | frontend |
| R13 | `KNOWN-ISSUES.md:249` is stale: "Playwright is not installed in any venv" while `@playwright/test ^1.62.1` and 7 specs exist | quality | **certain** | M | It is already true | Rewrite #10 in F6 | A stale issues doc causes double work and wrong planning — this register exists partly because of it | frontend |
| R14 | Four new routes (`/risk`, `/lab`, `/blotter`, `/ledger`) appear in the sidebar while still half-built | demo | M | H | A nav link leading to a skeleton | Nav visibility gate: a route is linked only when its empty state is complete | Remove the link, keep the route reachable by URL for development | frontend |
| R15 | `/lab` demoed with no sweep artefact — the one contingency the brief calls demo-unacceptable | demo | M | H | No W2 output on disk by D-1 | F4 marked CONDITIONAL; check for the artefact before starting | Drop `/lab` from nav and from the script entirely | frontend |
| R16 | F3 breaks against today's payload because debate/red-team fields were typed as required | integration | M | H | `/council` blank or throwing after the F3 commit | Every new field optional + a type guard deciding whether debate data exists; test against the current 6-verdict payload | Revert F3 — the existing board is presentable on its own | frontend |
| R17 | Fixtures leak into shipped app code while building panels for unbuilt endpoints | quality | M | H | Any `tests/fixtures` import under `app/` or `lib/` | Grep gate in the pre-push checklist: `grep -rn "tests/fixtures" frontend/app frontend/lib` must return nothing | Rip the import out and re-verify; a fabricated number that reaches a judge is unrecoverable | frontend |
| R18 | Scope overrun: two of the last three days produced <400 lines in `frontend/**`; mandatory scope is 4 routes + ~25 components + a migration | delivery | H | H | F1 not complete by end of D-5 | Cut list in §6, applied on schedule rather than discovered on D-1 | Minimum viable demo path (§6) | orchestrator |
| R19 | Market closed / empty positions on Fri 4 Sep → every panel legitimately empty | demo | M | M | Weekend or holiday; `/api/portfolio` returns no positions | Every panel has a designed empty state; rehearse against an empty account | Present the empty states deliberately as the honest-degradation story | frontend |
| R20 | framer-motion adds ~34 kB per route (KNOWN-ISSUES #10b) across 9 routes on demo wifi | demo | L | M | First-load JS climbing past ~260 kB | F10 `LazyMotion` if time permits | Demo on localhost, not over the tunnel | frontend |
| R21 | Commit includes unreported files — this repo has already had a batch reverted and force-pushed out of history for exactly this | quality | M | H | `git status` showing files nobody mentioned | Read the full diff and enumerate **every** changed file before committing. Never commit from a summary | Revert immediately and re-verify from a fresh clone | orchestrator |
| R22 | Cloudflare tunnel NXDOMAINs or hangs (QUIC blocked on this VPS; needs `--protocol http2`) | demo | M | M | Tunnel URL not resolving from outside | Demo from localhost by default; tunnel is a backup, not the plan | Screenshots + local demo | orchestrator |
| R23 | `ScoreGauge` reused on `/risk`: `charts/ScoreGauge.tsx:26` clamps a non-finite score **to 0**, so a `null` greek would render `0.0` — the exact failure the page exists to prevent | quality | M | H | Any `/risk` component importing `ScoreGauge` | SPEC-F2 §2 rejects it; build the `CapGauge` sibling. Test #4 asserts a `null` greek never renders 0 | Revert the panel rather than ship a gauge that fabricates flatness | frontend |
| R24 | Double-submit / duplicate paper order on `/blotter` | security | M | H | Two orders with the same symbol seconds apart | Synchronous module-scope lock (React state settles too late for a double-click) + `client_order_id` — **already accepted at `trade.py:29`, forwarded at `:77-78`, and Alpaca rejects duplicates**, so no backend change is needed | Disable the approve path for the demo | frontend |
|| R25 | `_pick_option_contract` (added at `agent.py:19`, fix (a) for KNOWN-ISSUES #2) changes `option_symbol` from always-null to sometimes-resolved mid-sprint | integration | M | M | Intents suddenly carrying real OCC symbols | Key every UI rule on the null *value*, never on the issue's status — SPEC-F5 §3.3 already does this | None needed if the rule is followed; a UI that assumed null breaks silently if it is not | frontend ||
|| R26 | Auth implementation introduces new failure modes: session expiry mid-demo, CSRF mismatch on rapid clicks, login page not rendering on mobile | demo | M | H | Login loop, 419/403 on protected routes | 24h TTL covers demo window; CSRF auto-refreshed via `/auth/csrf`; login page tested at 375px width | Manual refresh + relogin flow rehearsed; `/dashboard` accessible without auth | frontend ||
|| R27 | Unauthenticated judge clicks protected nav link → redirect to `/login` with no context of what they tried to reach | demo | M | M | Judge lands on `/login` confused | `AuthProvider` stores `nextPath` and redirects back after login | `/dashboard` always works; judge can always reach the portfolio view | frontend ||

---

## 2 · Dependency contingency matrix

The brief's §9 carries the short version. This is the operative one: for each
requested endpoint, what the panel shows if it never arrives, and whether that
state can be walked past a judge.

| Endpoint | Panel | If it never ships | Demo-acceptable |
|---|---|---|---|
| `GET /api/risk/greeks` | F2 cockpit | "Portfolio Greeks are not yet exposed by the backend." `KillSwitchPanel` still renders from `/agent/run` | **Yes.** The empty state is a talking point: the instrument is built, the feed is not wired |
| `GET /api/agent/stream` | F1 freshness, F12 toasts | Polling, with the indicator reading "polling — stream unavailable" | **Yes**, if labelled. Fabricated events on a timer would be a disqualifying lie |
| debate fields on `POST /api/council/assess` | F3 timeline, revision meter | Today's six-verdict board, unchanged | **Yes** — conditional on R16's field-optionality holding |
| red-team challenges | F3 `RedTeamPanel` | Panel absent | **Yes**, but it costs the strongest single argument in the demo. Prioritise this ask above the others |
| `GET /api/backtest/sweep` | F4 `/lab` | Nothing. There is no honest empty state for "here is our evidence of edge" | **No.** Cut the route from nav and from the script |
| `GET /api/ledger/cycles` + `/directives` | F7 `/ledger` | Route not built | **Yes** — already ranked optional |
| `GET /api/council/calibration` | F3d scoreboard | Panel absent | **Yes** |
| `GET /api/strategy/wheel` | F8 | Wheel machine absent | **Yes** |

Needs no backend cooperation at all: `GET /api/trade/orders` already exists at
`backend/app/routes/trade.py:114` and is called by nothing. **F5's blotter is the
only new route with zero integration risk** — which is why it sits on D-2 rather
than being cut.

---

## 3 · Demo-day failure playbook

Friday 4 Sep. US markets may be closed, the paper account may be rate-limited, and
the backend is one process on one box. Every row below must be **rehearsed**, not
imagined — trigger each failure once before demo day and confirm the UI does what
this table says.

The governing statement: **a UI that cannot render without live data will fail on
stage.** Every panel renders from an empty state up, never from data down.

| Failure | Pre-verified UI state | Presenter's line |
|---|---|---|
| Backend down | Fallback banner on `/dashboard` ("Backend unreachable — showing sample data"), freshness dots red everywhere | "The backend is down and the UI is telling you so — that banner is the point. Nothing on this screen is claiming to be live." |
| Alpaca 401 | `/api/portfolio` errors; panels show error state, not zeros | "Credentials are rejected right now. Note it says unreachable, not $0.00 — we never render a number the backend did not produce." |
| Alpaca 429 | Slow panels, freshness amber, no crash | "We're rate-limited. The intervals are per-endpoint and back off; the stale marker is honest about the age of what you see." |
| Empty positions | Every holdings panel shows its designed empty state | "No open positions today — this is the empty state, not a loading bug." |
| Kill switch halted | Full-width HALT banner with reasons; every submit affordance disabled | "The agent halted itself and gave its reasons. Every submit path in the app is disabled while that holds — and the server-side gate is backend B2's job, not this button's." |
| No sweep artefact | `/lab` not in nav | Do not raise the backtest. If asked: "The harness is specified and unbuilt — we're not going to show you a heatmap of synthetic numbers we haven't run." |
| SSE unavailable | Indicator reads "polling — stream unavailable" | "This is polling, not streaming. The stream endpoint isn't built; we won't dress polling up as something it isn't." |
| Slow / dead tunnel | Demo from localhost | — (do not demo over the tunnel by default; it is the backup) |

One rule that overrides the table: **if a panel throws, close the tab and move
on.** Never debug live. The screenshots in `docs/frontend-verification/` are the
fallback artefact, which is the other reason F6c is mandatory.

---

## 4 · Rollback and blast radius

`main` must be demo-able at every commit. Not "mostly working" — demo-able, because
the demo may happen from whatever is on `main` when the clock runs out.

**Nav visibility is the feature flag.** A new route exists on disk from its first
commit but is linked from `Sidebar.tsx` / `MobileSidebar.tsx` only when its empty
state is complete. A half-built page reachable only by typing the URL costs
nothing; the same page linked in the sidebar is a live landmine. This is the
cheapest risk control in the whole register — use it for `/risk`, `/lab`,
`/blotter`, `/ledger`.

Per-workstream revert plan:

| Workstream | If it destabilises | Blast radius |
|---|---|---|
| F1 | Revert `lib/live/` and the page migrations; the re-export shim means old call sites still work | **Widest in the brief** — touches all five existing pages. Migrate one page per commit, never all five in one |
| F2 | Unlink `/risk` from nav; leave the route | Self-contained, plus the dashboard risk strip — keep that in its own commit so it reverts alone |
| F3 | Revert `CouncilBoard` extraction | `/council` only, but the refactor doubles a 265-line file. Extract child components in separate commits so a bad one reverts without the rest |
| F4 | Unlink `/lab` | Self-contained |
| F5 | Unlink `/blotter`, restore the read-only intent list | `/blotter` + `AgentControl` + `TerminalClient` if #7's split is implemented at the same time — do the split in its own commit |
| F6 | Never reverted. Tests do not destabilise anything | — |

Pre-push checklist, every push, no exceptions:

```bash
cd frontend
npx tsc -p tsconfig.json --noEmit          # zero errors
npm run build                              # every route compiles
npm run test                               # vitest green
grep -rn "tests/fixtures" app lib          # must return NOTHING (R17)
grep -rInE "PK[A-Z0-9]{15,}|sk-[a-zA-Z0-9]{20,}" . \
  --exclude-dir=node_modules --exclude-dir=.next
cd .. && git status --short                # read EVERY line
git diff --stat                            # then read the actual diff
```

**The last two lines are a rule, not advice.** This repo has already had a batch of
work reverted and force-pushed out of history because files were committed that
nobody had reported — the commit was assembled from a summary instead of a diff.
Report every changed file by name before committing, including the ones you did
not expect to be there.

---

## 5 · Quality gates that cannot be waived

Each of these exists because of something that actually went wrong here, or
something a judge will see.

| Gate | The failure it prevents |
|---|---|
| **Three states per panel** (loading / empty / error) | `/council` is 19 lines with no error handling of its own; it inherits whatever `CouncilBoard` does. On a closed market or a dead backend that is a blank page in the demo |
| **`null` renders as `—`, never `0`** | W3 returns `None` for unknown greeks precisely because "zero is a claim of flatness". The trap is already in the tree: `charts/ScoreGauge.tsx:26` clamps non-finite input to `0`, so reusing it on `/risk` would render an unknown vega as `0.0` and tell a judge the book is flat when the system does not know. Single most damaging possible bug on that page |
| **No fabricated data, fixtures never in app code** | Three bugs already shipped past `tsc` + `next build` and were caught only in a browser (`playwright.config.ts:6-18`). A fixture that looks real would not be caught by any of those gates |
| **Kill-switch authority absolute** | D4: `POST /api/trade` has zero risk coupling. If the UI is the only thing standing between an agent halt and a live order, and it also *claims* to be a safety control, we have shipped a false assurance |
| **One writer per mutating endpoint** | `POST /api/trade` is called from exactly one module (`lib/blotter/submit.ts`). A grep for `placeTrade` returning two call sites is a review failure — that is how two divergent submit paths appear, which is KNOWN-ISSUES #7 repeating itself with real money attached |
| **Browser verification with screenshots, not `curl` 200** | All three historical bugs returned HTTP 200 while the page was broken — one shipped `/dashboard` at `opacity: 0`. A status code proves the server answered, nothing more |
| **Fallback data is always labelled** | `usePortfolio` falls back to `mock_portfolio.json` when the backend is unreachable. Unlabelled, that is plausible fake numbers in a demo; the banner at `dashboard/page.tsx:100-104` is what makes it honest |

---

## 6 · Cut list, ranked

Applied on schedule, not discovered on D-1. If F1–F6 are not done when D-2
arrives, drop in this order:

| # | Cut | Demo cost |
|---|---|---|
| 1 | F4 `/lab` entirely | Lose the "is the edge real?" answer. Already conditional on W2, which is unstarted — this cut is likely free |
| 2 | F2 `ExposureMatrix` | Lose per-symbol greek detail. Cockpit + breach list still answer the risk question |
| 3 | F3d `CalibrationScoreboard` | Lose "how do you know the committee is any good?" Keep the debate timeline and revision meter — they carry the same argument |
| 4 | F1 `stream.ts` | Lose nothing visible: polling was the honest answer anyway |
| 5 | F3 `DebateTimeline` | Lose round-2 revisions. Red-team panel alone still shows the trade was challenged |
| 6 | F2 `BetaWeightedDelta` | Lose SPY-normalised exposure. Four raw greeks remain |
| 7 | F5 blotter view (keep the approval queue) | Lose fill tracking. Approval + guard is the safety story; the blotter is the receipt |

Never cut: **F6a** (a red suite invalidates every other claim), **F1 core**
(everything consumes it), **F5 approval queue** (it is the product's headline
safety property), **F2 `KillSwitchPanel`** (needs no new endpoint and answers "can
I stop it?").

### Minimum viable demo path

Four routes, and it still answers all four judge questions:

1. **`/dashboard`** — portfolio, allocation, agent trigger, freshness dots.
   *Is it alive?*
2. **`/risk`** — `KillSwitchPanel` + `GreeksCockpit`, honest `null`s and all.
   *What is the risk?*
3. **`/council`** — six verdicts, dissent, red-team panel if it shipped.
   *Did anyone argue?*
4. **`/blotter`** — approval queue with the submit guard and the halt block.
   *Can I stop it?*

`/terminal`, `/assets` and `/settings` already exist and are presentable; they are
supporting material, not the path. `/lab` and `/ledger` are upside only.

Everything in this path except `/risk` and `/blotter` works **today**, and neither
of those two needs a single new backend endpoint to render its primary panel —
`/blotter` in particular runs entirely on `GET /api/trade/orders` and `POST
/api/trade`, both of which already exist, `client_order_id` included. That is
deliberate: the minimum viable demo has zero integration dependencies on a
teammate who is fixing four CRITICAL defects on the same six-day clock.

---

## 7 · Reconciliation log

What the specs changed after this register's first draft. Kept because the *pattern*
matters: three of these were found by reading code the brief had described from
memory.

| Source | Finding | Action |
|---|---|---|
| SPEC-F2 §2 | `ScoreGauge` clamps non-finite to `0` (`ScoreGauge.tsx:26`) — unusable on `/risk` | R23 added; brief instructs `CapGauge` instead |
| SPEC-F5 §4 | `client_order_id` already accepted at `trade.py:29`, forwarded `:77-78`, echoed `:101`; Alpaca rejects duplicates | R24 added; **no backend change needed** for idempotency, only a field on the frontend `TradeRequest` interface |
| SPEC-F5 §3.3 | `_pick_option_contract()` now exists at `agent.py:19` — KNOWN-ISSUES #2 is being fixed mid-sprint | R25 added; rules key on the null *value*, never the issue's status |
| SPEC-F1 §0 | `FRONTEND.md` is at `docs/FRONTEND.md`, not repo root | Path corrected in the specs |
| Critique §1 | Vitest + Playwright already exist; 105 + 20 tests; **3 failing** | F6 rewritten from "build a harness" to "fix the red suite"; R1/R2/R13 added |
| Critique §3 | Backend has 4 CRITICAL defects under all 8 requested endpoints | Brief §9 inverted into a contingency table; R5 added |

The recurring lesson, and the reason this section exists: **every one of these was
a claim that sounded right and was wrong.** The register's own entries are no more
trustworthy than the greps behind them — R1, R11, R12, R13, R23, R24 and R25 each
cite a file and line for exactly that reason. Re-verify before acting on any row
that does not.

