"""GET /api/alpaca/bars — intraday/daily bars from Alpaca data API.

Query params:
- symbol: equity ticker, e.g. AAPL
- timeframe: 1Min, 5Min, 15Min, 1Hour, 1Day
- limit: number of bars, default 500
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..alpaca_client import AlpacaClient, is_configured
from ..mock_data import mock_bars

router = APIRouter()


class BarsResponse(BaseModel):
    mode: str
    symbol: str
    timeframe: str
    bars: list[dict]


@router.get("/bars", response_model=BarsResponse)
async def get_bars(
    symbol: str = Query(..., min_length=1, max_length=16),
    timeframe: str = Query("1Hour", min_length=1, max_length=16),
    limit: int = Query(500, ge=1, le=5000),
) -> BarsResponse:
    symbol = symbol.upper().strip()
    if not is_configured():
        return BarsResponse(
            mode="mock",
            symbol=symbol,
            timeframe=timeframe,
            bars=mock_bars(symbol, limit),
        )
    client = AlpacaClient()
    try:
        bars = client.get_bars(symbol=symbol, timeframe=timeframe, limit=limit)
    except RuntimeError:
        bars = mock_bars(symbol, limit)
    return BarsResponse(mode="live", symbol=symbol, timeframe=timeframe, bars=bars)
