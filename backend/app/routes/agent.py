"""Recommendation-only agent orchestration endpoint."""

from __future__ import annotations

import math
import os
import time
from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..adapters.options import normalize_snapshot, parse_occ
from ..alpaca_client import AlpacaAPIError, AlpacaClient, is_configured
from ..auth import get_current_user, get_session_id, require_csrf
from .council import CouncilCycleRequest, council_cycle
from .strategy import _active_config, _active_strategy_config

router = APIRouter()

_active_run_cache: dict[str, dict] = {}
RUN_TTL_SECONDS = 30 * 60


def _clean_expired_runs() -> None:
    now = time.time()
    expired = [
        run_id
        for run_id, payload in _active_run_cache.items()
        if now - payload.get("cached_at", 0) > RUN_TTL_SECONDS
    ]
    for run_id in expired:
        _active_run_cache.pop(run_id, None)


@router.get("/agent/run/{run_id}")
async def get_agent_run(
    run_id: str,
    session_id: str | None = Depends(get_session_id),
) -> dict:
    _clean_expired_runs()
    payload = _active_run_cache.get(run_id)
    if not payload:
        raise HTTPException(status_code=404, detail="agent run not found")
    if session_id and payload.get("session_id") not in (session_id, None):
        raise HTTPException(status_code=403, detail="forbidden")
    return payload.get("data", {})


@router.post("/agent/run/order")
async def reject_order_execution() -> dict:
    raise HTTPException(status_code=404, detail="not found")


def _pick_option_contract(symbol: str | None, params: dict) -> dict | None:
    if not symbol:
        return None
    delta_min, delta_max, max_dte = _tier_bands(params)
    if delta_min is None or delta_max is None or max_dte is None:
        return None
    if not is_configured():
        return None
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
        snapshots = []
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(AlpacaClient().get_option_snapshots, symbol)
            snapshots = future.result(timeout=max(6.0, 0.5))
    except (AlpacaAPIError, ValueError, TypeError, FuturesTimeoutError):
        snapshots = []
    if not snapshots:
        return None
    today = datetime.now(timezone.utc).date()
    candidates: list[dict] = []
    for snap in snapshots:
        # normalize_snapshot returns None for a malformed OCC symbol or a
        # non-mapping payload rather than raising, so one bad contract cannot
        # abort contract selection for the whole directive.
        quote = normalize_snapshot(str(snap.get("symbol") or ""), snap)
        if quote is None or quote.underlying != symbol.upper():
            continue
        # Ensure contract matches strategy option type (Call for Covered Call, Put for Cash-Secured Put)
        expected_type = params.get("expected_option_type")
        if not expected_type:
            strats = params.get("strategy_allowed") or []
            if "COVERED_CALL" in strats and "CASH_SECURED_PUT" not in strats:
                expected_type = "call"
            elif "CASH_SECURED_PUT" in strats and "COVERED_CALL" not in strats:
                expected_type = "put"
        if expected_type and quote.option_type != expected_type:
            continue

        # A missing delta excludes the contract. It must never be treated as
        # 0.0, which would pass any delta band trivially.
        if quote.delta is None:
            continue
        abs_delta = abs(quote.delta)
        if not (delta_min <= abs_delta <= delta_max):
            continue
        dte = quote.days_to_expiry(today)
        if not (0 < dte <= max_dte):
            continue
        if quote.bid is None and quote.ask is None:
            continue
        if params.get("use_midpoint", False) and quote.bid is not None and quote.ask is not None and quote.bid > 0 and quote.ask > 0:
            limit_price = round((quote.bid + quote.ask) / 2.0, 2)
        else:
            limit_price = round((quote.bid or quote.ask or 0.0) + 0.05, 2)
        candidates.append({
            "symbol": symbol,
            "option_symbol": quote.option_symbol,
            "delta": quote.delta,
            "dte": dte,
            "limit_price": limit_price,
            "bid": quote.bid,
            "ask": quote.ask,
        })
    if not candidates:
        return None
    candidates.sort(key=lambda c: (abs(abs(c["delta"]) - ((delta_min + delta_max) / 2)), c["dte"]))
    return candidates[0]


def _tier_bands(params: dict) -> tuple[float | None, float | None, int | None]:
    band = params.get("delta_band") or params.get("delta_min") or params.get("delta_max")
    if isinstance(band, list) and len(band) == 2:
        try:
            delta_min = float(band[0])
            delta_max = float(band[1])
        except (TypeError, ValueError):
            return None, None, None
    else:
        try:
            delta_min = float(params.get("delta_min", 0))
            delta_max = float(params.get("delta_max", 0))
        except (TypeError, ValueError):
            return None, None, None
    try:
        max_dte = int(params.get("max_dte", 0))
    except (TypeError, ValueError):
        max_dte = 0
    if delta_min <= 0 or delta_max <= 0 or delta_min >= delta_max or max_dte <= 0:
        return None, None, None
    return delta_min, delta_max, max_dte


