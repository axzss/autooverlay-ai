"""GET /api/market-regime — market condition classification based on recent price action.

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

router = APIRouter()


class MarketRegimeResponse(BaseModel):
    mode: str
    symbol: str
    timeframe: str
    regime: str
    confidence: float
    last_close: float | None = None
    sma20: float | None = None
    ema50: float | None = None


@router.get("/market-regime", response_model=MarketRegimeResponse)
async def get_market_regime(
    symbol: str = Query(..., min_length=1, max_length=16),
    timeframe: str = Query("1Hour", min_length=1, max_length=16),
    limit: int = Query(200, ge=20, le=2000),
) -> MarketRegimeResponse:
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
    last_close = closes[-1] if closes else None

    # lightweight indicators for regime classification
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

    def _trange(bars: list[dict], idx: int) -> float:
        if idx == 0:
            return float(bars[idx].get("h", 0)) - float(bars[idx].get("l", 0))
        prev_c = float(bars[idx - 1].get("c", 0))
        h = float(bars[idx].get("h", 0))
        l = float(bars[idx].get("l", 0))
        return max(h - l, abs(h - prev_c), abs(l - prev_c))

    sma20 = _sma(closes, 20)
    ema50 = _ema(closes, 50)

    # ATR-based volatility
    tr = [_trange(bars, i) for i in range(len(bars))]
    atr20 = _sma(tr, 20) if len(tr) >= 20 else None

    # trend score: price vs sma20, sma20 vs ema50, slope sma20
    trend_score = 0
    if last_close and sma20:
        trend_score += 1 if last_close > sma20 else -1
    if sma20 and ema50:
        trend_score += 1 if sma20 > ema50 else -1
    if len(closes) >= 25 and sma20:
        prev_sma = sum(closes[-40:-20]) / 20 if len(closes) >= 40 else None
        if prev_sma:
            trend_score += 1 if sma20 > prev_sma else -1

    regime = "SIDEWAYS"
    confidence = 50.0
    if trend_score >= 2:
        regime = "BULLISH"
        confidence = min(95.0, 60.0 + abs(trend_score) * 10.0)
    elif trend_score <= -2:
        regime = "BEARISH"
        confidence = min(95.0, 60.0 + abs(trend_score) * 10.0)
    else:
        confidence = 60.0

    # damp confidence if very low volatility
    if atr20 and last_close and last_close > 0:
        atr_pct = (atr20 / last_close) * 100
        if atr_pct < 0.4:
            confidence = min(confidence, 70.0)

    return MarketRegimeResponse(
        mode=mode,
        symbol=symbol,
        timeframe=timeframe,
        regime=regime,
        confidence=round(confidence, 2),
        last_close=last_close,
        sma20=sma20,
        ema50=ema50,
    )
