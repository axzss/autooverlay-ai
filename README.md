# AutoOverlay AI

Agentic options-income overlay for existing equity portfolios — built for the
**Alpaca AI Trading Agents Hackathon, Track 04**.

Most investors hold equity that generates nothing while it sits there. Running an
options overlay against it by hand is time-consuming and easy to get wrong.
AutoOverlay AI does the analysis autonomously — but every recommendation has to
survive a six-person investment committee first, and **no order is ever submitted
without a human approving it**.

## What makes it different

**1 · Investment Council.** Six investor personas — Warren Buffett, Charlie
Munger, Ray Dalio, Benjamin Graham, Peter Lynch, Cathie Wood — each score a stock
against their own philosophy. Their verdicts combine into a consensus, and
**disagreement is shown, not smoothed over**. When the committee is split, that
is information.

**2 · Graham from the actual book.** The Graham persona implements the seven
defensive tests from Chapter 14 of *The Intelligent Investor*, plus Margin of
Safety (Ch. 20) and Mr. Market psychology (Ch. 8). Every verdict names the test
it passed or failed — e.g. *"fails test 4 (dividend record): 15y coverage only"* —
so the reasoning is auditable rather than asserted.

**3 · Nothing is a black box.** Every recommendation carries a `reasoning_trace`
listing each check performed, and every directive carries `provenance` naming the
rule that produced it (`council §6`, `graham test 4`, `tier:mid`).

## Risk control is the product, not a feature

- **Kill-switch** halts all new entries on >5% drawdown, >2% daily loss, or 3
  consecutive stop-losses — and it is checked **first** in every cycle, so a
  halted portfolio cannot open a position through any path
- Concentration cap 25% per ticker · cash reserve floor 10% · tech-complex sector
  cap 40% of deployed overlay capital
- Take profit at 60% of premium captured · stop loss at 200% of initial premium ·
  roll on |delta| > 0.40 or DTE < 7
- Volatility tiers: high-vol names get tighter delta bands and half size. TSLA
  (59% annualised) is capped at delta ≤ 0.10
- **No auto-submit exists anywhere in the backend.** `orders_ready` is always
  `false`; every intent carries `requires_approval: true`

Full detail: [`docs/RISK-MANAGEMENT.md`](docs/RISK-MANAGEMENT.md)

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js App Router + Tailwind — Dashboard, Assets, Terminal, Council, Settings |
| Backend | FastAPI — 11 routes, all under `/api` except `/health` |
| Agent | Python — strategies, decision engine, exit manager, portfolio analyst, council, daily-cycle orchestrator |
| Broker | Alpaca paper trading API, real market data |
| Fundamentals | Free public sources, 24h cache, degrades to `INCONCLUSIVE` rather than guessing |

Dependency direction is strictly one-way: `frontend → backend → agent → external
APIs`. The agent layer runs and tests without a web server or network.

## Quick start

```bash
# 1. Credentials — never commit .env
cp .env.example .env        # ALPACA_KEY, ALPACA_SECRET, ALPACA_BASE_URL

# 2. Backend  (works without credentials — falls back to mock data)
cd backend && pip install -r requirements.txt
PYTHONPATH=.. uvicorn app.main:app --reload

# 3. Frontend
cd frontend && npm install && npm run dev
```

Open http://localhost:3000/dashboard

```bash
# Tests — run both suites, the agent layer is imported by backend routes
pytest agent/tests backend/tests -q     # 236 passed, 1 skipped

# Frontend gates
cd frontend && npx tsc -p tsconfig.json --noEmit && npm run build
```

> Hitting an unexplained 500 on a page in dev? `rm -rf frontend/.next` and
> rebuild — a corrupt cache from repeated dev-server restarts looks like a code
> bug but isn't.

## Repo layout

```
agent/          strategies, decision engine, exit manager, portfolio analyst
  council/      6 personas, Graham principles, Mr. Market, handoff, kill-switch,
                daily-cycle orchestrator
backend/        FastAPI app, routes, Alpaca client, tests
frontend/       Next.js UI, typed API client
docs/           full documentation — start at docs/README.md
specials/        API contract notes (see KNOWN-ISSUES: currently drifted)
```

