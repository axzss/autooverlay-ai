# API-CONTRACT

**Every shape here was verified by calling a running backend**, not copied from a
design document. Where a response differs from
`specials/BACKEND_FRONTEND_API.md`, this file is correct and that one is a known
defect (`KNOWN-ISSUES.md`).

Verified against `mode: "mock"` on 2026-08-29 with `alpaca_configured: false`.

## Conventions

- Base URL: `http://localhost:8000`, override with `NEXT_PUBLIC_API_BASE_URL`
- **All routes are mounted under `/api` except `/health`**, which is bare
- `Content-Type: application/json` on every request
- `422` for invalid input, `502` for Alpaca failure
- Every response carries `"mode": "live" | "mock"`

### The `/api` prefix trap

`backend/app/main.py` mounts every router with `prefix="/api"`, and only
`@app.get("/health")` sits outside it. This caused a day-long outage where every
frontend call 404'd while the UI looked healthy because it fell back to mock on
error. Confirmed by direct test:

```
GET /health          → 200
GET /api/portfolio   → 200
GET /portfolio       → 404
```

The dev proxy in `frontend/next.config.js` must therefore map `/api/health` to
bare `/health` **before** the catch-all `/api/:path*` rule — Next matches in
order.

---

## `GET /health`

```json
{ "status": "ok", "alpaca_configured": false }
```

The only route not under `/api`. Use it to decide whether the UI should show a
"mock mode" badge.

**Dev proxy note:** The frontend's custom Express server (`frontend/server.js`)
proxies `/api/health` → `http://127.0.0.1:8000/health` with
`pathRewrite: { '^/api': '/api' }`, so the backend receives `/api/health` and
returns 200.

---

## `GET /api/portfolio`

```json
{
  "mode": "mock",
  "account_info": {
    "account_id": "MOCK_ACCOUNT_1",
    "status": "ACTIVE",
    "currency": "USD",
    "cash": "12543.78",
    "cash_withdrawable": "8231.45",
    "portfolio_value": "47821.32",
    "pattern_day_trader": false,
    "shorting_enabled": false
  },
  "positions": [ ... ],
  "orders": [ ... ]
}
```

**Money values are strings, not numbers** — this is Alpaca's convention, passed
through unchanged. Coerce with `Number()` before arithmetic.

---

## `GET|POST /api/strategy/screen`

Query params: `top_n` (bounded), `full` (bool — engine enrichment), `symbols`.

```json
{
  "mode": "mock",
  "strategy": "covered_call",
  "count": 3,
  "candidates": [
    {
      "symbol": "AAPL",
      "underlying_price": 172.9,
      "option_symbol": "AAPL240621C00175000",
      "strike_price": 175.0,
      "expiration_date": "2024-06-21",
      "days_to_expiry": 1,
      "bid": 1.25,
      "ask": 1.3,
      "last_price": 1.28,
      "volume": 12500,
      "open_interest": 8700,
      "implied_volatility": 0.24
    }
  ],
  "live_error": "AAPL: connection timeout; MSFT: 502"
}
```

`live_error` is **optional** — present only when live data failed. It is set on
the positions-fetch failure path and as a joined `"SYM: err; SYM: err"` string
for per-symbol snapshot failures. Field name is exactly `live_error`
(`backend/app/responses.py::CandidateResponse`).

Do not swallow it. The frontend renders it as an amber banner, because a silent
mock fallback hid an auth bug for a full day.

With `full=true`, candidates gain `action`, `risk_score`, `reasoning_trace`, and
the response gains `portfolio_context`.

---

## `GET|PUT /api/strategy/config`

