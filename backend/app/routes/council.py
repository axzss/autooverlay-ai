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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError, constr

from ..alpaca_client import AlpacaClient, is_configured, normalize_option_position
from ..mock_data import mock_account, mock_council_snapshots, mock_positions

router = APIRouter()

# The eight underlyings covered by the council report / docs/market_snapshots.json
COUNCIL_UNIVERSE = ("AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ", "JPM", "KO")

from agent.council.engine import CouncilEngine  # noqa: E402
from agent.council.handoff import effective_policy_for_symbol  # noqa: E402
from agent.council.daily_cycle import run_daily_cycle  # noqa: E402


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


# ---------------------------------------------------------------------------
# POST /council/cycle — run the full autonomous daily cycle
# ---------------------------------------------------------------------------

class CouncilCycleRequest(BaseModel):
    """Optional overrides; defaults pull live Alpaca portfolio or mock data."""
    candidates: Optional[List[str]] = Field(default=None, max_length=50)
    cash_override: Optional[float] = Field(default=None, ge=0)
    portfolio_state_overrides: Optional[dict] = None


@router.post("/council/cycle")
async def council_cycle(req: CouncilCycleRequest) -> dict:
    import math

    # Live portfolio from Alpaca when configured, else bundled mock fallback.
    positions: List[dict] = []
    open_option_positions: List[dict] = []
    cash: float = 0.0
    account: dict = {}
    mode = "live"
    if is_configured():
        try:
            client = AlpacaClient()
            raw_positions = client.get_positions()
            positions = [p for p in raw_positions if (
                isinstance(p, dict)
                and p.get("asset_class") != "us_option"
                and str(p.get("symbol", "")).upper() != "SPY"
            )]
            open_option_positions = [
                normalized for normalized in (
                    normalize_option_position(p) for p in raw_positions
                ) if normalized is not None and normalized["qty"] < 0
            ]
            account = client.get_account() or {}
        except (RuntimeError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not positions and not account:
        mode = "mock"
        account = mock_account()
        positions = mock_positions()

    def _f(v) -> float:
        try:
            f = float(v)
            return f if math.isfinite(f) else 0.0
        except (TypeError, ValueError):
            return 0.0

    cash = req.cash_override if req.cash_override is not None else _f(
        account.get("cash") or account.get("buying_power") or 0)
    state_overrides = {
        "peak_equity": _f(account.get("equity")) or None,
        "prev_equity": _f(account.get("last_equity")) or None,
        **(req.portfolio_state_overrides or {}),
    }

    return run_daily_cycle(
        positions, cash,
        open_option_positions=open_option_positions,
        candidates=req.candidates,
        candidate_snapshots={s["symbol"]: s for s in mock_council_snapshots()}
        if mode == "mock" else None,
        portfolio_state_overrides=state_overrides,
        allow_provider=is_configured(),
    )
