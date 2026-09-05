"""GET /api/ai-signals — AI buy/sell signal markers derived from indicators/regime.

Query params:
- symbol: equity ticker
- timeframe: bar timeframe
- limit: number of bars to analyze, default 200
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..alpaca_client import AlpacaClient, is_configured
from ..mock_data import mock_bars
from .market_regime import get_market_regime

router = APIRouter()


class Signal(BaseModel):
    time: str
    side: str
    price: float | None = None
    reason: str | None = None


class SignalsResponse(BaseModel):
    mode: str
    symbol: str
    timeframe: str
    signals: list[Signal]


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return round(sum(values[-period:]) / period, 4)


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for price in values[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 4)


@router.get("/ai-signals", response_model=SignalsResponse)
async def get_ai_signals(
    symbol: str = Query(..., min_length=1, max_length=16),
    timeframe: str = Query("1Hour", min_length=1, max_length=16),
    limit: int = Query(200, ge=20, le=2000),
) -> SignalsResponse:
    symbol = symbol.upper().strip()
    regime_data = await get_market_regime(symbol=symbol, timeframe=timeframe, limit=limit)
    if not is_configured():
        bars = mock_bars(symbol, min(limit, 200))
        mode = "mock"
    else:
        client = AlpacaClient()
        try:
            bars = client.get_bars(symbol=symbol, timeframe=timeframe, limit=limit)
            mode = "live"
        except RuntimeError:
            bars = mock_bars(symbol, min(limit, 200))
            mode = "mock"

    closes = [float(b["c"]) for b in bars if "c" in b]
    times = [str(b.get("t", "")) for b in bars]
    sma20 = _sma(closes, 20)
    ema50 = _ema(closes, 50)
    signals: list[Signal] = []
    last = len(closes) - 1
    if last >= 0:
        price = closes[last]
        reasons = []
        if sma20 and price > sma20:
            reasons.append("price above SMA20")
        if ema50 and price > ema50:
            reasons.append("price above EMA50")
        if regime_data.regime == "BULLISH":
            reasons.append("bullish regime")
        if reasons:
            signals.append(Signal(time=times[last], side="buy", price=round(price, 2), reason=", ".join(reasons)))

    return SignalsResponse(mode=mode, symbol=symbol, timeframe=timeframe, signals=signals)
