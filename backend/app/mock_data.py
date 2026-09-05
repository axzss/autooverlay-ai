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


def mock_bars(symbol: str, limit: int = 500) -> list[dict]:
    import random
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    base = 150.0
    rows = []
    for i in range(limit):
        t = now - timedelta(minutes=limit - i)
        rows.append({
            "t": t.isoformat(),
            "o": round(base + random.uniform(-1, 1), 2),
            "h": round(base + random.uniform(0, 2), 2),
            "l": round(base - random.uniform(0, 2), 2),
            "c": round(base + random.uniform(-1, 1), 2),
            "v": random.randint(1000, 5000),
        })
    return rows


# ---------------------------------------------------------------------------
# Council snapshots (bundled fallback for GET /council/assess without creds)
# ---------------------------------------------------------------------------

_COUNCIL_SNAPSHOT_PATHS = [
    Path(__file__).resolve().parents[2] / "docs" / "market_snapshots.json",
]


def mock_council_snapshots() -> list[dict]:
    """Bundled per-symbol market snapshots: price, 30d vol, drawdown, 52w band."""
    for path in _COUNCIL_SNAPSHOT_PATHS:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if isinstance(data, list) and data:
                    return data
            except json.JSONDecodeError:
                continue
    return [
        {"symbol": "AAPL", "price": 230.0, "vol30d_annualized_pct": 24.0,
         "drawdown_from_52w_high_pct": -8.0, "w52_low": 200.0, "w52_high": 250.0},
        {"symbol": "TSLA", "price": 250.0, "vol30d_annualized_pct": 59.0,
         "drawdown_from_52w_high_pct": -27.0, "w52_low": 190.0, "w52_high": 340.0},
    ]
