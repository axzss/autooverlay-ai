"""Focused tests for safe Alpaca market-data failure handling."""

from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
import pytest

from backend.app.alpaca_client import AlpacaAPIError, AlpacaClient


def _response(status_code=200, content=b'{"bars": {"AAPL": []}}', json_value=None):
    response = Mock()
    response.status_code = status_code
    response.content = content
    response.text = content.decode("utf-8", errors="replace")
    if json_value is not None:
        response.json.return_value = json_value
    else:
        response.json.side_effect = ValueError("invalid json")
    return response


def _configure_test_alpaca(monkeypatch):
    monkeypatch.setenv("ALPACA_KEY", "TEST_KEY")
    monkeypatch.setenv("ALPACA_SECRET", "TEST_SECRET")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.test")


def test_daily_bars_timeout_is_safe_error(monkeypatch):
    _configure_test_alpaca(monkeypatch)
    with patch("backend.app.alpaca_client.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.request.side_effect = httpx.TimeoutException("timed out")

        with pytest.raises(AlpacaAPIError, match="timed out"):
            AlpacaClient().get_daily_bars("AAPL")


def test_option_snapshot_http_error_is_safe_error(monkeypatch):
    _configure_test_alpaca(monkeypatch)
    with patch("backend.app.alpaca_client.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.request.return_value = _response(429, b"rate limited")

        with pytest.raises(AlpacaAPIError, match="429"):
            AlpacaClient().get_option_snapshots("AAPL")


def test_daily_bars_requires_mapping_response(monkeypatch):
    _configure_test_alpaca(monkeypatch)
    with patch("backend.app.alpaca_client.httpx.Client") as client_cls:
        response = _response(json_value={"bars": []})
        client_cls.return_value.__enter__.return_value.request.return_value = response

        with pytest.raises(AlpacaAPIError, match="bars"):
            AlpacaClient().get_daily_bars("AAPL")


def test_option_snapshots_requires_list_response(monkeypatch):
    _configure_test_alpaca(monkeypatch)
    with patch("backend.app.alpaca_client.httpx.Client") as client_cls:
        response = _response(json_value={"snapshots": {}})
        client_cls.return_value.__enter__.return_value.request.return_value = response

        with pytest.raises(AlpacaAPIError, match="snapshots"):
            AlpacaClient().get_option_snapshots("AAPL")
