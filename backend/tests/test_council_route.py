"""Route tests for GET /council/assess — Alpaca fully mocked."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.usefixtures("client")


def _bar(close: float) -> dict:
    return {"c": close}


@pytest.fixture
def live_env(monkeypatch):
    """Make is_configured() True so the live branch runs (still mocked)."""
    monkeypatch.setattr("backend.app.routes.council.is_configured", lambda: True)


def test_council_assess_mock_mode(client):
    resp = client.get("/council/assess")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "mock"
    assert data["count"] >= 1
    first = data["assessments"][0]
    for key in ("symbol", "tier", "tier_policy_summary", "consensus_score",
                "recommendation", "verdicts", "dissent"):
        assert key in first
    v = first["verdicts"][0]
    assert set(v) >= {"persona", "score", "stance", "bullets"}
    assert first["tier"] in ("LOW", "MID", "HIGH")


def test_council_assess_api_alias_matches_canonical(client):
    canonical = client.get("/council/assess?symbols=AAPL")
    alias = client.get("/api/council/assess?symbols=AAPL")
    assert canonical.status_code == 200
    assert alias.status_code == 200
    assert alias.json() == canonical.json()


def test_council_assess_symbol_filter(client):
    resp = client.get("/council/assess?symbols=TSLA")
    assert resp.status_code == 200
    data = resp.json()
    assert [a["symbol"] for a in data["assessments"]] == ["TSLA"]
    # TSLA at 59% vol must land in the HIGH tier per council §2
    tsla = data["assessments"][0]
    assert tsla["tier"] == "HIGH"
    assert any("OVERRIDE" in tsla["tier_policy_summary"] or "TSLA" in s
               for s in [tsla["tier_policy_summary"]])


def test_council_assess_live_with_mocked_alpaca(client, live_env):
    bars = [_bar(100.0 + i * 0.5) for i in range(260)]
    with patch(
        "backend.app.routes.council._fetch_live_snapshots",
        return_value={
            "AAPL": {"symbol": "AAPL", "price": 230.0,
                     "vol30d_annualized_pct": 18.0,
                     "drawdown_from_52w_high_pct": -8.0,
                     "w52_low": 200.0, "w52_high": 250.0},
        },
    ) as fetch:
        resp = client.get("/council/assess?symbols=AAPL")
    assert resp.status_code == 200
    fetch.assert_called_once()
    data = resp.json()
    assert data["mode"] == "live"
    a = data["assessments"][0]
    assert a["symbol"] == "AAPL"
    # 18% vol -> LOW tier
    assert a["tier"] == "LOW"


def test_council_assess_rejects_bad_symbols(client):
    resp = client.get("/council/assess?symbols=")
    assert resp.status_code == 200  # empty -> default universe
    resp = client.get("/council/assess?symbols=DROP TABLE")
    assert resp.status_code == 422


def test_vol_30d_computation():
    from backend.app.routes.council import _snapshot_from_bars, _vol_30d_from_bars

    import math as m

    closes = []
    p = 100.0
    for i in range(60):
        p *= 1 + (0.01 if i % 2 else -0.01)
        closes.append(_bar(p))
    vol = _vol_30d_from_bars(closes)
    assert vol is not None and 5 < vol < 300
    snap = _snapshot_from_bars("TEST", closes)
    assert snap is not None and snap["symbol"] == "TEST" and snap["price"] > 0
