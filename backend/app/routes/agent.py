"""Recommendation-only agent orchestration endpoint."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..alpaca_client import AlpacaAPIError, AlpacaClient, is_configured
from .council import CouncilCycleRequest, council_cycle

router = APIRouter()


def _pick_option_contract(symbol: str | None, params: dict) -> dict | None:
    if not symbol:
        return None
    delta_min, delta_max, max_dte = _tier_bands(params)
    if None in (delta_min, delta_max, max_dte):
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
        symbol_in = str(snap.get("symbol") or "").upper()
        if not symbol_in.startswith(symbol.upper()):
            continue
        greeks = snap.get("greeks") or {}
        delta = _safe_float(greeks.get("delta"))
        if delta is None:
            continue
        abs_delta = abs(float(delta))
        if not (delta_min <= abs_delta <= delta_max):
            continue
        try:
            exp = _occ_expiration(symbol_in)
        except ValueError:
            continue
        dte = (exp - today).days
        if not (0 < dte <= max_dte):
            continue
        bid = _safe_float(snap.get("bid_price"))
        ask = _safe_float(snap.get("ask_price"))
        if bid is None and ask is None:
            continue
        limit_price = round((bid or ask or 0.0) + 0.05, 2)
        candidates.append({
            "symbol": symbol,
            "option_symbol": symbol_in,
            "delta": delta,
            "dte": dte,
            "limit_price": limit_price,
            "bid": bid,
            "ask": ask,
        })
    if not candidates:
        return None
    candidates.sort(key=lambda c: (abs(c["delta"] - ((delta_min + delta_max) / 2)), c["dte"]))
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


def _occ_expiration(symbol: str) -> datetime.date:
    m = re.match(r"^([A-Z.]{1,6})(\d{6})([CP])(\d{8})$", symbol.upper().replace(" ", ""))
    if not m:
        raise ValueError(symbol)
    _, date, _, _ = m.groups()
    return datetime.date(2000 + int(date[0:2]), int(date[2:4]), int(date[4:6]))


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
            "requires_approval": True,
            "submitted": False,
        }
        intents.append(intent)
    return intents


class AgentRunRequest(BaseModel):
    """Optional inputs forwarded to the existing council daily cycle."""

    candidates: list[str] | None = Field(default=None, max_length=50)
    cash_override: float | None = Field(default=None, ge=0)
    portfolio_state_overrides: dict | None = None


@router.post("/agent/run")
async def agent_run(req: AgentRunRequest) -> dict:
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
    return {
        "run_id": f"run-{uuid4().hex}",
        "status": "completed",
        "mode": "live" if is_configured() else "mock",
        "orders_ready": False,
        "order_intents": order_intents,
        "recommendations": recommendations,
        "risk_summary": risk_summary,
        "reasoning_trace": reasoning_trace,
        "cycle": cycle,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
