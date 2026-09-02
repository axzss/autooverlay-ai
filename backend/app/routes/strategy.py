"""GET/POST /strategy/screen — overlay candidates (covered calls / cash-secured puts).

Live mode: scans held equity positions and pulls option snapshots from the
Alpaca data API to build covered-call candidates. Falls back to bundled mock
candidates when credentials are missing or live data fails.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, constr

from ..auth import get_current_user, require_csrf
from ..adapters.options import OptionQuote, normalize_snapshot
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

_active_config = StrategyConfig.from_env()


def _active_strategy_config() -> StrategyConfig:
    """Return the currently active strategy configuration singleton."""
    return _active_config



class StrategyConfigModel(BaseModel):
    # Security: reject NaN/Infinity outright at parse time (raw-JSON bodies can
    # smuggle them past httpx-level checks); they previously flowed into
    # validate() where NaN comparisons are all False.
    take_profit_pct: float = Field(..., allow_inf_nan=False)
    stop_loss_mult: float = Field(..., allow_inf_nan=False)
    roll_delta: float = Field(..., allow_inf_nan=False)
    roll_min_dte: int
    delta_min: float = Field(..., allow_inf_nan=False)
    delta_max: float = Field(..., allow_inf_nan=False)
    dte_min: int
    dte_max: int
    max_concentration_pct: float = Field(..., allow_inf_nan=False)
    min_cash_reserve_pct: float = Field(..., allow_inf_nan=False)


@router.get("/strategy/config")
async def get_strategy_config() -> dict:
    return {"config": _active_config.to_dict(), "valid": not _active_config.validate()}


@router.put("/strategy/config")
async def put_strategy_config(
    body: StrategyConfigModel,
    _user: dict = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> dict:
    global _active_config
    candidate = StrategyConfig.from_dict(body.model_dump())
    errors = candidate.validate()
    if errors:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail={"errors": errors})
    _active_config = candidate
    return {"status": "ok", "config": _active_config.to_dict()}


class ScreenRequest(BaseModel):
    # Security bounds: cap the symbols list (length + item size) so a hostile
    # client cannot push unbounded payloads into the scan pipeline.
    symbols: Optional[List[constr(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9.^\-]+$")]] = Field(
        default=None, description="Restrict scan to these underlyings", max_length=200,
    )
    min_open_interest: int = Field(default=0, ge=0)
    max_annualized_return: float = Field(default=10.0, gt=0, description="Sanity cap on annualized yield")
    top_n: int = Field(default=5, ge=1, le=25)
    full: bool = Field(default=True, description="Run the agent DecisionEngine and enrich candidates")


def _candidate_from_snapshot(
    pos_symbol: str,
    pos_qty: float,
    snap: dict,
    underlying_price: float | None = None,
) -> dict | None:
    """Turn an Alpaca options snapshot into a covered-call candidate.

    This used to read ``snap["details"]["type"]``, ``details.strike_price``,
    ``latest_quote.bid_price`` and ``underlying_asset.price`` — none of which
    Alpaca sends in a snapshots payload. Every candidate was therefore dropped
    at the first line (docs/BRIEF-BACKEND-V2.md D2). All broker-field access now
    goes through the options adapter; strike and expiry come from the OCC
    symbol, which is always present.

    ``underlying_price`` comes from the held position when the caller has it,
    because the snapshots feed does not carry one.
    """
    quote = normalize_snapshot(str(snap.get("symbol") or ""), snap)
    if quote is None or quote.option_type != "call":
        return None
    price = underlying_price if underlying_price is not None else _underlying_price(snap)
    return _candidate_from_quote(pos_symbol, pos_qty, quote, price)


def _position_price(position: dict) -> float | None:
    """Derive a per-share price from a held position, or None.

    Prefers Alpaca's ``current_price``; falls back to market_value / qty. Never
    returns 0.0 — a zero denominator silently zeroes every annualized yield.
    """
    direct = _safe_positive(position.get("current_price"))
    if direct is not None:
        return direct
    market_value = _safe_positive(position.get("market_value"))
    qty = _safe_positive(position.get("qty"))
    if market_value is not None and qty is not None:
        return market_value / qty
    return _safe_positive(position.get("avg_entry_price"))


def _underlying_price(snap: dict) -> float | None:
    """Underlying price if the payload happens to carry one, else None.

    The snapshots endpoint does not include it; the option *chain* endpoint may.
    Never defaults to 0.0 — a zero underlying silently zeroes the annualized
    yield of every candidate.
    """
    for container_key in ("underlyingAsset", "underlying_asset"):
        container = snap.get(container_key)
        if isinstance(container, dict):
            price = _safe_positive(container.get("price"))
            if price is not None:
                return price
    return _safe_positive(snap.get("underlying_price"))


def _safe_positive(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _candidate_from_quote(
    pos_symbol: str,
    pos_qty: float,
    quote: OptionQuote,
    underlying_price: float | None,
) -> dict | None:
    """Build a covered-call candidate dict from a normalized OptionQuote."""
    premium = quote.price
    dte = quote.days_to_expiry()
    if premium is None or dte <= 0:
        return None

    contracts = math.floor(float(pos_qty) / 100.0)
    per_contract_premium = premium * 100

    # Annualized yield needs the underlying price. When the feed does not carry
    # one we report None rather than inventing a denominator — a fabricated
    # yield is worse than an absent one, and the recommendation below degrades
    # to MONITOR_CLOSELY instead of pretending to a verdict.
    if underlying_price is not None:
        annualized = (premium / underlying_price) * (365.0 / dte)
    else:
        annualized = None

    delta = quote.delta
    prob_itm = round(min(1.0, abs(delta)), 3) if delta is not None else None

    if annualized is None:
        rec = "MONITOR_CLOSELY"
    elif 0.02 <= annualized <= 0.45 and (quote.open_interest or 0) >= 100:
        rec = "INITIATE_POSITION"
    elif annualized > 0.45:
        rec = "MONITOR_CLOSELY"
    else:
        rec = "HOLD_POSITION"

    yield_text = f"{annualized:.1%} annualized" if annualized is not None else "yield unavailable (no underlying price)"
    return {
        "symbol": pos_symbol,
        "position_qty": pos_qty,
        "underlying_price": underlying_price,
        "contracts_available": contracts,
        "option_symbol": quote.option_symbol,
        "strike_price": quote.strike,
        "expiration_date": quote.expiration.isoformat(),
        "days_to_expiry": dte,
        "bid": quote.bid,
        "ask": quote.ask,
        "last_price": premium,
        "open_interest": quote.open_interest,
        "implied_volatility": quote.implied_volatility,
        "delta": delta,
        "theta": quote.theta,
        "premium_received_per_share": round(premium, 4),
        "total_premium_received": round(per_contract_premium * contracts, 2),
        "annualized_return_rate": round(annualized, 4) if annualized is not None else None,
        "probability_itm": prob_itm,
        "recommendation": rec,
        "reasoning": (
            f"Covered call on held {pos_symbol}: {contracts} contract(s), "
            f"{yield_text} at {quote.strike:.0f} strike."
        ),
    }


@router.get("/strategy/screen")
async def screen_strategies_get(
    symbols: Optional[str] = None,
    min_open_interest: int = 0,
    top_n: int = 5,
    full: bool = True,
) -> dict:
    # Security fix: validate explicitly and translate failures to a 422 —
    # constructing ScreenRequest directly used to raise an unhandled
    # ValidationError -> HTTP 500 for hostile query params (top_n=-1 etc.).
    try:
        req = ScreenRequest(
            symbols=[s.strip().upper() for s in symbols.split(",")] if symbols else None,
            min_open_interest=min_open_interest,
            top_n=top_n,
            full=full,
        )
    except ValidationError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc.errors()[:5]))
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
        return {
            "mode": "live",
            "live_error": str(exc),
            "strategy": "covered_call",
            "count": 0,
            "candidates": [],
        }

    wanted = set(req.symbols or [])
    candidates: List[dict] = []
    live_errors: List[str] = []
    for p in positions:
        sym = p.get("symbol", "")
        if wanted and sym not in wanted:
            continue
        try:
            snaps = client.get_option_snapshots(sym)
        except RuntimeError as exc:
            live_errors.append(f"{sym}: {exc}")
            continue
        # The snapshots feed carries no underlying price, so take it from the
        # held position. Without it every annualized yield would be None and
        # nothing could be ranked.
        underlying = _position_price(p)
        for snap in snaps:
            cand = _candidate_from_snapshot(
                sym, float(p.get("qty", 0) or 0), snap, underlying_price=underlying
            )
            if cand is None:
                continue
            oi = cand.get("open_interest")
            if req.min_open_interest > 0 and (oi is None or oi < req.min_open_interest):
                continue
            ann = cand.get("annualized_return_rate")
            # An unknown yield is not a passing yield: without a price we cannot
            # assert it sits under the sanity cap, so it is excluded here rather
            # than ranked against candidates whose yield is known.
            if ann is None or ann > req.max_annualized_return:
                continue
            candidates.append(cand)

    candidates.sort(key=lambda c: c.get("annualized_return_rate") or 0, reverse=True)
    candidates = candidates[: req.top_n]

    response = {"mode": "live", "strategy": "covered_call", "count": len(candidates), "candidates": candidates}
    if live_errors:
        response["live_error"] = "; ".join(live_errors)
    if req.full:
        enriched, portfolio_context = _enrich_with_engine(candidates, positions)
        response["candidates"] = enriched
        if portfolio_context is not None:
            response["portfolio_context"] = portfolio_context
    return response