```json
{
  "config": {
    "take_profit_pct": 0.6,
    "stop_loss_mult": 2.0,
    "roll_delta": 0.4,
    "roll_min_dte": 7,
    "delta_min": 0.15,
    "delta_max": 0.35,
    "dte_min": 7,
    "dte_max": 45,
    "max_concentration_pct": 25.0,
    "min_cash_reserve_pct": 10.0,
    "max_sector_concentration_pct": 40.0,
    "sector_cap_group": ["AAPL", "MSFT", "NVDA", "QQQ"],
    "kill_max_drawdown_pct": 5.0,
    "kill_max_single_day_loss_pct": 2.0,
    "kill_consecutive_stop_losses": 3,
    "overlay_only_drawdown": true,
    "scalp_mode": false,
    "scalp_min_dte": 0,
    "scalp_max_dte": 1,
    "scalp_delta_min": 0.2,
    "scalp_delta_max": 0.5,
    "scalp_target_pct": 0.25,
    "scalp_stop_mult": 2.0,
    "scalp_max_daily_trades": 6,
    "scalp_max_daily_loss_pct": 1.5
  }
}
```

`PUT` rejects with `422`: NaN, ±Infinity, out-of-magnitude values, and wrong
types. These are not cosmetic — security finding S1 was that a NaN threshold
makes every comparison return `False`, silently disabling the kill-switch.

Scalping mode adds daily safeguards: `scalp_max_daily_trades` and
`scalp_max_daily_loss_pct` are enforced when `scalp_mode=true`.

---

## `GET|POST /api/council/assess`

`GET` takes `?symbols=AAPL,MSFT`. `POST` takes `{"symbols": ["AAPL"]}`. Omit for
the default 8-symbol universe.

```json
{
  "mode": "mock",
  "count": 8,
  "assessments": [
    {
      "symbol": "AAPL",
      "tier": "MID",
      "tier_policy_summary": "AAPL: 30.5% vol → 'mid' tier (delta 0.10-0.25, DTE≤45, strategies=CSP,COVERED_CALL, size x0.5)",
      "tier_policy": {
        "delta_min": 0.1,
        "delta_max": 0.25,
        "max_dte": 45,
        "allowed_strategies": ["CSP", "COVERED_CALL"],
        "size_multiplier": 0.5
      },
      "consensus_score": 53.6,
      "recommendation": "HOLD",
      "majority_stance": "HOLD",
      "is_split": true,
      "verdicts": [
        { "persona": "Warren Buffett", "score": 48.2, "stance": "HOLD", "bullets": ["..."] }
      ],
      "dissent": [
        {
          "persona": "Charlie Munger",
          "direction": "bullish-minority",
          "score": 75.0,
          "consensus": 53.61,
          "why": ["ROE missing — can't verify quality.", "Gross margin missing."]
        }
      ]
    }
  ]
}
```

### Three fields where the older doc is wrong

| Field | Older doc says | **Actual** |
|---|---|---|
| `tier` | `"CORE"` | `"LOW"` \| `"MID"` \| `"HIGH"` |
| `consensus_score` | `7.5` (0–10) | `53.6` (**0–100**) |
| `delta_min` | `-0.2` (negative) | `0.1` (**positive** — short option delta) |

Also: `dissent[].why` is a **`string[]`**, not a string.

Building UI thresholds against the older doc puts every colour boundary in the
wrong place.

---

## `POST /api/council/cycle`

Body (all optional): `candidates`, `cash_override`, `portfolio_state_overrides`.

Response keys, verified:

```json
{
  "halted": true,
  "steps_run": ["kill_switch"],
  "directives": [ ... ],
  "assessments": [ ... ],
  "kill_switch": { "halted": true, "reasons": ["..."] },
  "portfolio_state": { ... },
  "halt_reasons": ["single-day loss -12.96% breaches kill threshold -2.00%"]
}
```

When `halted` is `true`, `steps_run` contains only `kill_switch` — every later
step is skipped by design.

### DailyDirective

