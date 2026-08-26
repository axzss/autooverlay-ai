"""GET /council/assess — run the six-persona hedge-fund council live.

For each requested symbol (default: the 8-council universe), builds a market
snapshot (price, 30d annualized vol from daily bars, drawdown from 52-week
high) via the Alpaca data API when credentials are configured, then runs
agent.council.engine.CouncilEngine.assess_underlying. Without credentials the
endpoint degrades to bundled snapshot-like mock data so the UI works offline.
"""

from __future__ import annotations

import math
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, ValidationError, constr

from ..alpaca_client import AlpacaClient, is_configured
from ..mock_data import mock_council_snapshots

router = APIRouter()

# The eight underlyings covered by the council report / docs/market_snapshots.json
COUNCIL_UNIVERSE = ("AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ", "JPM", "KO")

from agent.council.engine import CouncilEngine  # noqa: E402
from agent.council.handoff import effective_policy_for_symbol  # noqa: E402


class CouncilAssessRequest(BaseModel):
    symbols: Optional[
        List[constr(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9.^\-]+$")]
    ] = Field(default=None, description="Underlyings to assess", max_length=50)


def _vol_30d_from_bars(bars: list[dict]) -> float | None:
    """Annualized realized volatility (%) from the last ~30 daily closes."""
    closes = [float(b.get("c") or 0) for b in bars if float(b.get("c") or 0) > 0]
    window = closes[-31:]
    if len(window) < 5:
        return None
    rets = [
        math.log(window[i] / window[i - 1])
        for i in range(1, len(window))
        if window[i - 1] > 0
    ]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252) * 100


def _snapshot_from_bars(symbol: str, bars: list[dict]) -> dict | None:
    closes = [float(b.get("c") or 0) for b in bars if float(b.get("c") or 0) > 0]
    if not closes:
        return None
    price = closes[-1]
    w52_high = max(closes)
    vol = _vol_30d_from_bars(bars)
    return {
        "symbol": symbol,
        "price": price,
        "vol30d_annualized_pct": round(vol, 1) if vol is not None else None,
        "drawdown_from_52w_high_pct": round((price / w52_high - 1) * 100, 1),
        "w52_high": w52_high,
        "w52_low": min(closes),
    }


def _fetch_live_snapshots(symbols: List[str]) -> dict[str, dict]:
    """Fetch snapshots from the Alpaca data API; per-symbol failures skipped."""
    client = AlpacaClient()
    out: dict[str, dict] = {}
    for sym in symbols:
        try:
            snaps = client.get_daily_bars(sym, days=365)
            snap = _snapshot_from_bars(sym, snaps)
        except RuntimeError:
            continue
        if snap:
            out[sym] = snap
    return out


def _assessment_to_dict(symbol: str) -> dict:
    """Snapshot lookup + council evaluation for one symbol."""
    engine = CouncilEngine()
    assessment = engine.assess_underlying(dict(_snapshots[symbol]))
    tier, notes = effective_policy_for_symbol(
        symbol, float(_snapshots[symbol].get("vol30d_annualized_pct") or 0)
    )
    policy = {
        "delta_min": tier.delta_min,
        "delta_max": tier.delta_max,
        "max_dte": tier.max_dte,
        "allowed_strategies": list(tier.allowed_strategies),
        "size_multiplier": tier.size_multiplier,
    }
    return {
        "symbol": symbol,
        "tier": tier.name.upper(),
        "tier_policy_summary": "; ".join(notes),
        "tier_policy": policy,
        "consensus_score": round(float(assessment.consensus_score), 1),
        "recommendation": assessment.recommendation,
        "majority_stance": assessment.majority_stance,
        "is_split": assessment.is_split,
        "verdicts": [
            {
                "persona": v.persona,
                "score": round(float(v.score), 1),
                "stance": v.stance,
                "bullets": list(v.bullets),
            }
            for v in assessment.verdicts.values()
        ],
        "dissent": [dict(d) for d in assessment.dissent],
    }


_snapshots: dict[str, dict] = {}


@router.get("/council/assess")
async def council_assess_get(symbols: Optional[str] = None) -> dict:
    try:
        req = CouncilAssessRequest(
            symbols=[s.strip().upper() for s in symbols.split(",")] if symbols else None
        )
    except ValidationError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=str(exc.errors()[:5]))
    return await _assess(req)


@router.post("/council/assess")
async def council_assess_post(req: CouncilAssessRequest) -> dict:
    return await _assess(req)


async def _assess(req: CouncilAssessRequest) -> dict:
    global _snapshots
    wanted = req.symbols or list(COUNCIL_UNIVERSE)

    mode = "live"
    if is_configured():
        try:
            _snapshots = _fetch_live_snapshots(wanted)
        except Exception:
            _snapshots = {}
    else:
        mode = "mock"
        _snapshots = {s["symbol"]: s for s in mock_council_snapshots()}

    assessments: List[dict] = []
    missing: List[str] = []
    for sym in wanted:
        if sym in _snapshots:
            try:
                assessments.append(_assessment_to_dict(sym))
            except Exception:
                missing.append(sym)
        else:
            missing.append(sym)

    return {"mode": mode, "count": len(assessments), "assessments": assessments}
