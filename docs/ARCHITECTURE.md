# ARCHITECTURE

## System shape

```
┌──────────────────────────────────────────────────────────────────┐
│  FRONTEND — Next.js App Router, Tailwind                         │
│  Dashboard · Assets · Terminal · Council · Settings              │
│  frontend/lib/api.ts  (typed client, all paths under /api)       │
└────────────────────────────┬─────────────────────────────────────┘
                             │  HTTP, JSON
                             │  dev: next.config.js rewrites /api/* → :8000
┌────────────────────────────▼─────────────────────────────────────┐
│  BACKEND — FastAPI                                               │
│  routes/portfolio · trade · strategy · council · agent           │
│  alpaca_client.py   AlpacaAPIError, timeout/retry, 502 on failure │
│  mock_data.py       fallback fixtures when no credentials         │
└──────────┬─────────────────────────────────┬─────────────────────┘
           │                                 │
           │ imports                         │ HTTPS
┌──────────▼──────────────────────┐   ┌──────▼──────────────────────┐
│  AGENT LAYER — agent/           │   │  Alpaca paper API           │
│                                 │   │  paper-api.alpaca.markets   │
│  config.py   StrategyConfig     │   │  data.alpaca.markets        │
│  strategies/ covered_call, CSP  │   └─────────────────────────────┘
│  decision_engine.py             │
│  exit_manager.py                │   ┌─────────────────────────────┐
│  portfolio_analyst.py           │   │  Yahoo Finance (free)       │
│                                 │◄──┤  fundamentals, dividends    │
│  council/                       │   │  24h cache                  │
│   ├── personas.py     6 personas│   └─────────────────────────────┘
│   ├── engine.py       consensus │
│   ├── graham_principles.py      │
│   ├── mr_market.py              │
│   ├── fundamentals.py           │
│   ├── handoff.py      TierPolicy│
│   ├── risk_mitigation.py  kill  │
│   └── daily_cycle.py  ORCHESTRA │
└─────────────────────────────────┘
```

## Dependency direction

```
frontend  →  backend  →  agent  →  external APIs
```

Strictly one-directional. The agent layer never imports from `backend/`, and the
backend never imports from `frontend/`. This is what makes the agent layer
testable without a web server and the whole system testable without network.

## The daily cycle — primary data flow

`POST /api/council/cycle` → `agent/council/daily_cycle.py::run_daily_cycle`

```
       ┌─────────────────────────┐
       │ 1. KILL-SWITCH CHECK    │
       │    risk_mitigation.py   │
       └───────────┬─────────────┘
                   │
          halted?  ├── YES ──►  return { halted, reasons }   ✕ STOP
                   │             nothing else executes
                   ▼ NO
       ┌─────────────────────────┐
       │ 2. Snapshots +          │  timeout 5s, 2 retries,
       │    fundamentals         │  fallback → market_snapshots.json
       └───────────┬─────────────┘
                   ▼
       ┌─────────────────────────┐
       │ 3. Mr. Market mood      │  from SPY price series + vol
       │    mr_market.py         │  euphoric → block new entries
       └───────────┬─────────────┘
                   ▼
       ┌─────────────────────────┐
       │ 4. Council assessment   │  6 personas per symbol
       │    engine.py            │  → consensus, dissent
       └───────────┬─────────────┘
                   ▼
       ┌─────────────────────────┐
       │ 5. Exit evaluation      │  TP 60% / SL 200% / roll
       │    exit_manager.py      │  on open overlay positions
       └───────────┬─────────────┘
                   ▼
       ┌─────────────────────────┐
       │ 6. Entry screening      │  tier policy from handoff.py
       │    strategies/ +        │  + concentration + cash + sector
       │    decision_engine.py   │  blocked entries keep their reason
       └───────────┬─────────────┘
                   ▼
       ┌─────────────────────────┐
       │ 7. DailyDirective queue │  EXIT / ROLL / INITIATE / HOLD /
       │                         │  MONITOR, each with trace +
       │                         │  provenance
       └─────────────────────────┘
```

**Step 1 is first and that ordering is load-bearing.** If the kill-switch fires,
no later step runs, so a halted portfolio cannot produce a new entry through any
path. Enforced and tested.

