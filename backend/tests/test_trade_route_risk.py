"""`POST /api/trade` and `/api/trade/preflight` at the route level.

Covers the status-code contract the frontend depends on:

* **409** — well-formed request, unsafe state (the gate blocked it)
* **422** — malformed request (Pydantic rejected it)
* **502** — Alpaca failed
* **200** — accepted, with the full risk decision attached

The headline case is D4 from docs/BRIEF-BACKEND-V2.md: 500 naked short calls on
an unheld symbol returned 200 against ddcc665.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.app.risk import PortfolioSnapshot


def _occ(days_out: int, kind: str = "C", strike: float = 175.0, root: str = "AAPL") -> str:
    exp = datetime.now(timezone.utc).date() + timedelta(days=days_out)
    return f"{root}{exp:%y%m%d}{kind}{int(strike * 1000):08d}"


def _snapshot(**kwargs) -> PortfolioSnapshot:
    defaults = dict(
        available=True,
        equity=200_000.0,
        cash=100_000.0,
        positions=[{
            "symbol": "AAPL", "qty": "300", "asset_class": "us_equity",
            "market_value": "69750",
        }],
        open_option_positions=[],
        halted=False,
        mode="mock",
    )
    defaults.update(kwargs)
    return PortfolioSnapshot(**defaults)


def _covered_call_order(**overrides) -> dict:
    payload = {
        "symbol": _occ(30, "C", 250.0),
        "qty": 1,
        "side": "sell",
        "type": "limit",
        "time_in_force": "day",
        "limit_price": 2.50,
        "run_id": "run-abc123",
        "directive_ref": "directive-1",
    }
    payload.update(overrides)
    return payload


# --- D4: the naked-call case ---------------------------------------------


def test_five_hundred_naked_calls_are_rejected_with_409(client):
    """The exact payload from docs/BRIEF-BACKEND-V2.md D4. Was 200."""
    with patch("backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()):
        response = client.post("/api/trade", json={
            "symbol": _occ(30, "C", 100.0, root="GME"),
            "qty": 500,
            "side": "sell",
            "type": "limit",
            "limit_price": 2.5,
            "time_in_force": "day",
            "run_id": "run-abc123",
        })

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["message"] == "order blocked by the pre-trade risk gate"
    coverage = next(c for c in detail["risk"]["checks"] if c["name"] == "coverage")
    assert coverage["passed"] is False
    assert "NAKED CALL" in coverage["detail"]
    assert coverage["values"]["shares_required"] == 50_000


def test_the_blocked_response_carries_every_check_not_just_the_failure(client):
    with patch("backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()):
        response = client.post("/api/trade", json={
            "symbol": _occ(30, "C", 100.0, root="GME"),
            "qty": 500, "side": "sell", "type": "limit",
            "limit_price": 2.5, "time_in_force": "day", "run_id": "run-x",
        })

    checks = response.json()["detail"]["risk"]["checks"]
    assert {c["name"] for c in checks} >= {
        "state_available", "kill_switch", "contract_sanity", "coverage",
        "collateral", "concentration", "duplicate", "price_sanity", "provenance",
    }
    assert any(c["passed"] for c in checks), "passing checks must be reported too"


# --- the happy path -----------------------------------------------------


def test_a_covered_provenanced_order_is_accepted(client):
    with patch("backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()):
        response = client.post("/api/trade", json=_covered_call_order())

    assert response.status_code == 200
    body = response.json()
    assert body["risk"]["allowed"] is True
    assert body["risk"]["hard_failures"] == []
    assert body["submitted"] is False  # mock mode: validated, never submitted
    assert body["order"]["status"] == "simulated"


def test_the_risk_decision_is_attached_even_on_success(client):
    """Auditability: the accepted order records what it was checked against."""
    with patch("backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()):
        body = client.post("/api/trade", json=_covered_call_order()).json()

    assert len(body["risk"]["snapshot_hash"]) == 16
    assert body["risk"]["evaluated_at"].endswith("+00:00")


def test_live_submission_reaches_the_broker_when_the_gate_allows(client):
    order_result = {
        "id": "order-1", "client_order_id": "cid-1", "symbol": "AAPL",
        "qty": "1", "side": "sell", "type": "limit", "time_in_force": "day",
        "limit_price": "2.5", "status": "accepted",
        "submitted_at": "2026-09-01T13:30:00Z",
    }
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot",
        return_value=_snapshot(mode="live"),
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=order_result
    ) as submit:
        response = client.post("/api/trade", json=_covered_call_order())

    assert response.status_code == 200
    assert response.json()["submitted"] is True
    assert submit.call_count == 1


def test_a_blocked_order_never_reaches_the_broker(client):
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot",
        return_value=_snapshot(mode="live"),
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order"
    ) as submit:
        response = client.post("/api/trade", json=_covered_call_order(
            symbol=_occ(30, "C", 100.0, root="GME"), qty=500,
        ))

    assert response.status_code == 409
    assert submit.call_count == 0


# --- status-code contract ----------------------------------------------


def test_malformed_request_is_422_not_409(client):
    """422 means "you sent nonsense"; 409 means "this trade is unsafe"."""
    response = client.post("/api/trade", json={"nonsense": True})
    assert response.status_code == 422


def test_kill_switch_halt_returns_409_with_the_reason(client):
    with patch(
        "backend.app.routes.trade.fetch_snapshot",
        return_value=_snapshot(halted=True, halt_reasons=["single-day loss -12.96%"]),
    ):
        response = client.post("/api/trade", json=_covered_call_order())

    assert response.status_code == 409
    kill = next(
        c for c in response.json()["detail"]["risk"]["checks"]
        if c["name"] == "kill_switch"
    )
    assert "single-day loss" in kill["detail"]


def test_unreadable_state_returns_409_and_fails_closed(client):
    with patch(
        "backend.app.routes.trade.fetch_snapshot",
        return_value=_snapshot(available=False, fetch_error="AlpacaAPIError: 503"),
    ):
        response = client.post("/api/trade", json=_covered_call_order())

    assert response.status_code == 409
    state = next(
        c for c in response.json()["detail"]["risk"]["checks"]
        if c["name"] == "state_available"
    )
    assert state["passed"] is False


# --- preflight ----------------------------------------------------------


def test_preflight_reports_the_same_verdict_without_submitting(client):
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot",
        return_value=_snapshot(mode="live"),
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order"
    ) as submit:
        response = client.post("/api/trade/preflight", json=_covered_call_order())

    assert response.status_code == 200
    body = response.json()
    assert body["submitted"] is False
    assert body["risk"]["allowed"] is True
    assert submit.call_count == 0


def test_preflight_explains_a_block_so_the_ui_can_disable_the_button(client):
    with patch("backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()):
        response = client.post("/api/trade/preflight", json=_covered_call_order(
            symbol=_occ(30, "C", 100.0, root="GME"), qty=500,
        ))

    assert response.status_code == 200  # preflight itself succeeded
    body = response.json()
    assert body["risk"]["allowed"] is False
    assert any("NAKED CALL" in f for f in body["risk"]["hard_failures"])


def test_preflight_does_not_require_provenance_to_be_useful(client):
    """The UI can preflight before it has attached a run_id."""
    with patch("backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()):
        body = client.post(
            "/api/trade/preflight", json=_covered_call_order(run_id=None)
        ).json()

    names = {c["name"] for c in body["risk"]["checks"]}
    assert "coverage" in names
    provenance = next(c for c in body["risk"]["checks"] if c["name"] == "provenance")
    assert provenance["passed"] is False


# --- override path -----------------------------------------------------


def test_override_allows_a_blocked_order_and_records_the_reason(client):
    with patch("backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()):
        response = client.post("/api/trade", json=_covered_call_order(
            symbol=_occ(30, "C", 100.0, root="GME"), qty=5,
            run_id=None, manual_override=True, override_reason="hedge unwind",
        ))

    assert response.status_code == 200
    risk = response.json()["risk"]
    assert risk["allowed"] is True
    assert risk["override_applied"] is True
    override = next(c for c in risk["checks"] if c["name"] == "manual_override")
    assert override["values"]["reason"] == "hedge unwind"


def test_override_cannot_bypass_the_kill_switch(client):
    with patch(
        "backend.app.routes.trade.fetch_snapshot",
        return_value=_snapshot(halted=True, halt_reasons=["drawdown -9%"]),
    ):
        response = client.post("/api/trade", json=_covered_call_order(
            manual_override=True, override_reason="demo",
        ))

    assert response.status_code == 409
    assert response.json()["detail"]["risk"]["override_applied"] is False
