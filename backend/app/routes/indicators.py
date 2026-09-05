"""GET /api/indicators — technical indicators computed from OHLCV bars.

Query params:
- symbol: equity ticker
- timeframe: 1Min, 5Min, 15Min, 1Hour, 1Day
- limit: number of bars to fetch, default 500
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..alpaca_client import AlpacaClient, is_configured
from ..mock_data import mock_bars

router = APIRouter()


class IndicatorPoint(BaseModel):
    time: str
    sma20: float | None = None
    ema50: float | None = None


class IndicatorsResponse(BaseModel):
    mode: str
    symbol: str
    timeframe: str
    indicators: list[IndicatorPoint]


def _sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    window = sum(values[:period]) / period
    out[period - 1] = round(window, 4)
    for i in range(period, len(values)):
        window += (values[i] - values[i - period]) / period
        out[i] = round(window, 4)
    return out


def _ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    out[period - 1] = round(ema, 4)
    for i in range(period, len(values)):
        ema = values[i] * k + ema * (1 - k)
        out[i] = round(ema, 4)
    return out


@router.get("/indicators", response_model=IndicatorsResponse)
async def get_indicators(
    symbol: str = Query(..., min_length=1, max_length=16),
    timeframe: str = Query("1Hour", min_length=1, max_length=16),
    limit: int = Query(500, ge=20, le=5000),
) -> IndicatorsResponse:
    symbol = symbol.upper().strip()
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

    indicators = []
    for i, t in enumerate(times):
        indicators.append(
            IndicatorPoint(
                time=t,
                sma20=sma20[i] if i < len(sma20) else None,
                ema50=ema50[i] if i < len(ema50) else None,
            )
        )
    return IndicatorsResponse(mode=mode, symbol=symbol, timeframe=timeframe, indicators=indicators)
