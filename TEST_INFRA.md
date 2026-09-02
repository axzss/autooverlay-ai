# E2E Test Infra: ALPACHA Autonomous Options Overlay AI Trading Agent

## Test Philosophy
- Opaque-box, requirement-driven, and institutional safety-focused.
- Systematic 4-tier testing hierarchy: Category-Partition (Tier 1), Boundary Value Analysis (Tier 2), Pairwise Interaction (Tier 3), and Real-World Multi-Cycle Market Workload Testing (Tier 4).

## Feature Inventory & Test Mapping
| # | Feature | Source (Requirement) | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Scenario) |
|---|---------|----------------------|:----------------:|:-----------------:|:-----------------:|:-----------------:|
| 1 | Autonomous Background Scheduler | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 2 | Market Hours Validation (`is_market_open()`) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 3 | Concurrency Execution Lock (`_execution_lock`) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 4 | Working-Order Deduplication | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 5 | Bot Management Endpoints (`/api/bot/*`) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 6 | 7-Step Investment Council Cycle | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 7 | Kill-Switch Drawdown Limits (5% / 2% / 3 stops) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 8 | OCC Strike Collateral Derivation | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 9 | Midpoint Limit Order Pricing | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 10 | 9-Check Pre-Trade Risk Gate | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 11 | MCP Native Tool Exposure (`GET /api/bot/mcp/tools`) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 12 | Multi-Agent Consensus Engine & Personas | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Test Runner**: Python pytest runner (`pytest agent/tests backend/tests -v`)
- **Isolation Harness**: In-memory SQLite DB, mock Alpaca client fixtures, `tmp_path` ephemeral high-water mark stores
- **Concurrency Harness**: `backend/tests/test_bot_scheduler.py`, `backend/tests/test_council_concurrency.py`, `backend/tests/test_trade_idempotency.py`

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity | Verification |
|---|----------|--------------------|------------|--------------|
| 1 | Full Hourly Autonomous Market Cycle | Scheduler + Market Clock + 7-Step Council + Order Deduplication | High | Clean execution, no lock collisions, orders logged |
| 2 | Market Crash & Kill-Switch Activation | PeakStore + 5% Drawdown Gate + Council Step 0 Halt | Critical | Trade blocked, kill-switch reason logged, zero orders submitted |
| 3 | Short Option Assignment & OCC Collateral Derivation | OCC Regex + Strike * 100 * Contracts + Coverage Gate | High | Non-negative collateral calculation, correct position sizing |
| 4 | External AI Agent MCP Orchestration | `GET /api/bot/mcp/tools` + `POST /api/bot/cycle` | Medium | Valid tool schemas, execution via standard tool call |
| 5 | Midpoint Limit Order Execution in Volatile Spread | Options Adapter + `(bid + ask) / 2` + Price Sanity Gate | Medium | Valid limit order price within bid-ask bounds |

## Coverage Thresholds
- Total tests passing: 596 passed across 36 test files
- Zero failing tests
- Scheduler thread concurrency verified
