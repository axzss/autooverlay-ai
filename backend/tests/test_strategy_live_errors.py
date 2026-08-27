"""Tests for explicit live-mode strategy failures."""

from unittest.mock import patch


def test_strategy_screen_preserves_live_mode_and_error_on_position_failure(client):
    with patch("backend.app.routes.strategy.is_configured", return_value=True), patch(
        "backend.app.routes.strategy.AlpacaClient.get_positions",
        side_effect=RuntimeError("Alpaca API unreachable"),
    ):
        response = client.get("/api/strategy/screen")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "live"
    assert body["live_error"] == "Alpaca API unreachable"
    assert body["candidates"] == []


def test_strategy_screen_surfaces_option_data_error(client):
    position = {"symbol": "AAPL", "qty": "100", "asset_class": "us_equity"}
    with patch("backend.app.routes.strategy.is_configured", return_value=True), patch(
        "backend.app.routes.strategy.AlpacaClient.get_positions",
        return_value=[position],
    ), patch(
        "backend.app.routes.strategy.AlpacaClient.get_option_snapshots",
        side_effect=RuntimeError("Alpaca data API error 503"),
    ):
        response = client.get("/api/strategy/screen")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "live"
    assert body["live_error"] == "AAPL: Alpaca data API error 503"
    assert body["candidates"] == []
