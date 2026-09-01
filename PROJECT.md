# Project: ALPACHA Autonomous Options Overlay AI Trading Agent

## Architecture
ALPACHA (AutoOverlay AI) is an institutional-grade, multi-agent covered call and cash-secured put options overlay trading system designed for the Alpaca AI Trading Agents Hackathon.
- **Autonomous Scheduler Daemon (`backend/app/scheduler.py`)**: APScheduler `BackgroundScheduler(daemon=True)` running 1-hour automated trading cycles, protected by market hours validation (`is_market_open()`), atomic non-blocking thread execution lock (`_execution_lock`), and SQLite working-order deduplication.
- **Pre-Trade Risk Gate & Layer 1 Kill-Switch (`agent/council/risk_mitigation.py`, `backend/app/risk/gate.py`)**: 7-step daily investment cycle (kill-switch evaluated first). Kill-switch drawdown limits (5% max drawdown from SQLite/JSON high-water mark, 2% single-day loss, 3 consecutive stop-losses), OCC strike collateral derivation ($\text{Strike} \times 100 \times \text{Contracts}$) preventing inverted drawdown false halts, and midpoint limit pricing (`(bid + ask) / 2`).
- **Model Context Protocol (MCP) Multi-Agent Engine (`backend/app/routes/bot.py`, `agent/council/`)**: `GET /api/bot/mcp/tools` exposing 5 native MCP tools (`run_autonomous_cycle`, `get_bot_status`, `get_portfolio_summary`, `screen_options_overlay`, `evaluate_risk_gate`) and 6-persona investment council (Buffett, Munger, Dalio, Graham 7-check Ch.14 tests, Lynch, Wood).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Autonomous Background Scheduler | APScheduler daemon with configurable intervals (default 1.0h) executing autonomous trading cycles | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Market Hours Validation | `is_market_open()` validating Alpaca `/v2/clock` with UTC weekday trading window fallback (13:30–20:00 UTC) | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Concurrency Execution Lock | Non-blocking `_execution_lock.acquire(blocking=False)` preventing overlapping cycles under latency | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Working-Order Deduplication | SQLite `BackendStore` idempotency keys preventing duplicate options order submission | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Bot Management Endpoints | FastAPI routes: `/api/bot/status`, `/api/bot/start`, `/api/bot/stop`, `/api/bot/config`, `/api/bot/cycle`, `/api/bot/history` | M1 | ORIGINAL_REQUEST §R1 |
| 6 | 7-Step Investment Council Cycle | Daily cycle pipeline executing Kill-Switch first, Snapshots, Mr. Market mood, 6 Personas consensus, Exit Manager, Entry Screening, Priority Queue | M2 | ORIGINAL_REQUEST §R2 |
| 7 | Kill-Switch Drawdown Limits | 5% max drawdown from peak equity, 2% single-day loss, 3 consecutive stop-losses with persistent high-water mark (`PeakStore`) | M2 | ORIGINAL_REQUEST §R2 |
| 8 | OCC Strike Collateral Derivation | OCC option symbol regex derivation ($\text{Strike} \times 100 \times \text{Contracts}$) providing invariant collateral baseline and eliminating inverted drawdown false halts | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Midpoint Limit Order Pricing | Limit order price derivation at exact bid-ask midpoint: `(bid + ask) / 2` | M2 | ORIGINAL_REQUEST §R2 |
| 10 | 9-Check Pre-Trade Risk Gate | Pre-trade risk gate in `backend/app/risk/gate.py` with hard-block unoverridable kill-switch | M2 | ORIGINAL_REQUEST §R2 |
| 11 | MCP Native Tool Exposure | `GET /api/bot/mcp/tools` exposing native JSON schema definitions for external AI agent integration | M3 | ORIGINAL_REQUEST §R3 |
| 12 | Multi-Agent Consensus Engine | 6-persona council consensus engine with supermajority rules, Graham Ch.14 7-test screening, split detection, and dissent logs | M3 | ORIGINAL_REQUEST §R3 |
| 13 | Documentation Suite Alignment | Full accuracy across `README.md`, `ARCHITECTURE.md`, `API-CONTRACT.md`, `RISK-MANAGEMENT.md`, `KNOWN-ISSUES.md`, `TESTING.md`, `AI-ENGINEER.md`, `HEDGE-FUND-COUNCIL.md` | M4 | ORIGINAL_REQUEST §Acceptance |
| 14 | Git Master Branch Synchronization | Master branch synchronized with commit `c8843b7` | M4 | ORIGINAL_REQUEST §Acceptance |
| 15 | 596-Test Python Regression Suite | 100% green status across `agent/tests` (194 tests) and `backend/tests` (402 passing, 1 skipped) | M5 | ORIGINAL_REQUEST §Acceptance |
| 16 | Scheduler Concurrency Verification | Full verification of `test_bot_scheduler.py` thread safety, start/stop lifecycle, and idempotency | M5 | ORIGINAL_REQUEST §Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | R1: Background Scheduler & Bot API | Scheduler daemon, market clock validation, concurrency locks, order deduplication, bot REST routes | none | DONE |
| M2 | R2: Risk Gate & Institutional Overlay | 7-step council cycle, kill-switch drawdown limits (5%/2%/3 stops), OCC collateral formula, midpoint pricing, risk gate | M1 | DONE |
| M3 | R3: MCP & Multi-Agent Interface | `GET /api/bot/mcp/tools` schema, 6-persona council, Graham defensive tests | M2 | DONE |
| M4 | Documentation & Git Alignment | Documentation suite alignment, Git master branch verification at commit `c8843b7` | M1, M2, M3 | DONE |
| M5 | E2E Testing, Adversarial Verification & Forensic Audit | 596 regression test pass, `test_bot_scheduler.py` concurrency pass, Reviewer & Challenger verification, Forensic Audit | M1, M2, M3, M4 | IN_PROGRESS |

