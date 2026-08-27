"""Tests for Alpaca option-position normalization and council wiring."""

from unittest.mock import patch

from backend.app.alpaca_client import normalize_option_position


def test_normalize_short_occ_option_position():
    raw = {
        "symbol": "AAPL240621C00175000",
        "qty": "-2",
        "avg_entry_price": "2.50",
        "current_price": "1.20",
        "market_value": "-240.00",
        "asset_class": "us_option",
    }

    result = normalize_option_position(raw)

    assert result == {
        "symbol": "AAPL",
        "option_symbol": "AAPL240621C00175000",
        "strategy": "SHORT_CALL",
        "contracts": 2,
        "qty": -2.0,
        "side": "short",
        "expiration_date": "2024-06-21",
        "strike_price": 175.0,
        "option_type": "call",
        "initial_premium": 2.5,
        "current_premium": 1.2,
        "premium_received": 500.0,
        "market_value": -240.0,
    }


def test_invalid_occ_position_is_ignored():
    assert normalize_option_position({"symbol": "NOT_AN_OPTION", "qty": "-1"}) is None


def test_council_cycle_passes_normalized_option_positions(client):
    option = {
        "symbol": "AAPL240621C00175000",
        "qty": "-1",
        "avg_entry_price": "2.50",
        "current_price": "1.20",
        "asset_class": "us_option",
    }
    with patch("backend.app.routes.council.is_configured", return_value=True), patch(
        "backend.app.routes.council.AlpacaClient.get_positions",
        return_value=[option],
    ), patch(
        "backend.app.routes.council.AlpacaClient.get_account",
        return_value={"cash": "50000", "equity": "100000"},
    ), patch(
        "backend.app.routes.council.run_daily_cycle",
        return_value={"directives": [], "captured": True},
    ) as run_cycle:
        response = client.post("/api/council/cycle", json={})

    assert response.status_code == 200
    assert run_cycle.call_args.kwargs["open_option_positions"] == [
        normalize_option_position(option)
    ]


def test_council_cycle_does_not_use_mock_when_live_fetch_fails(client):
    with patch("backend.app.routes.council.is_configured", return_value=True), patch(
        "backend.app.routes.council.AlpacaClient.get_positions",
        side_effect=RuntimeError("Alpaca API unreachable"),
    ):
        response = client.post("/api/council/cycle", json={})

    assert response.status_code == 502
    assert response.json()["detail"] == "Alpaca API unreachable"