## Results on real market data

Eight symbols — AAPL, MSFT, NVDA, TSLA, SPY, QQQ, JPM, KO.

Before fundamentals were available, all eight came back HOLD (LOW-CONFIDENCE): a
committee of six unanimously saying "not sure" is theatre. After merging
fundamentals:

| Symbol | Before | After | Verdict |
|---|---|---|---|
| **NVDA** | 53.9 | **68.0** | HOLD → **ACCUMULATE** |
| **MSFT** | 53.9 | **60.2** | HOLD → **ACCUMULATE** |
| KO | 56.6 | 59.2 | HOLD |
| AAPL | 53.3 | 57.2 | HOLD |
| SPY / QQQ | 56.6 | 55.4 | HOLD |
| JPM | 56.6 | 52.0 | HOLD |
| **TSLA** | 53.9 | **43.8** | HOLD — pushed down on 59% vol |

Four up, four down. That two-directional movement is the evidence fundamentals
are being weighed rather than uniformly inflating scores.

Notable: **every name fails Graham's P/E ≤ 15 ceiling** — a fair verdict on 2026
valuations from a 1949 standard, not a bug.

Full report: [`docs/council_report.md`](docs/council_report.md)

## Security

- Credentials from environment only — never in code, never logged, never committed
- `.env`, `docs/.cache/`, and copyrighted source texts are gitignored
- Config validated for **value** as well as type: NaN and ±Infinity are rejected,
  because a NaN threshold makes every comparison return `False` and silently
  disables the kill-switch while the UI still shows it active
- Internal penetration test: **7 findings, all fixed, 32 regression tests**

Details: [`docs/security_review.md`](docs/security_review.md)

## Documentation

| Document | Covers |
|---|---|
| [`docs/README.md`](docs/README.md) | Documentation index |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System diagram, data flow |
| [`docs/AI-ENGINEER.md`](docs/AI-ENGINEER.md) | Agent layer in depth |
| [`docs/HEDGE-FUND-COUNCIL.md`](docs/HEDGE-FUND-COUNCIL.md) | The six personas, Graham, Mr. Market |
| [`docs/FRONTEND.md`](docs/FRONTEND.md) | Next.js layer: API client, layout, brand, charts |
| [`docs/RISK-MANAGEMENT.md`](docs/RISK-MANAGEMENT.md) | Kill-switch, caps, exits, tiers |
| [`docs/API-CONTRACT.md`](docs/API-CONTRACT.md) | Every endpoint, **verified** shapes |
| [`docs/MEMORY.md`](docs/MEMORY.md) | Dated build log with criticism per milestone |
| [`docs/TESTING.md`](docs/TESTING.md) | Suite map, and what is **not** covered |
| [`docs/KNOWN-ISSUES.md`](docs/KNOWN-ISSUES.md) | Open defects, honestly listed |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | What is next, by value |
| [`docs/JOBDESK.md`](docs/JOBDESK.md) | Ownership and scope boundaries |

## Team

| Person | GitHub | Owns |
|---|---|---|
| Aditya Maulana | [`axzss`](https://github.com/axzss) | Frontend |
| Zacky Muhammad Dinata | [`zmdinata`](https://github.com/zmdinata) | AI engineering + council |
| Aji Nur Aji | [`AjiNurAji`](https://github.com/AjiNurAji) | Backend |

Scope boundaries and verification requirements per role:
[`docs/JOBDESK.md`](docs/JOBDESK.md)

## Status

237 tests collected, 236 passing. Backend complete with zero TODOs. Agent layer
core complete. Frontend fully wired: all endpoints consumed, brand identity and
charts built, and every mockup component either connected to real data or deleted.

Known defects are listed openly in
[`docs/KNOWN-ISSUES.md`](docs/KNOWN-ISSUES.md) rather than left for a reviewer to
discover — the two that matter most being a fundamentals cache that does not
survive a restart, and the fact that **nobody has yet verified the UI visually**:
type checks and a passing build are not the same as looking at it.

---

*Paper trading only. Not investment advice.*
