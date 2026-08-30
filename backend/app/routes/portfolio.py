"""GET /portfolio — account + positions from Alpaca paper API (mock fallback)."""

from __future__ import annotations

from fastapi import APIRouter
from ..alpaca_client import AlpacaClient, is_configured
from ..mock_data import mock_account, mock_positions

router = APIRouter()


def _mode() -> str:
    return "live" if is_configured() else "mock"


@router.get("/portfolio")
async def get_portfolio() -> dict:
    if not is_configured():
        return {
            "mode": _mode(),
            "account_info": mock_account(),
            "positions": mock_positions(),
        }
    client = AlpacaClient()
    try:
        account = client.get_account()
    except RuntimeError as exc:
        return {"mode": "error", "detail": str(exc), "account_info": {}, "positions": [], "orders": []}
    try:
        positions = client.get_positions()
    except RuntimeError as exc:
        return {"mode": "error", "detail": str(exc), "account_info": account, "positions": [], "orders": []}
    try:
        orders = client.list_orders(status="all")
    except RuntimeError:
        orders = []
    return {
        "mode": _mode(),
        "account_info": {
            "account_id": account.get("id"),
            "status": account.get("status"),
            "currency": account.get("currency"),
            "cash": account.get("cash"),
            "portfolio_value": account.get("portfolio_value"),
            "equity": account.get("equity"),
            "last_equity": account.get("last_equity"),
            "long_market_value": account.get("long_market_value"),
            "short_market_value": account.get("short_market_value"),
            "pattern_day_trader": account.get("pattern_day_trader"),
            "trade_suspended_by_user": account.get("trade_suspended_by_user"),
            "multiplier": account.get("multiplier"),
        },
        "positions": [
            {
                "symbol": p.get("symbol"),
                "qty": p.get("qty"),
                "avg_entry_price": p.get("avg_entry_price"),
                "market_value": p.get("market_value"),
                "cost_basis": p.get("cost_basis"),
                "unrealized_pl": p.get("unrealized_pl"),
                "unrealized_plpc": p.get("unrealized_plpc"),
                "change_today": p.get("change_today"),
                "asset_class": p.get("asset_class"),
                "exchange": p.get("exchange"),
                "asset_id": p.get("asset_id"),
                "id": p.get("id"),
            }
            for p in positions
        ],
        "orders": orders,
    }
