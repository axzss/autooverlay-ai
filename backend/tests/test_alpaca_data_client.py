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


def test_option_snapshots_accepts_dict_payload(monkeypatch):
    """Alpaca returns ``snapshots`` as a dict keyed by OCC option symbol.

    MODIFIED TEST (was ``test_option_snapshots_requires_list_response``): the
    previous version asserted that a dict payload *raises*, which encoded
    defect D1 — the real Alpaca shape was rejected on every live call, so no
    options data ever reached the strategy layer. The correct contract is that
    the dict form is accepted and each entry carries its symbol.
    """
    _configure_test_alpaca(monkeypatch)
    payload = {
        "snapshots": {
            "AAPL301231C00175000": {
                "greeks": {"delta": 0.22},
                "latestQuote": {"bp": 1.20, "ap": 1.30},
            }
        }
    }
    with patch("backend.app.alpaca_client.httpx.Client") as client_cls:
        response = _response(json_value=payload)
        client_cls.return_value.__enter__.return_value.request.return_value = response

        snapshots = AlpacaClient().get_option_snapshots("AAPL")

    assert len(snapshots) == 1
    assert snapshots[0]["symbol"] == "AAPL301231C00175000"
    assert snapshots[0]["greeks"]["delta"] == 0.22


def test_option_snapshots_rejects_non_container_payload(monkeypatch):
    """A scalar where the container belongs is still a hard error."""
    _configure_test_alpaca(monkeypatch)
    with patch("backend.app.alpaca_client.httpx.Client") as client_cls:
        response = _response(json_value={"snapshots": "unexpected"})
        client_cls.return_value.__enter__.return_value.request.return_value = response

        with pytest.raises(AlpacaAPIError, match="snapshots"):
            AlpacaClient().get_option_snapshots("AAPL")


def test_option_snapshots_follows_pagination(monkeypatch):
    """A liquid chain spans pages; truncating it biases every screen."""
    _configure_test_alpaca(monkeypatch)
    pages = [
        _response(json_value={
            "snapshots": {"AAPL301231C00175000": {"greeks": {"delta": 0.2}}},
            "next_page_token": "page-2",
        }),
        _response(json_value={
            "snapshots": {"AAPL301231C00180000": {"greeks": {"delta": 0.1}}},
            "next_page_token": None,
        }),
    ]
    with patch("backend.app.alpaca_client.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.request.side_effect = pages

        snapshots = AlpacaClient().get_option_snapshots("AAPL")

    assert [s["symbol"] for s in snapshots] == [
        "AAPL301231C00175000",
        "AAPL301231C00180000",
    ]


def test_option_snapshots_pagination_is_bounded(monkeypatch):
    """A token that never clears must not spin forever inside one request."""
    _configure_test_alpaca(monkeypatch)
    endless = _response(json_value={
        "snapshots": {"AAPL301231C00175000": {"greeks": {"delta": 0.2}}},
        "next_page_token": "always-more",
    })
    with patch("backend.app.alpaca_client.httpx.Client") as client_cls:
        request_mock = client_cls.return_value.__enter__.return_value.request
        request_mock.return_value = endless

        snapshots = AlpacaClient().get_option_snapshots("AAPL")

    assert request_mock.call_count == AlpacaClient.MAX_SNAPSHOT_PAGES
    assert len(snapshots) == AlpacaClient.MAX_SNAPSHOT_PAGES
