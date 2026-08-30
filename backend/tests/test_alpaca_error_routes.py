"""Route behavior when configured Alpaca is unavailable or returns bad data."""

from unittest.mock import patch

from backend.app.alpaca_client import AlpacaAPIError
from backend.app.risk import PortfolioSnapshot


def _passing_snapshot() -> PortfolioSnapshot:
    """A readable, non-halted portfolio so the gate lets the order through."""
    return PortfolioSnapshot(
        available=True,
        equity=100_000.0,
        cash=100_000.0,
        positions=[],
        open_option_positions=[],
        halted=False,
        mode="live",
    )


def test_trade_returns_502_for_alpaca_api_failure(client):
    """MODIFIED TEST: added `run_id` and a stubbed portfolio snapshot.

    `POST /api/trade` now runs the pre-trade risk gate first. Two things then
    stopped this request before it could reach `submit_order`:

    * no `run_id` — the provenance check blocks unattributable orders (409);
    * `is_configured()` patched True with no broker stub — `fetch_snapshot`
      could not read state, and the gate **fails closed** by design.

    Both are correct gate behaviour, so the test supplies provenance and a
    readable snapshot. The 502 contract itself is unchanged.
    """
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_passing_snapshot()
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order",
        side_effect=AlpacaAPIError("Alpaca request timed out"),
    ):
        response = client.post(
            "/api/trade",
            json={"symbol": "AAPL", "qty": 1, "side": "buy", "run_id": "run-test"},
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
