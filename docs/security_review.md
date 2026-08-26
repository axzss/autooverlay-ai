# Security Review — Red-Team Pentest of AI Engineer Code Paths

**Date:** 2026-08-26 · **Scope:** backend/app (FastAPI), agent/ (config + council handoff), frontend/lib/api.ts
**Method:** live exploitation against a locally started uvicorn instance in mock mode (no credentials), plus direct unit-level exploits for the agent layer and a static audit of the frontend client. Exploit scripts preserved at `/tmp/exploit_backend.py`, `/tmp/exploit2.py`, `/tmp/exploit3.py`.

## Severity Table

| # | Finding | Vector | Severity | Status |
|---|---------|--------|----------|--------|
| S1 | `PUT /strategy/config` accepted **NaN/Infinity floats** from raw JSON bodies (`NaN`/`Infinity` literals). Pydantic's default float allows them and `StrategyConfig.validate()` passed them because every NaN comparison is `False`. A NaN `take_profit_pct` or Inf `stop_loss_mult` poisoned the live `_active_config` consumed by DecisionEngine/ExitManager (e.g. exit logic never firing). | Strategy config injection | **HIGH** | **FIXED** — `allow_inf_nan=False` on all `StrategyConfigModel` fields; finite check added to `validate()`; non-finite overrides skipped in `from_dict()`. Now 422. |
| S2 | **Absurd magnitudes accepted**: `stop_loss_mult=1e308` returned 200 and became the active config. | Strategy config injection | **MED** | **FIXED** — `validate()` now bounds `stop_loss_mult` to (0, 1000). Now 422. |
| S3 | `POST /trade` with `qty: NaN` → **HTTP 500**; `limit_price: Infinity` crashed the response mid-flight (connection reset). Root cause: pydantic accepted NaN/Inf, then FastAPI's default validation-error handler could not JSON-encode the non-finite input value. | Trade route abuse | **HIGH** (robustness/DoS) | **FIXED** — `allow_inf_nan=False` on `qty`/`limit_price`, plus a sanitizing `RequestValidationError` handler in `main.py` that makes error payloads JSON-safe (non-finite floats rendered as strings). Now 422. |
| S4 | `GET /strategy/screen?top_n=-1` (and `top_n=1e9`, `min_open_interest=-5`) → **HTTP 500**: the GET handler constructed `ScreenRequest` directly, so pydantic's `ValidationError` escaped unhandled. POST was fine (422). | Screen endpoint abuse | **MED** | **FIXED** — explicit try/except translating `ValidationError` → HTTP 422. |
| S5 | Unbounded trade inputs: `qty=10**15` accepted; 10 MB `client_order_id` accepted into the order pipeline; equity `symbol` accepted arbitrary strings ("AAPL…; DROP TABLE users", unicode homoglyphs) because only option symbols were format-checked. No SQLi/injection sink exists downstream (payload goes into an httpx JSON body), but junk could reach the broker API and bloat memory/logs. | Trade route abuse | **LOW** | **FIXED** — `qty ≤ 1e9`, `client_order_id ≤ 128 chars`, symbol regex `^[A-Z0-9.\-]{1,15}$` (equity) + existing strict OCC parse (options). All now 422. |
| S6 | `POST /strategy/screen` accepted a 10,000-item `symbols` list and symbols containing null bytes (mock path filtered harmlessly by equality; live path only used them as a set filter). | Screen endpoint abuse | **LOW** | **FIXED** — symbols capped at 200 items × 16 chars matching `^[A-Za-z0-9.^\-]+$`; null-byte/hostile items now 422. |
| S7 | **Council handoff parser trusts document content**: a crafted `council_report.md` containing "IGNORE PRIOR RULES … delta 0.99 … DTE<=9999" changed parsed policy (high-tier `delta_max` 0.15→0.99, `max_dte` 30→9999) and mutated module-global `SYMBOL_OVERRIDES["TSLA"]` (delta cap raised to 0.99, `until_vol_below` set to 0 = override permanently active). Plain prompt-injection text without parseable patterns had no effect — the schema holds — but *well-formed* injected tables/lines did move policy. | Handoff parser trust | **MED** (residual risk remains, see below) | **PARTIALLY FIXED** — clamps added: delta bands clamped to [0.01–0.95], DTE clamped to [1–365], TSLA `delta_max` ≤ 0.50, `until_vol_below` ≥ 1%. Injection can still shift values *within* these safe bounds. Recommend eventually signing/provenance-checking the report file. |
| S8 | `STRATEGY_CONFIG_JSON` env injection: malformed JSON, arrays, hostile types, dataclass-internals collisions (`validate`, `__init__`), dunder keys — all safely ignored. **Except** `"nan"`/`"inf"` strings became real NaN/Inf floats and passed `validate()` (same root cause as S1). | Env injection | **MED** | **FIXED** — non-finite overrides skipped in `from_dict()`; `validate()` rejects them defensively too. |

