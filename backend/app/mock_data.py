"""Bundled mock/fallback data used when Alpaca credentials are absent."""

from __future__ import annotations

import json
from pathlib import Path

_MOCK_PATHS = [
    Path(__file__).resolve().parents[2] / "frontend" / "app" / "data" / "mock_portfolio.json",
    Path(__file__).resolve().parents[2] / "agent" / "data" / "mock_portfolio.json",
]


def load_mock() -> dict:
    for path in _MOCK_PATHS:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
    return {"account_info": {}, "positions": [], "orders": [], "covered_call_opportunities": []}


def mock_account() -> dict:
    return load_mock().get("account_info", {})


def mock_positions() -> list[dict]:
    return load_mock().get("positions", [])


def mock_orders() -> list[dict]:
    return load_mock().get("orders", [])


def mock_screen_candidates() -> list[dict]:
    return load_mock().get("covered_call_opportunities", [])
