"""Recommendation-only agent orchestration endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..alpaca_client import is_configured
from .council import CouncilCycleRequest, council_cycle

router = APIRouter()


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
        intent = {
            "action": "SELL_TO_OPEN",
            "strategy": strategy,
            "symbol": directive.get("symbol"),
            "option_symbol": params.get("option_symbol"),
            "contracts": contracts,
            "qty": params.get("qty", contracts),
            "side": "sell",
            "type": "limit" if params.get("limit_price") is not None else "market",
            "time_in_force": "day",
            "limit_price": params.get("limit_price"),
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
