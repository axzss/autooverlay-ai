"""Chaos-style tests for /council/cycle under live Alpaca failures."""

from __future__ import annotations

from unittest.mock import patch

from backend.app.alpaca_client import AlpacaAPIError


def test_council_cycle_returns_502_on_alpaca_rate_limit(client):
    with patch("backend.app.routes.council.is_configured", return_value=True), patch(
        "backend.app.routes.council.AlpacaClient.get_positions",
        side_effect=AlpacaAPIError("Rate limit"),
    ):
        response = client.post("/api/council/cycle", json={})

    assert response.status_code == 502
    assert "Rate limit" in response.json()["detail"]


def test_council_cycle_returns_502_on_alpaca_timeout(client):
    with patch("backend.app.routes.council.is_configured", return_value=True), patch(
        "backend.app.routes.council.AlpacaClient.get_positions",
        side_effect=AlpacaAPIError("Timeout"),
    ):
        response = client.post("/api/council/cycle", json={})

    assert response.status_code == 502
    assert response.json()["detail"] == "Timeout"


def test_council_cycle_never_returns_mock_when_live_fails(client):
    with patch("backend.app.routes.council.is_configured", return_value=True), patch(
        "backend.app.routes.council.AlpacaClient.get_positions",
        side_effect=AlpacaAPIError("API error"),
    ):
        response = client.post("/api/council/cycle", json={})

    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == "API error"
    assert "mode" not in body
