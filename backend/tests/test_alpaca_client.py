"""Focused tests for safe Alpaca client failure handling."""

from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
import pytest

from backend.app.alpaca_client import AlpacaAPIError, AlpacaClient


def _response(status_code=200, content=b'{"ok": true}', json_value=None):
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


def test_timeout_is_exposed_as_safe_alpaca_error(monkeypatch):
    _configure_test_alpaca(monkeypatch)
    with patch("backend.app.alpaca_client._get_shared_client") as get_client:
        get_client.return_value.request.side_effect = httpx.TimeoutException("timed out")

        with pytest.raises(AlpacaAPIError, match="timed out"):
            AlpacaClient().get_account()


def test_network_error_is_exposed_as_safe_alpaca_error(monkeypatch):
    _configure_test_alpaca(monkeypatch)
    with patch("backend.app.alpaca_client._get_shared_client") as get_client:
        get_client.return_value.request.side_effect = httpx.ConnectError("offline")

        with pytest.raises(AlpacaAPIError, match="unreachable"):
            AlpacaClient().get_account()


def test_http_error_contains_status_without_secret_values(monkeypatch):
    _configure_test_alpaca(monkeypatch)
    with patch("backend.app.alpaca_client._get_shared_client") as get_client:
        response = _response(503, b"broker unavailable")
        get_client.return_value.request.return_value = response

        with pytest.raises(AlpacaAPIError, match="503"):
            AlpacaClient().get_account()


def test_invalid_json_is_exposed_as_safe_alpaca_error(monkeypatch):
    _configure_test_alpaca(monkeypatch)
    with patch("backend.app.alpaca_client._get_shared_client") as get_client:
        get_client.return_value.request.return_value = _response()

        with pytest.raises(AlpacaAPIError, match="invalid JSON"):
            AlpacaClient().get_account()


def test_empty_positions_response_is_rejected_when_not_a_list(monkeypatch):
    _configure_test_alpaca(monkeypatch)
    with patch("backend.app.alpaca_client._get_shared_client") as get_client:
        response = _response(json_value={"unexpected": True})
        get_client.return_value.request.return_value = response

        with pytest.raises(AlpacaAPIError, match="positions"):
            AlpacaClient().get_positions()
