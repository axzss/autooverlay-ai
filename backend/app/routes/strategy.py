"""GET/POST /strategy/screen — overlay candidates (covered calls / cash-secured puts).

Live mode: scans held equity positions and pulls option snapshots from the
Alpaca data API to build covered-call candidates. Falls back to bundled mock
candidates when credentials are missing or live data fails.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..alpaca_client import AlpacaClient, is_configured, parse_occ_symbol
from ..mock_data import mock_positions, mock_screen_candidates

router = APIRouter()


# ---------------------------------------------------------------------------
# Strategy configuration (GET/PUT /strategy/config)
#
# Hackathon scope: the active config lives as an in-process module-level
# singleton shared by every request. It is seeded from StrategyConfig()
# which honors the optional STRATEGY_CONFIG_JSON env var.
# ---------------------------------------------------------------------------
from agent.config import StrategyConfig  # noqa: E402
from agent.decision_engine import DecisionEngine  # noqa: E402

_active_config = StrategyConfig()


class StrategyConfigModel(BaseModel):
    take_profit_pct: float
    stop_loss_mult: float
    roll_delta: float
    roll_min_dte: int
    delta_min: float
    delta_max: float
    dte_min: int
    dte_max: int
    max_concentration_pct: float
    min_cash_reserve_pct: float


@router.get("/strategy/config")
async def get_strategy_config() -> dict:
    return {"config": _active_config.to_dict(), "valid": not _active_config.validate()}


@router.put("/strategy/config")
async def put_strategy_config(body: StrategyConfigModel) -> dict:
    global _active_config
    candidate = StrategyConfig.from_dict(body.model_dump())
    errors = candidate.validate()
    if errors:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail={"errors": errors})
    _active_config = candidate
    return {"status": "ok", "config": _active_config.to_dict()}


class ScreenRequest(BaseModel):
    symbols: Optional[List[str]] = Field(default=None, description="Restrict scan to these underlyings")
    min_open_interest: int = Field(default=0, ge=0)
    max_annualized_return: float = Field(default=10.0, gt=0, description="Sanity cap on annualized yield")
    top_n: int = Field(default=5, ge=1, le=25)
    full: bool = Field(default=True, description="Run the agent DecisionEngine and enrich candidates")


def _candidate_from_snapshot(pos_symbol: str, pos_qty: float, snap: dict) -> dict | None:
    """Turn an Alpaca options snapshot into a covered-call candidate."""
    symbol = snap.get("symbol") or ""
    details = snap.get("details") or {}
    quote = snap.get("latest_quote") or {}
    greeks = snap.get("greeks") or {}
    if details.get("type") != "call":
        return None
    strike = float(details.get("strike_price", 0) or 0)
    bid = float(quote.get("bid_price", 0) or 0)
    ask = float(quote.get("ask_price", 0) or 0)
    mid = (bid + ask) / 2 if ask else bid
    underlying_price = float(snap.get("underlying_asset", {}).get("price", 0) or 0)
    oi = int(details.get("open_interest", 0) or 0)
    exp = details.get("expiration_date") or ""
    try:
        dte = max((datetime.fromisoformat(exp).replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days, 0)
    except ValueError:
        return None
    if mid <= 0 or dte == 0 or underlying_price <= 0:
        return None
    contracts = math.floor(float(pos_qty) / 100.0)
    per_contract_premium = mid * 100
    annualized = ((mid / underlying_price) * (365.0 / dte)) if dte else 0
    prob_itm = max(0.0, min(1.0, 1 - abs(getattr(greeks, "delta", 0) or greeks.get("delta", 0) or 0)))
    rec = (
        "INITIATE_POSITION" if 0.02 <= annualized <= 0.45 and oi >= 100
        else "MONITOR_CLOSELY" if annualized > 0.45
        else "HOLD_POSITION"
    )
    return {
        "symbol": pos_symbol,
        "position_qty": pos_qty,
        "underlying_price": underlying_price,
        "contracts_available": contracts,
        "option_symbol": symbol,
        "strike_price": strike,
        "expiration_date": exp,
        "days_to_expiry": dte,
        "bid": bid,
        "ask": ask,
        "last_price": mid,
        "open_interest": oi,
        "implied_volatility": snap.get("implied_volatility"),
        "delta": greeks.get("delta") if isinstance(greeks, dict) else None,
        "theta": greeks.get("theta") if isinstance(greeks, dict) else None,
        "premium_received_per_share": round(mid, 4),
        "total_premium_received": round(per_contract_premium * contracts, 2),
        "annualized_return_rate": round(annualized, 4),
        "probability_itm": round(prob_itm, 3),
        "recommendation": rec,
        "reasoning": f"Covered call on held {pos_symbol}: {contracts} contract(s), {annualized:.1%} annualized at {strike:.0f} strike.",
    }


@router.get("/strategy/screen")
async def screen_strategies_get(
    symbols: Optional[str] = None,
    min_open_interest: int = 0,
    top_n: int = 5,
    full: bool = True,
) -> dict:
    req = ScreenRequest(
        symbols=[s.strip().upper() for s in symbols.split(",")] if symbols else None,
        min_open_interest=min_open_interest,
        top_n=top_n,
        full=full,
    )
    return await _screen(req)


@router.post("/strategy/screen")
async def screen_strategies_post(req: ScreenRequest) -> dict:
    return await _screen(req)


def _match_key(cand: dict) -> tuple:
    return (
        cand.get("option_symbol") or "",
        cand.get("symbol", ""),
        float(cand.get("strike_price") or 0),
        cand.get("expiration_date") or "",
    )


def _fallback_enrichment(cand: dict, engine: DecisionEngine) -> dict:
    """Score a candidate the engine filtered out (lots/DTE/delta bounds).

    Still returns a real composite risk score plus an explicit trace of why
    it did not surface as a ranked recommendation.
    """
    dte = int(cand.get("days_to_expiry") or 0)
    delta = abs(float(cand.get("delta") or 0))
    iv = float(cand.get("implied_volatility") or 0)
    underlying = float(cand.get("underlying_price") or 0)
    strike = float(cand.get("strike_price") or 0)
    ann_yield = float(cand.get("annualized_return_rate") or 0)
    risk_score = engine.cc._risk_score(
        iv=iv, delta=delta, dte=dte, underlying=underlying,
        strike=strike, strike_above_basis=None,
    ) if underlying > 0 and strike > 0 else 50
    recommendation = engine.cc._recommendation(ann_yield, risk_score)
    qty = float(cand.get("position_qty") or 0)
    trace = [
        f"holding check: {qty:g} shares of {cand.get('symbol', '')} "
        f"= {int(qty) // 100} full lot(s) — "
        f"{'✓' if qty >= 100 else '✗ below one full lot'}",
        f"DTE {dte} vs engine band {engine.cc.min_dte}-{engine.cc.max_dte} — "
        f"{'✓' if engine.cc.min_dte <= dte <= engine.cc.max_dte else '✗ outside band'}",
        f"delta {delta:.2f} vs band {engine.cc.min_delta:.2f}-"
        f"{engine.cc.MAX_DELTA:.2f} — "
        f"{'✓' if engine.cc.min_delta <= delta <= engine.cc.MAX_DELTA else '✗ outside band'}",
        f"risk score {risk_score}/100 from IV, delta, DTE gamma, cushion",
        f"verdict: {recommendation}",
    ]
    rationale = (
        f"{cand.get('symbol', '')}: covered call at ${strike:.2f}, {dte} DTE, "
        f"{ann_yield * 100:.1f}% annualized. Risk score {risk_score}/100. "
        f"=> {recommendation}"
    )
    return {
        "risk_score": int(risk_score),
        "action": recommendation,
        "rationale": rationale,
        "reasoning_trace": trace,
    }


def _enrich_with_engine(
    candidates: List[dict], positions: List[dict]
) -> tuple[List[dict], Optional[dict]]:
    """Run DecisionEngine.evaluate over candidates + positions and merge its
    risk_score / action / rationale / reasoning_trace into each candidate.

    Returns (enriched_candidates, portfolio_context).
    """
    engine = DecisionEngine(config=_active_config)
    try:
        result = engine.evaluate(
            [],  # no CSP chain in this endpoint — covered calls only
            list(candidates),
            list(positions),
            open_option_positions=[],  # mock/live-safe: nothing to exit yet
        )
    except Exception:
        return candidates, None

    by_key: dict = {}
    for rec in result.get("cc_results", []):
        key = (
            rec.get("option_symbol") or "",
            rec.get("symbol", ""),
            float(rec.get("strike_price") or 0),
            rec.get("expiration_date") or "",
        )
        by_key[key] = rec

    enriched: List[dict] = []
    for cand in candidates:
        rec = by_key.get(_match_key(cand))
        if rec is not None:
            cand = {
                **cand,
                "risk_score": rec["risk_score"],
                "action": rec["recommendation"],
                "rationale": rec["rationale"],
                "reasoning_trace": rec.get("reasoning_trace", []),
            }
        else:
            cand = {**cand, **_fallback_enrichment(cand, engine)}
        enriched.append(cand)

    portfolio_context = result.get("portfolio_context")
    return enriched, portfolio_context


async def _screen(req: ScreenRequest) -> dict:
    if not is_configured():
        cands = mock_screen_candidates()
        if req.symbols:
            cands = [c for c in cands if c.get("symbol") in req.symbols]
        cands = [c for c in cands if c.get("open_interest", 0) >= req.min_open_interest]
        cands = cands[: req.top_n]
        response: dict = {"mode": "mock", "strategy": "covered_call", "count": len(cands), "candidates": cands}
        if req.full:
            positions = [p for p in mock_positions() if p.get("asset_class") == "us_equity"]
            enriched, portfolio_context = _enrich_with_engine(cands, positions)
            response["candidates"] = enriched
            if portfolio_context is not None:
                response["portfolio_context"] = portfolio_context
        return response

    client = AlpacaClient()
    try:
        positions = [p for p in client.get_positions() if p.get("asset_class") == "us_equity"]
    except RuntimeError as exc:
        cands = mock_screen_candidates()
        response = {"mode": "error", "detail": str(exc), "strategy": "covered_call",
                    "count": len(cands), "candidates": cands}
        if req.full:
            mock_pos = [p for p in mock_positions() if p.get("asset_class") == "us_equity"]
            enriched, portfolio_context = _enrich_with_engine(cands, mock_pos)
            response["candidates"] = enriched
            if portfolio_context is not None:
                response["portfolio_context"] = portfolio_context
        return response

    wanted = set(req.symbols or [])
    candidates: List[dict] = []
    for p in positions:
        sym = p.get("symbol", "")
        if wanted and sym not in wanted:
            continue
        try:
            snaps = client.get_option_snapshots(sym)
        except RuntimeError:
            continue
        for snap in snaps:
            cand = _candidate_from_snapshot(sym, float(p.get("qty", 0) or 0), snap)
            if cand and cand["open_interest"] >= req.min_open_interest \
                    and cand["annualized_return_rate"] <= req.max_annualized_return:
                candidates.append(cand)

    candidates.sort(key=lambda c: c.get("annualized_return_rate", 0), reverse=True)
    candidates = candidates[: req.top_n]

    response = {"mode": "live", "strategy": "covered_call", "count": len(candidates), "candidates": candidates}
    if req.full:
        enriched, portfolio_context = _enrich_with_engine(candidates, positions)
        response["candidates"] = enriched
        if portfolio_context is not None:
            response["portfolio_context"] = portfolio_context
    return response
