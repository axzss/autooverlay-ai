"""Recommendation-only agent orchestration endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..alpaca_client import is_configured
from .council import CouncilCycleRequest, council_cycle

router = APIRouter()


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
        "recommendations": recommendations,
        "risk_summary": risk_summary,
        "reasoning_trace": reasoning_trace,
        "cycle": cycle,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