```json
{
  "action": "INITIATE",
  "symbol": "MSFT",
  "priority": 2,
  "params": { "strategy_allowed": ["CSP"], "delta_min": 0.10, "delta_max": 0.25 },
  "reasoning_trace": ["tier mid: delta band 0.10-0.25", "sector cap not breached"],
  "provenance": [
    { "source": "tier:mid", "detail": "30.5% annualised vol" },
    { "source": "council §6", "detail": "consensus HOLD, size x0.5" }
  ]
}
```

`action` ∈ `EXIT` | `ROLL` | `INITIATE` | `HOLD` | `MONITOR`.
`reasoning_trace` is always `list[str]` — normalised by `_normalize_trace()`.

---

## `POST /api/agent/run`

Recommendation-only. **Never submits.**

Verified live response, mock mode:

```json
{
  "run_id": "run-554e72edf83d4a1793b851a1285c2d97",
  "status": "completed",
  "mode": "mock",
  "orders_ready": false,
  "order_intents": [],
  "recommendations": [ /* 1 item */ ],
  "risk_summary": { "halted": true, "kill_switch": {...}, "portfolio_state": {...}, "blocked_entries": 0 },
  "reasoning_trace": [ /* 2 lines */ ],
  "cycle": { /* full cycle response, 7 keys */ },
  "completed_at": "2026-08-29T03:59:13.890321+00:00"
}
```

### Two things to know before building UI on this

**1. `recommendations` are council *directives*, not screening candidates.** They
have `action` / `symbol` / `params` / `priority` / `reasoning_trace` /
`provenance` — not `strike_price` / `annualized_premium_yield`. Do not reuse the
`/strategy/screen` card component here.

**2. `order_intents` currently cannot contain a real contract.**
`_order_intents()` reads `params.get("option_symbol")` and
`params.get("limit_price")` from each `INITIATE` directive — but `INITIATE`
directives carry *tier policy* (`strategy_allowed`, `delta_min/max`, `size`), not
a resolved contract. So in practice:

- `option_symbol` → `null`
- `limit_price` → `null`
- `type` → `"market"` (because `limit_price` is null)

The intent shape when non-empty:

```json
{
  "action": "SELL_TO_OPEN",
  "strategy": "covered_call",
  "symbol": "AAPL",
  "option_symbol": null,
  "contracts": 1,
  "qty": 1,
  "side": "sell",
  "type": "market",
  "time_in_force": "day",
  "limit_price": null,
  "requires_approval": true,
  "submitted": false
}
```

A UI table with strike/expiry/premium columns will render `—` for all three. Open
item: either `_order_intents` resolves contracts from the option chain using the
tier's delta band and DTE, or `daily_cycle` populates concrete contracts in
`params`. Backend's call.

**3. `order_intents` is empty when halted.** In the verified response above,
mock portfolio state trips the kill-switch (`single-day loss -12.96%`), so intents
are `[]`. If `risk_summary.halted` is true, show the halt reason instead of an
empty table.

`orders_ready` is **always `false`** — there is no auto-submit path anywhere in
the backend.

---

## `POST /api/trade`

Explicit submission. Never call this automatically from an agent run — it
requires a separate, user-initiated approve action.

Validated: `qty` bounded and finite, `limit_price` bounded and finite, `symbol`
regex-checked, OCC option symbols accepted.

```json
{ "symbol": "AAPL", "qty": 1, "side": "sell", "type": "limit", "limit_price": 2.5, "time_in_force": "day" }
```

Rejects NaN/Infinity with `422` (finding S3 — these previously caused HTTP 500).

## `GET /api/trade/orders`

```json
{
  "mode": "mock",
  "orders": [
    {
      "id": "98765432-abcd-efgh-4321-fedcba987654",
      "client_order_id": "alpaca_py_order_zz1",
      "created_at": "2024-06-18T09:30:00Z",
      "submitted_at": "2024-06-18T09:30:00Z"
    }
  ]
}
```

---

## `GET /api/bot/status`

