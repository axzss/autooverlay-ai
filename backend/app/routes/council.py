"""GET /council/assess — run the six-persona hedge-fund council live.

For each requested symbol (default: the 8-council universe), builds a market
snapshot (price, 30d annualized vol from daily bars, drawdown from 52-week
high) via the Alpaca data API when credentials are configured, then runs
agent.council.engine.CouncilEngine.assess_underlying. Without credentials the
endpoint degrades to bundled snapshot-like mock data so the UI works offline.
"""

from __future__ import annotations

import asyncio
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
        # classify_market_mood() needs a price series to judge run-up and
        # realized vol. Without it Mr. Market reports mood "unknown" and the
        # cycle loses its market-context step entirely.
        "recent_prices": closes[-60:],
    }


def _fetch_live_snapshots(symbols: List[str]) -> dict[str, dict]:
    """Fetch snapshots from the Alpaca data API; per-symbol failures skipped.

    Bars give price, 30d vol and drawdown. Those alone are not enough for the
    council: Buffett, Graham, Lynch and Munger all score on fundamentals, so
    without them every symbol scored an identical 53.6 / HOLD with bullets like
    "Margins unavailable" — a data outage that reads as analysis. Each snapshot
    is therefore enriched with the fundamentals provider (24h cached, never
    fabricated: unfetched fields stay None).
    """
    client = AlpacaClient()
    out: dict[str, dict] = {}
    for sym in symbols:
        try:
            snaps = client.get_daily_bars(sym, days=365)
            snap = _snapshot_from_bars(sym, snaps)
        except RuntimeError:
            continue
        if not snap:
            continue
        try:
            from agent.council.fundamentals import build_snapshot_with_fundamentals
            snap = build_snapshot_with_fundamentals(sym, snap)
        except Exception:
            pass  # bar-derived fields still usable; fundamentals stay absent
        out[sym] = snap
    return out


def _live_cycle_snapshots(positions: List[dict],
                          candidates: Optional[List[str]]) -> dict[str, dict]:
    """Bar-derived snapshots for the daily cycle in live mode.

    Covers the council universe plus every held symbol, so the cycle gets the
    same price/vol series that GET /council/assess already builds. SPY is always
    included: classify_market_mood() reads its ``recent_prices``, and without it
    market mood is "unknown".

    Never raises — a failed fetch degrades to a missing symbol, which the cycle
    already reports via ``snapshot_symbols_missing``.
    """
    wanted: List[str] = list(COUNCIL_UNIVERSE)
    for sym in [str(p.get("symbol", "")).upper() for p in positions]:
        if sym and sym not in wanted:
            wanted.append(sym)
    for sym in [c.upper() for c in (candidates or [])]:
        if sym and sym not in wanted:
            wanted.append(sym)
    if "SPY" not in wanted:
        wanted.append("SPY")
    try:
        return _fetch_live_snapshots(wanted)
    except Exception:
        return {}


def _assessment_to_dict(symbol: str, snapshots: dict[str, dict]) -> dict:
    """Snapshot lookup + council evaluation for one symbol.

    ``snapshots`` is passed explicitly. It used to be read from a module-level
    ``_snapshots`` global that ``_assess`` overwrote on every request (D6): two
    concurrent requests shared one dict, so a request asking for AAPL could
    render another request's universe. That only ever looked safe because the
    blocking fetch (D5) serialised every request — fixing the concurrency
    without removing the global would have turned a latent bug into live
    cross-request data leakage.
    """
    engine = CouncilEngine()
    snapshot = snapshots[symbol]
    assessment = engine.assess_underlying(dict(snapshot))
    tier, notes = effective_policy_for_symbol(
        symbol, float(snapshot.get("vol30d_annualized_pct") or 0)
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
    """Assess the requested symbols.

    The blocking Alpaca fetch runs in a worker thread (``asyncio.to_thread``).
    Called directly it blocked the event loop for its whole duration — 8 symbols
    × 4 HTTP calls each — so every other request, including `/health`, queued
    behind it (D5). Nothing about the fetch is async-native, so a thread is the
    correct tool rather than rewriting the client.

    Snapshots are local to this call and passed down explicitly; see
    ``_assessment_to_dict`` for why the module global had to go with it.
    """
    wanted: List[str] = [str(s) for s in (req.symbols or COUNCIL_UNIVERSE)]

    mode = "live"
    snapshots: dict[str, dict]
    if is_configured():
        try:
            snapshots = await asyncio.to_thread(_fetch_live_snapshots, wanted)
        except Exception:
            snapshots = {}
    else:
        mode = "mock"
        snapshots = {s["symbol"]: s for s in mock_council_snapshots()}

    assessments: List[dict] = []
    missing: List[str] = []
    for sym in wanted:
        if sym in snapshots:
            try:
                assessments.append(_assessment_to_dict(sym, snapshots))
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
    """Run the full autonomous daily cycle.

    Every blocking step runs in a worker thread: the Alpaca portfolio fetch, the
    per-symbol bar/fundamentals fetch, and ``run_daily_cycle`` itself (which is
    CPU-bound over six personas and may fall back to its own provider calls).
    Run inline they held the event loop for the whole cycle — measured at 0.8s
    for two trivial concurrent requests, and far worse against the live API —
    which is what made `/health` unanswerable during a run (D5).
    """
    import math

    # Live portfolio from Alpaca when configured, else bundled mock fallback.
    positions: List[dict] = []
    open_option_positions: List[dict] = []
    cash: float = 0.0
    account: dict = {}
    mode = "live"
    if is_configured():
        try:
            positions, open_option_positions, account = await asyncio.to_thread(
                _fetch_live_portfolio
            )
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
        "equity": _f(account.get("equity")) or None,
        "peak_equity": _f(account.get("equity")) or None,
        "prev_equity": _f(account.get("last_equity")) or None,
        **(req.portfolio_state_overrides or {}),
    }

    # run_daily_cycle builds its symbol list from held positions + candidates.
    # With an empty portfolio and no explicit candidates that list is empty, so
    # the cycle ran all seven steps and produced nothing — no assessments, no
    # directives, and Mr. Market stuck at "unknown" — while GET /council/assess
    # returned eight assessments from the same credentials. Default to the
    # council universe so both endpoints agree.
    cycle_candidates = req.candidates or list(COUNCIL_UNIVERSE)

    # Live mode: inject bar-derived + fundamentals-enriched snapshots. The
    # provider alone returns no price/vol series, so SPY would carry no
    # recent_prices and market mood could never be classified.
    if mode == "mock":
        candidate_snapshots = {s["symbol"]: s for s in mock_council_snapshots()}
    else:
        candidate_snapshots = await asyncio.to_thread(
            _live_cycle_snapshots, positions, cycle_candidates
        )

    return await asyncio.to_thread(
        lambda: run_daily_cycle(
            positions, cash,
            open_option_positions=open_option_positions,
            candidates=cycle_candidates,
            candidate_snapshots=candidate_snapshots,
            portfolio_state_overrides=state_overrides,
            allow_provider=is_configured(),
        )
    )


def _fetch_live_portfolio() -> tuple[List[dict], List[dict], dict]:
    """Blocking Alpaca portfolio read. Runs in a worker thread."""
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
    return positions, open_option_positions, client.get_account() or {}