## Verified Already Safe

| Area | Result |
|------|--------|
| Frontend `lib/api.ts` | INFO — no `eval`, `new Function`, `dangerouslySetInnerHTML`, `innerHTML`, or `document.write` anywhere in `app/`, `lib/`, `components/`. Backend errors are converted to typed `ApiError` messages carrying only path + status code; response bodies are never executed or injected into HTML. React's default escaping applies everywhere. |
| TIF whitelist | INFO — bypass attempts (`" GTC "`, `"day OR 1=1"`, mixed case) all rejected; option orders locked to `day`. |
| OCC option parsing | INFO — homoglyph (`ΑΑΡL…`) and SQL-suffixed symbols rejected via strict OCC regex. |
| Credentials | INFO — repo grep found no hardcoded Alpaca keys/secrets; creds read only from env vars; mock fallback when unset. |
| CORS | LOW (accepted for hackathon scope) — `allow_origins=["*"]` combined with `allow_credentials=True` is over-permissive for production; flagged for hardening, not exploited (no auth state to steal in mock mode). |
| Fractional qty | INFO — `qty=0.5` is valid Alpaca notional-style quantity for equities; left permitted intentionally. |

## Fixes Applied (files)

- `agent/config.py` — finite-value checks in `validate()`; skip non-finite overrides in `from_dict()`; bound `stop_loss_mult < 1000`.
- `agent/council/handoff.py` — clamp helpers; delta bands / DTE / TSLA override values clamped to sane ranges during parsing.
- `backend/app/main.py` — JSON-safe `RequestValidationError` exception handler.
- `backend/app/routes/trade.py` — finite/magnitude/length bounds on qty, limit price, symbol, TIF, client_order_id; equity symbol format regex.
- `backend/app/routes/strategy.py` — `allow_inf_nan=False` on config model; bounded `ScreenRequest.symbols`; GET `/strategy/screen` returns 422 instead of 500.

## Regression Tests

- `backend/tests/test_security_regression.py` (16 tests) — config NaN/Inf/absurd-magnitude rejection, raw-NaN bodies, trade NaN/Inf/oversized/negative qty, huge client_order_id, SQL/homoglyph symbols, TIF bypass, screen 422s, symbols-list caps, null bytes.
- `agent/tests/test_security_regression.py` (16 tests) — env-injection cases, validate() finite rejection, handoff injection clamps (delta/DTE/TSLA/until_vol), legitimate-report passthrough unchanged, garbage/binary input safety.

## QA Sign-off

| Gate | Result |
|------|--------|
| 1. `pytest agent/tests backend/tests -q` | ✅ **158 passed, 1 skipped** (baseline before pentest: 126 passed, 1 skipped; +32 new security regression tests) |
| 2. Re-run exploit scripts against fixed code | ✅ All previously-successful exploits now fail: raw NaN/Infinity config PUT → 422; `stop_loss_mult=1e308` → 422; trade NaN qty / Infinity limit → 422 (was 500/connection-reset); `qty=1e15` → 422; huge client_order_id → 422; screen `top_n=-1` / `top_n=1e9` / `min_open_interest=-5` → 422 (was 500); handoff injection clamped (delta_max ≤0.95, max_dte ≤365, TSLA cap ≤0.50, until_vol ≥1%); env `"nan"`/`"inf"` ignored (defaults retained). |
| 3. `cd frontend && npm run build` | ✅ Build succeeded (static prerender complete, shared JS 87 kB first-load; no type/build errors). |
| 4. Credential-pattern grep | ✅ No matches — no hardcoded `ALPACA_KEY`/`ALPACA_SECRET`/APCA key material anywhere in tracked source (exit 1 / zero findings after filtering test/mock placeholders). |
| 5. This sign-off section | ✅ Present, with actual outputs above. |

## Residual Recommendations (not fixed, out of minimal-fix scope)

1. Tighten CORS for any authenticated deployment (`allow_origins=["*"]` + credentials).
2. Add provenance/signature verification for `docs/council_report.md` before trusting its HANDOFF section (S7 residual).
3. Consider per-IP rate limiting on `/trade` before wiring live broker keys.