## The council → engine feedback loop

This is the part that makes the system a closed loop rather than two disconnected
features:

```
run_full_assessment.py
        │  runs the 6 personas over the 8-symbol universe
        ▼
docs/council_report.md
        │  HANDOFF section: tier bands, per-symbol overrides, sector cap
        ▼
handoff.py  ──parse──►  TierPolicy
        │
        ▼
decision_engine.py + strategies/
        │  delta bands adjusted, size multiplied, candidates blocked
        ▼
reasoning_trace: ["blocked: tech complex at 42% > 40% cap (council §6)"]
```

The council does not merely advise — its conclusions become enforced constraints,
and every enforcement action cites the section that caused it.

**Weak point:** that parse is markdown-with-regex. See `AI-ENGINEER.md`.

## Live vs mock

Every Alpaca-dependent path has a mock fallback so the system runs with no
credentials. Mode is reported in the response (`"mode": "live" | "mock"`).

The important lesson: **degradation must be visible.** For a full day an auth
header typo (`APCA-API-SECRET` instead of `APCA-API-SECRET-KEY`) meant every live
call returned 401 and silently fell back to mock — the app looked perfectly
healthy. That is why the backend now raises `AlpacaAPIError` → HTTP 502 on live
failure instead of quietly substituting mock, and why `/api/strategy/screen`
returns a `live_error` string that the frontend renders as an amber banner.

## Backend routes

All under `/api` except `/health`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + whether Alpaca is configured |
| GET | `/api/portfolio` | Account + positions + orders |
| POST | `/api/trade` | Submit an order (validated, explicit) |
| GET | `/api/trade/orders` | Order history |
| GET/POST | `/api/strategy/screen` | Covered-call screening, engine-enriched |
| GET/PUT | `/api/strategy/config` | Read/update StrategyConfig |
| GET/POST | `/api/council/assess` | Persona verdicts per symbol |
| POST | `/api/council/cycle` | Full daily cycle |
| POST | `/api/agent/run` | Recommendations + order intents, never submits |

`/api/agent/run` returns `orders_ready: false` always, and every intent carries
`requires_approval: true` and `submitted: false`. The backend has no auto-submit
path.

## Frontend pages

| Route | Renders |
|---|---|
| `/dashboard` | Metrics, holdings, agent status, agent control |
| `/assets` | Position detail |
| `/terminal` | Agent feed with reasoning traces, Daily Cycle panel, order-intent preview |
| `/council` | Six-persona verdicts, tier badges, consensus gauges, dissent |
| `/settings` | Live StrategyConfig editing |

Layout: `Sidebar` is `fixed` at 240px on `lg+`, so each page's content wrapper
carries `lg:ml-[240px]`. Below `lg` the sidebar is hidden and navigation is a
`useState` drawer — no bottom nav.

## Security posture

- Credentials from environment only — `ALPACA_KEY`, `ALPACA_SECRET`,
  `ALPACA_BASE_URL`. Never in code, never logged, never committed.
- `.env` gitignored; `docs/.cache/` gitignored; copyrighted book files gitignored.
- Config validated for **value** as well as type — NaN and ±Infinity rejected,
  because a NaN threshold silently disables every comparison it appears in.
- Route inputs bounded (`top_n`, `qty`, `limit_price`, symbol regex).
- Handoff parsing sanitised, delta clamped ≤ 0.95, DTE ≤ 365.
- 7 penetration-test findings fixed, 32 regression tests.

## What this architecture does not have

- **No persistent database.** State lives in Alpaca plus in-process. Restarting
  loses the fundamentals cache (it is in `/tmp`), which silently drops council
  confidence.
- **No authentication on the backend.** Any local caller can hit every endpoint
  including `POST /api/trade`. Acceptable for a localhost hackathon demo; **not
  acceptable if exposed**, and it has been exposed via Cloudflare tunnel during
  development.
- **No message queue or scheduler.** The daily cycle runs when something calls
  it; nothing runs it daily.
- **No backtest harness.** Nothing establishes that these parameters or this
  persona blend are profitable.
