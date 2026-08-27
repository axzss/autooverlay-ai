"""Reusable response envelopes for backend routes."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    detail: str


class PortfolioResponse(BaseModel):
    mode: str
    account_info: dict | None = None
    positions: list[dict] | None = None


class CandidateResponse(BaseModel):
    mode: str
    live_error: str | None = None
    strategy: str
    count: int
    candidates: list[dict]


class CouncilResponse(BaseModel):
    mode: str
    count: int
    assessments: list[dict]


class AgentRunResponse(BaseModel):
    run_id: str
    status: str
    mode: str
    orders_ready: bool
    order_intents: list[dict]
    recommendations: list[dict]
    risk_summary: dict
    reasoning_trace: list[str]
    cycle: dict
    completed_at: str