def _safe_float(value: object) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _occ_expiration(symbol: str) -> date:
    """Expiration date from an OCC option symbol.

    This used to call ``datetime.date(...)`` where ``datetime`` is the *class*,
    not the module, so it raised ``TypeError: descriptor 'date' ...`` on every
    call. The call site in ``_pick_option_contract`` only caught ``ValueError``,
    so ``POST /api/agent/run`` returned HTTP 500 the moment live credentials and
    one option snapshot were present (docs/BRIEF-BACKEND-V2.md D3).

    Retained as a thin wrapper over the single OCC parser in the adapter.
    """
    return parse_occ(symbol).expiration


def _order_intents(directives: list[dict]) -> list[dict]:
    intents = []
    for directive in directives:
        if directive.get("action") != "INITIATE":
            continue
        params = directive.get("params") or {}
        strategies = params.get("strategy_allowed") or []
        strategy = strategies[0] if strategies else params.get("strategy")
        if not strategy:
            continue
        contracts = params.get("contracts") or params.get("size") or 1
        if strategy == "COVERED_CALL":
            params["expected_option_type"] = "call"
        elif strategy == "CASH_SECURED_PUT":
            params["expected_option_type"] = "put"
        option = _pick_option_contract(directive.get("symbol"), params)
        option_symbol = option["option_symbol"] if option else params.get("option_symbol")
        limit_price = option["limit_price"] if option else params.get("limit_price")
        intent = {
            "action": "SELL_TO_OPEN",
            "strategy": strategy,
            "symbol": directive.get("symbol"),
            "option_symbol": option_symbol,
            "contracts": contracts,
            "qty": params.get("qty", contracts),
            "side": "sell",
            "type": "limit" if limit_price is not None else "market",
            "time_in_force": "day",
            "limit_price": limit_price,
            "requires_approval": os.getenv("ALPACA_REQUIRE_APPROVAL", "true").lower() != "false",
            "submitted": False,
        }
        if os.getenv("BOT_EXECUTE_ORDERS", "false").lower() == "true":
            intent["submitted"] = _submit_order(intent)
            intent["requires_approval"] = False
        intents.append(intent)
    return intents


def _submit_order(intent: dict) -> bool:
    try:
        client = AlpacaClient()
        order_params = {
            "symbol": intent["option_symbol"],
            "qty": intent["qty"],
            "side": "sell",
            "type": "limit" if intent.get("limit_price") else "market",
            "time_in_force": "day",
        }
        if intent.get("limit_price"):
            order_params["limit_price"] = intent["limit_price"]
        client.submit_order(**order_params)
        return True
    except Exception:
        return False


class AgentRunRequest(BaseModel):
    """Optional inputs forwarded to the existing council daily cycle."""

    candidates: list[str] | None = Field(default=None, max_length=50)
    cash_override: float | None = Field(default=None, ge=0)
    portfolio_state_overrides: dict | None = None


@router.post("/agent/run")
async def agent_run(
    req: AgentRunRequest,
    _user: dict = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
    session_id: str | None = Depends(get_session_id),
) -> dict:
    """Run analysis and return recommendations without submitting orders."""
    cycle = await council_cycle(CouncilCycleRequest(
        candidates=req.candidates,
        cash_override=req.cash_override,
        portfolio_state_overrides=req.portfolio_state_overrides,
    ))
    recommendations = list(cycle.get("directives", []))
    order_intents = [] if cycle.get("halted") else _order_intents(recommendations)
    reasoning_trace = [
        trace
        for recommendation in recommendations
        for trace in recommendation.get("reasoning_trace", [])
    ]
    risk_summary = {
        "halted": cycle.get("halted", False),
        "kill_switch": cycle.get("kill_switch", {}),
        "portfolio_state": cycle.get("portfolio_state", {}),
        "blocked_entries": len(cycle.get("blocked_entries", {})),
    }
    run_id = f"run-{uuid4().hex}"
    response = {
        "run_id": run_id,
        "status": "completed",
        "mode": "live" if is_configured() else "mock",
        "orders_ready": os.getenv("BOT_EXECUTE_ORDERS", "false").lower() == "true",
        "order_intents": order_intents,
        "recommendations": recommendations,
        "risk_summary": risk_summary,
        "reasoning_trace": reasoning_trace,
        "cycle": cycle,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    _active_run_cache[run_id] = {
        "session_id": session_id,
        "data": response,
        "cached_at": time.time(),
    }
    return response