Returns the state of the background autonomous trading scheduler. When
`BOT_AUTONOMOUS_ENABLED=true`, the scheduler auto-starts on backend startup
and fires one immediate cycle, so `run_count` increments without user action.

```json
{
  "running": true,
  "interval_hours": 1.0,
  "autonomous_execution": true,
  "enforce_market_hours": false,
  "is_market_open": false,
  "alpaca_configured": true,
  "run_count": 1,
  "last_run_at": "2026-09-02T15:19:17.000Z",
  "next_run_at": "2026-09-02T16:00:00.000Z",
  "last_error": null,
  "last_result": {
    "run_id": "bot-a1b2c3d4e5f6",
    "mode": "live",
    "halted": false,
    "directives_count": 4,
    "orders_evaluated": 2,
    "orders_submitted": 2,
    "orders_blocked": 0,
    "summary": {
      "status": "completed",
      "executed_orders": []
    }
  }
}
```

---

## `POST /api/bot/start` & `POST /api/bot/stop`

Controls the background scheduler process:

```json
// POST /api/bot/start
{
  "status": "started",
  "message": "Autonomous bot scheduler started (interval: 1.0h, auto_execution: false)",
  "bot": { "running": true, ... }
}
```

---

## `POST /api/bot/config`

Dynamically updates scheduler parameters:

```json
// Request
{
  "interval_hours": 2.0,
  "autonomous_execution": true
}

// Response
{
  "status": "updated",
  "bot": {
    "running": true,
    "interval_hours": 2.0,
    "autonomous_execution": true
  }
}
```

---

## `POST /api/bot/cycle`

Triggers an immediate on-demand autonomous cycle. The scheduler also fires
one automatic cycle on startup when `BOT_AUTONOMOUS_ENABLED=true`.

```json
// Response
{
  "status": "completed",
  "result": {
    "run_id": "bot-f4e3d2c1b0a9",
    "mode": "live",
    "halted": false,
    "directives_count": 4,
    "orders_evaluated": 2,
    "orders_submitted": 0,
    "orders_blocked": 0,
    "summary": {
      "status": "completed",
      "executed_orders": []
    }
  }
}
```

---

## `GET /api/bot/mcp/tools`

Returns the native Model Context Protocol (MCP) tool manifest:

```json
{
  "mcp_version": "2024-11-05",
  "server_name": "autooverlay-ai-agent",
  "server_version": "2.0.0",
  "tools": [
    {
      "name": "run_autonomous_cycle",
      "description": "Trigger an autonomous 7-step investment council cycle..."
    },
    {
      "name": "get_bot_status",
      "description": "Get current status of the autonomous background scheduler..."
    },
    {
      "name": "get_portfolio_summary",
      "description": "Inspect live portfolio equity, cash, and short options..."
    },
    {
      "name": "screen_options_overlay",
      "description": "Screen options overlay candidates for covered calls and CSPs..."
    },
    {
      "name": "evaluate_risk_gate",
      "description": "Run pre-trade risk evaluation against active positions..."
    }
  ]
}
```

---

## Error handling

| Status | Meaning | Frontend should |
|---|---|---|
| 200 + `live_error` | Succeeded on fallback data | Show amber banner with the text |
| 422 | Invalid input | Show validation message; do not retry unchanged |
| 502 | Alpaca failed | Show error; retry is reasonable |
| 500 | Bug | Should not happen — all known paths return 422 |

`AlpacaAPIError` → 502 was added deliberately so live failures surface instead of
silently becoming mock data.

---

## How to verify a field yourself

Never trust a document, including this one, for a field you are about to depend
on:

```bash
curl -s http://localhost:8000/api/council/assess | python3 -m json.tool | head -40
curl -s -X POST http://localhost:8000/api/agent/run \
     -H 'Content-Type: application/json' -d '{}' | python3 -m json.tool
curl -s http://localhost:8000/api/bot/status | python3 -m json.tool
```

The route source is the contract: `backend/app/routes/*.py`.