## Interface Contracts
### Scheduler (`backend/app/scheduler.py`) ↔ FastAPI App (`backend/app/main.py`)
- `get_scheduler() -> BotScheduler`: Singleton accessor for bot scheduler instance.
- `BotScheduler.start()`: Initializes background daemon and schedules interval job.
- `BotScheduler.stop()`: Shuts down background scheduler cleanly.
- `BotScheduler.run_cycle_now() -> dict`: Atomically acquires `_execution_lock`, runs market validation, executes 7-step council cycle, releases lock, returns summary dict.
- `BotScheduler.get_status() -> dict`: Returns `{ "running": bool, "interval_hours": float, "is_market_open": bool, "last_run": str, "next_run": str, "cycle_count": int, "last_result": dict }`.

### Pre-Trade Risk Gate (`backend/app/risk/gate.py`) ↔ Trade Execution (`backend/app/routes/agent.py`)
- `evaluate_trade(trade_request: TradeRequest, account_state: AccountState, market_state: MarketState, high_water_mark: float) -> RiskGateResult`:
  - Pure function evaluating 9 distinct safety checks.
  - Returns `{ "approved": bool, "blocked_by": list[str], "reasons": list[str], "calculated_collateral": float }`.
  - Hard-blocks `kill_switch` if drawdown > 5.0%, daily loss > 2.0%, or consecutive stop losses >= 3.

### MCP Interface (`backend/app/routes/bot.py`) ↔ External Agents
- `GET /api/bot/mcp/tools`: Returns `{ "tools": [ { "name": str, "description": str, "inputSchema": dict } ] }` conforming to Model Context Protocol specification.

## Code Layout
```
c:\Projects\ALPACHA/
├── agent/                         # Core hedge fund council and risk intelligence
│   ├── council/                   # 6-persona investment council, daily cycle, risk mitigation
│   │   ├── daily_cycle.py         # 7-step investment council orchestration
│   │   ├── personas.py            # Buffett, Munger, Dalio, Graham, Lynch, Wood
│   │   ├── risk_mitigation.py     # Kill-switch, OCC strike collateral, drawdown calculation
│   │   └── graham.py              # Benjamin Graham Ch.14 7-test quantitative screener
│   ├── state/                     # PeakStore high-water mark persistence
│   └── tests/                     # 12 test files, 194 unit and integration tests
├── backend/                       # FastAPI REST API & Execution Engine
│   ├── app/
│   │   ├── scheduler.py           # APScheduler autonomous background daemon
│   │   ├── routes/
│   │   │   ├── bot.py             # Bot control endpoints & MCP tool manifest
│   │   │   ├── agent.py           # Council execution, trade evaluation, options picker
│   │   │   └── portfolio.py       # Portfolio inspection, positions, ledger
│   │   ├── risk/
│   │   │   └── gate.py            # 9-check pre-trade risk engine
│   │   ├── adapters/              # Alpaca API client, options chain adapter
│   │   └── main.py                # FastAPI application entrypoint & lifespan
│   └── tests/                     # 24 test files, 403 test cases (including test_bot_scheduler.py)
├── docs/                          # Architecture, API contract, Risk, Testing, Known Issues docs
├── README.md                      # Project root documentation & quickstart
└── .agents/                       # Agent coordination metadata (plans, handoffs, briefings)
```
