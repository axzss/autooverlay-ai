"""Live-mode integration tests — the coverage gap that let D1/D2/D3 ship.

Every test here runs with `is_configured() == True` via the `live_credentials`
fixture and a monkeypatched broker. No network: the fixture replaces
`httpx.Client` with a raiser, so an unpatched call fails loudly rather than
reaching Alpaca.

Each test in this file FAILS against ddcc665.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "options_snapshots_aapl.json"


def _captured_payload() -> dict:
    return json.loads(FIXTURE.read_text())


def _tradeable_chain(underlying: str = "AAPL") -> list[dict]:
    """The captured chain, re-dated so the contracts are not already expired.

    The fixture is a real payload, so its expirations are fixed in the past
    relative to any future test run. Re-keying the symbols keeps every field
    authentic while making the DTE window meaningful.
    """
    payload = _captured_payload()
    out: list[dict] = []
    for offset, (symbol, raw) in enumerate(payload["snapshots"].items()):
        exp = datetime.now(timezone.utc).date() + timedelta(days=21 + offset)
        rekeyed = f"{underlying}{exp:%y%m%d}{symbol[10]}{symbol[11:]}"
        out.append({**raw, "symbol": rekeyed})
    return out


@pytest.fixture
def live_position(monkeypatch):
    """One held equity position: 300 AAPL shares at $232.50."""
    position = {
        "symbol": "AAPL",
        "qty": "300",
        "asset_class": "us_equity",
        "current_price": "232.50",
        "market_value": "69750",
        "avg_entry_price": "210.00",
    }
    monkeypatch.setattr(
        "backend.app.routes.strategy.AlpacaClient.get_positions",
        lambda self: [position],
    )
    return position


def test_screen_returns_candidates_from_a_real_chain(
    client, live_credentials, live_position, monkeypatch
):
    """D1 + D2 together: live screen used to return count 0 and a live_error.

    Against ddcc665 this asserts `count > 0` and fails, because
    `get_option_snapshots` rejected the dict payload and
    `_candidate_from_snapshot` then dropped every entry on `details.type`.
    """
    monkeypatch.setattr(
        "backend.app.routes.strategy.AlpacaClient.get_option_snapshots",
        lambda self, symbol: _tradeable_chain(symbol),
    )

    response = client.get("/api/strategy/screen?full=false&min_open_interest=0")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "live"
    assert "live_error" not in body
    assert body["count"] > 0

    candidate = body["candidates"][0]
    assert candidate["symbol"] == "AAPL"
    assert candidate["option_symbol"].startswith("AAPL")
    # Strike and expiry are parsed from the OCC symbol, not from a `details`
    # block the payload does not contain.
    assert candidate["strike_price"] > 0
    assert candidate["expiration_date"]
    assert candidate["days_to_expiry"] > 0
    # Underlying price comes from the held position; the snapshots feed has none.
    assert candidate["underlying_price"] == pytest.approx(232.50)
    assert candidate["annualized_return_rate"] is not None
    assert candidate["contracts_available"] == 3  # 300 shares = 3 lots


def test_screen_only_surfaces_calls(client, live_credentials, live_position, monkeypatch):
    """The captured chain contains puts; a covered-call screen must exclude them."""
    monkeypatch.setattr(
        "backend.app.routes.strategy.AlpacaClient.get_option_snapshots",
        lambda self, symbol: _tradeable_chain(symbol),
    )

    body = client.get("/api/strategy/screen?full=false&top_n=25").json()

    assert body["count"] > 0
    assert all("C" in c["option_symbol"][10:11] for c in body["candidates"])


def test_agent_run_returns_200_with_a_live_chain(
    client, live_credentials, monkeypatch
):
    """D3: this returned HTTP 500 via `_occ_expiration`'s TypeError."""
    monkeypatch.setattr(
        "backend.app.routes.agent.AlpacaClient.get_option_snapshots",
        lambda self, symbol: _tradeable_chain(symbol),
    )

    async def fake_cycle(_req):
        return {
            "halted": False,
            "steps_run": ["stubbed"],
            "directives": [{
                "action": "INITIATE",
                "symbol": "AAPL",
                "params": {
                    "strategy_allowed": ["COVERED_CALL"],
                    "delta_min": 0.02,
                    "delta_max": 0.60,
                    "max_dte": 60,
                    "size": 1,
                },
                "reasoning_trace": ["stubbed directive"],
            }],
        }

    monkeypatch.setattr("backend.app.routes.agent.council_cycle", fake_cycle)

    response = client.post("/api/agent/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "live"
    assert body["orders_ready"] is False
    assert len(body["order_intents"]) == 1

    intent = body["order_intents"][0]
    # The whole point of the order preview: a resolved contract, not "pending".
    assert intent["option_symbol"] is not None
    assert intent["option_symbol"].startswith("AAPL")
    assert intent["type"] == "limit"
    assert intent["limit_price"] is not None
    assert intent["requires_approval"] is True
    assert intent["submitted"] is False


def test_agent_run_survives_a_broken_contract_in_the_chain(
    client, live_credentials, monkeypatch
):
    """One malformed OCC symbol must not 500 the whole run."""
    def chain(self, symbol):
        return [{"symbol": "NOT_AN_OCC", "greeks": {"delta": 0.2}}] + _tradeable_chain(symbol)

    monkeypatch.setattr(
        "backend.app.routes.agent.AlpacaClient.get_option_snapshots", chain
    )

    async def fake_cycle(_req):
        return {
            "halted": False,
            "steps_run": ["stubbed"],
            "directives": [{
                "action": "INITIATE",
                "symbol": "AAPL",
                "params": {
                    "strategy_allowed": ["COVERED_CALL"],
                    "delta_min": 0.02,
                    "delta_max": 0.60,
                    "max_dte": 60,
                    "size": 1,
                },
                "reasoning_trace": [],
            }],
        }

    monkeypatch.setattr("backend.app.routes.agent.council_cycle", fake_cycle)

    response = client.post("/api/agent/run", json={})

    assert response.status_code == 200
    assert response.json()["order_intents"][0]["option_symbol"] is not None


def test_live_broker_failure_still_surfaces_as_live_error(
    client, live_credentials, live_position, monkeypatch
):
    """Live failures must never silently become mock data."""
    monkeypatch.setattr(
        "backend.app.routes.strategy.AlpacaClient.get_option_snapshots",
        lambda self, symbol: (_ for _ in ()).throw(RuntimeError("Alpaca data API error 503")),
    )

    body = client.get("/api/strategy/screen?full=false").json()

    assert body["mode"] == "live"
    assert body["live_error"] == "AAPL: Alpaca data API error 503"
    assert body["candidates"] == []
