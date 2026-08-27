"""POST /trade — submit an option or equity order to Alpaca paper API."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from ..alpaca_client import AlpacaClient, parse_occ_symbol
from ..mock_data import mock_orders

router = APIRouter()

VALID_TIF = {"day", "gtc", "opg", "cls", "ioc", "fok"}


class TradeRequest(BaseModel):
    # Security bounds: qty/limit_price reject NaN & Infinity (allow_inf_nan=False)
    # and absurd magnitudes; symbol / client_order_id are length-capped so a
    # hostile client cannot push multi-MB strings into the order pipeline.
    symbol: str = Field(..., max_length=64, description="Equity ticker or OCC option symbol (e.g. AAPL240621C00175000)")
    qty: float = Field(..., gt=0, allow_inf_nan=False, le=1_000_000_000)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = Field(default="market", alias="type")
    time_in_force: str = Field(default="day", max_length=16)
    limit_price: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False, le=10_000_000)
    extended_hours: bool = False
    client_order_id: Optional[str] = Field(default=None, max_length=128)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_order(self) -> "TradeRequest":
        import re

        self.symbol = self.symbol.upper().strip()
        # Security: equity symbols must be plain tickers (A-Z, digits, dot,
        # hyphen). Anything else (SQL fragments, shell/unicode junk) is rejected.
        if not re.fullmatch(r"[A-Z0-9.\-]{1,15}", self.symbol):
            raise ValueError(f"invalid symbol format: {self.symbol!r}")
        if self.time_in_force.lower() not in VALID_TIF:
            raise ValueError(f"time_in_force must be one of {sorted(VALID_TIF)}")
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required when order_type is 'limit'")
        if self.order_type == "market" and self.limit_price is not None:
            raise ValueError("limit_price should only be set for limit orders")
        # Option symbols must be traded with day TIF on Alpaca.
        is_option = any(ch.isdigit() for ch in self.symbol) and len(self.symbol) >= 15 and self.symbol[-1].isdigit()
        if is_option:
            try:
                parse_occ_symbol(self.symbol)
            except ValueError as exc:
                raise ValueError(str(exc))
            if self.time_in_force.lower() != "day":
                raise ValueError("option orders require time_in_force='day'")
            if self.limit_price is not None and not (0.01 <= self.limit_price <= 10000):
                raise ValueError("option limit_price must be between 0.01 and 10000")
        return self


@router.post("/trade")
async def submit_trade(req: TradeRequest) -> dict:
    order_payload: dict = {
        "symbol": req.symbol,
        "qty": req.qty,
        "side": req.side,
        "type": req.order_type,
        "time_in_force": req.time_in_force.lower(),
        "extended_hours": req.extended_hours,
    }
    if req.order_type == "limit":
        order_payload["limit_price"] = req.limit_price
    if req.client_order_id:
        order_payload["client_order_id"] = req.client_order_id

    from ..alpaca_client import is_configured

    if not is_configured():
        # Graceful fallback: echo the validated order without submitting.
        return {
            "mode": "mock",
            "submitted": False,
            "reason": "Alpaca credentials not configured; order validated but not submitted",
            "order": {**order_payload, "status": "simulated"},
        }

    client = AlpacaClient()
    try:
        result = client.submit_order(order_payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "mode": "live",
        "submitted": True,
        "order": {
            "id": result.get("id"),
            "client_order_id": result.get("client_order_id"),
            "symbol": result.get("symbol"),
            "qty": result.get("qty"),
            "side": result.get("side"),
            "type": result.get("type"),
            "time_in_force": result.get("time_in_force"),
            "limit_price": result.get("limit_price"),
            "status": result.get("status"),
            "submitted_at": result.get("submitted_at"),
        },
    }


@router.get("/trade/orders")
async def list_orders(status: str = "open") -> dict:
    from ..alpaca_client import is_configured

    if not is_configured():
        return {"mode": "mock", "orders": mock_orders()}
    try:
        orders = AlpacaClient().list_orders(status=status)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"mode": "live", "orders": orders}
