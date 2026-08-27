"""Route behavior when configured Alpaca is unavailable or returns bad data."""

from unittest.mock import patch

from backend.app.alpaca_client import AlpacaAPIError


def test_trade_returns_502_for_alpaca_api_failure(client):
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order",
        side_effect=AlpacaAPIError("Alpaca request timed out"),
    ):
        response = client.post(
            "/api/trade",
            json={"symbol": "AAPL", "qty": 1, "side": "buy"},
        )

    assert response.status_code == 502
    assert "timed out" in response.json()["detail"]


def test_orders_returns_502_for_alpaca_api_failure(client):
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.AlpacaClient.list_orders",
        side_effect=AlpacaAPIError("Alpaca API unreachable"),
    ):
        response = client.get("/api/trade/orders")

    assert response.status_code == 502
    assert "unreachable" in response.json()["detail"]
