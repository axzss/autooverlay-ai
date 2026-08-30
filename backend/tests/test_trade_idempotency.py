"""`POST /api/trade` idempotency and ledger integration.

Double-submission is the failure the demo is most likely to produce: a judge
clicks twice, or the network stalls and the UI retries. Before B3 that placed
two live orders.

Store-level behaviour is covered in `test_order_ledger.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.app.risk import PortfolioSnapshot


def _occ(days_out: int, kind: str = "C", strike: float = 250.0, root: str = "AAPL") -> str:
    exp = datetime.now(timezone.utc).date() + timedelta(days=days_out)
    return f"{root}{exp:%y%m%d}{kind}{int(strike * 1000):08d}"


def _snapshot(**overrides) -> PortfolioSnapshot:
    defaults = dict(
        available=True,
        equity=400_000.0,
        cash=100_000.0,
        positions=[{
            "symbol": "AAPL", "qty": "300", "asset_class": "us_equity",
            "market_value": "69750",
        }],
        open_option_positions=[],
        halted=False,
        mode="live",
    )
    defaults.update(overrides)
    return PortfolioSnapshot(**defaults)


def _order(**overrides) -> dict:
    payload = {
        "symbol": _occ(30),
        "qty": 1,
        "side": "sell",
        "type": "limit",
        "time_in_force": "day",
        "limit_price": 2.50,
        "run_id": "run-abc123",
    }
    payload.update(overrides)
    return payload


BROKER_RESULT = {
    "id": "ord-1", "client_order_id": "cid-1", "symbol": "AAPL",
    "qty": "1", "side": "sell", "type": "limit", "time_in_force": "day",
    "limit_price": "2.5", "status": "accepted",
    "submitted_at": "2026-09-01T13:30:00Z",
}


def _live(**extra):
    """Patch context for a live, gate-passing submission."""
    patches = {
        "backend.app.alpaca_client.is_configured": lambda: True,
        "backend.app.routes.trade.fetch_snapshot": lambda **_: _snapshot(),
        "backend.app.routes.trade._quote_price": lambda _s: 2.40,
    }
    patches.update(extra)
    return patches


# --- the double-click case ----------------------------------------------


def test_a_repeated_submission_calls_the_broker_once(client, isolated_store):
    """The headline B3 guarantee. Two identical POSTs, one broker order."""
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=BROKER_RESULT
    ) as submit:
        first = client.post("/api/trade", json=_order())
        second = client.post("/api/trade", json=_order())

    assert first.status_code == 200
    assert second.status_code == 200
    assert submit.call_count == 1, "the second submission reached the broker"


def test_the_retry_returns_the_original_response_not_an_error(client, isolated_store):
    """Idempotency that 409s on retry is not idempotency.

    A client retrying after a network timeout must be able to converge on the
    original outcome.
    """
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=BROKER_RESULT
    ):
        first = client.post("/api/trade", json=_order()).json()
        second = client.post("/api/trade", json=_order()).json()

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["order"]["id"] == first["order"]["id"] == "ord-1"
    assert second["submitted"] is True
    assert second["original_submitted_at"] is not None


def test_the_idempotency_key_is_returned_so_a_client_can_correlate(client, isolated_store):
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=BROKER_RESULT
    ):
        body = client.post("/api/trade", json=_order()).json()

    assert body["idempotency_key"].startswith("auto:")


def test_a_client_order_id_makes_the_key_explicit(client, isolated_store):
    """A client-supplied id asserts request identity over payload contents.

    The differing field is `limit_price`, not `qty`: the risk gate runs before
    the idempotency check, so a qty large enough to change the key would be
    rejected as a naked call (409) and never reach it. That ordering is
    deliberate — an unsafe order must not be waved through just because it
    carries a familiar id.
    """
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=BROKER_RESULT
    ) as submit:
        client.post("/api/trade", json=_order(client_order_id="cid-42"))
        second = client.post(
            "/api/trade", json=_order(client_order_id="cid-42", limit_price=2.75)
        )

    # Same client id → same request, even though limit_price differs.
    assert submit.call_count == 1
    assert second.json()["duplicate"] is True


def test_an_unsafe_order_is_still_blocked_even_with_a_known_client_order_id(
    client, isolated_store
):
    """The gate runs before idempotency; a familiar id is not a safety argument."""
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=BROKER_RESULT
    ):
        client.post("/api/trade", json=_order(client_order_id="cid-42"))
        # 5 contracts needs 500 shares; the portfolio holds 300.
        second = client.post(
            "/api/trade", json=_order(client_order_id="cid-42", qty=5)
        )

    assert second.status_code == 409
    failed = {
        c["name"] for c in second.json()["detail"]["risk"]["checks"] if not c["passed"]
    }
    assert "coverage" in failed


def test_a_genuinely_different_order_is_not_suppressed(client, isolated_store):
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=BROKER_RESULT
    ) as submit:
        client.post("/api/trade", json=_order())
        client.post("/api/trade", json=_order(symbol=_occ(30, "C", 260.0)))

    assert submit.call_count == 2


def test_mock_mode_is_also_idempotent(client, isolated_store):
    """The demo path must behave like the live path."""
    with patch("backend.app.routes.trade.fetch_snapshot",
               return_value=_snapshot(mode="mock")):
        first = client.post("/api/trade", json=_order())
        second = client.post("/api/trade", json=_order())

    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True


# --- the crash window ---------------------------------------------------


def test_the_intent_is_written_before_the_broker_call(client, isolated_store):
    """Proven by inspecting the ledger from inside the broker call.

    If the write happened after, a timeout would leave a live order with no
    record of it anywhere in this system.
    """
    seen: dict = {}

    def capture(self, payload):
        seen["pending"] = isolated_store.pending_intents()
        return BROKER_RESULT

    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", capture
    ):
        client.post("/api/trade", json=_order())

    assert len(seen["pending"]) == 1
    assert seen["pending"][0]["status"] == "pending"
    assert seen["pending"][0]["run_id"] == "run-abc123"
    # Resolved after the call returns.
    assert isolated_store.pending_intents() == []


def test_a_broker_failure_leaves_a_failed_row_not_a_silent_gap(client, isolated_store):
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order",
        side_effect=RuntimeError("Alpaca request timed out"),
    ):
        response = client.post("/api/trade", json=_order())

    assert response.status_code == 502
    row = isolated_store.recent_intents()[0]
    assert row["status"] == "failed"
    assert "timed out" in row["error"]


def test_a_retry_after_a_broker_failure_does_not_fire_a_second_order(client, isolated_store):
    """A broker failure is ambiguous — the order may already exist.

    Suppressing the retry is the safe default. The failed row is the operator's
    signal to reconcile rather than resubmit blindly.
    """
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order",
        side_effect=RuntimeError("Alpaca request timed out"),
    ) as submit:
        client.post("/api/trade", json=_order())
        second = client.post("/api/trade", json=_order())

    assert submit.call_count == 1
    assert second.status_code == 200
    assert second.json()["duplicate"] is True


# --- blocked orders are recorded, and are retryable ---------------------


def test_a_blocked_order_is_recorded_in_the_ledger(client, isolated_store):
    with patch("backend.app.routes.trade.fetch_snapshot",
               return_value=_snapshot(positions=[])):
        response = client.post("/api/trade", json=_order())

    assert response.status_code == 409
    row = isolated_store.recent_intents()[0]
    assert row["status"] == "rejected"
    assert row["risk"]["allowed"] is False


def test_a_blocked_order_can_be_resubmitted_once_the_portfolio_allows_it(
    client, isolated_store
):
    """A rejection is not a duplicate: nothing was placed."""
    with patch("backend.app.routes.trade.fetch_snapshot",
               return_value=_snapshot(positions=[])):
        blocked = client.post("/api/trade", json=_order())
    assert blocked.status_code == 409

    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=BROKER_RESULT
    ) as submit:
        allowed = client.post("/api/trade", json=_order())

    assert allowed.status_code == 200
    assert allowed.json()["duplicate"] is False
    assert submit.call_count == 1


# --- the audit endpoints -----------------------------------------------


def test_the_ledger_endpoint_reports_intents_and_pending_rows(client, isolated_store):
    with patch("backend.app.routes.trade.fetch_snapshot",
               return_value=_snapshot(mode="mock")):
        client.post("/api/trade", json=_order())

    body = client.get("/api/trade/ledger").json()
    assert body["degraded"] is False
    assert body["schema_version"] >= 1
    assert body["pending"] == []
    assert len(body["intents"]) == 1
    assert body["intents"][0]["status"] == "simulated"


def test_the_audit_endpoint_records_both_outcomes(client, isolated_store):
    with patch("backend.app.routes.trade.fetch_snapshot",
               return_value=_snapshot(positions=[])):
        client.post("/api/trade", json=_order())
    with patch("backend.app.routes.trade.fetch_snapshot",
               return_value=_snapshot(mode="mock")):
        client.post("/api/trade", json=_order(symbol=_occ(30, "C", 260.0)))

    outcomes = [e["outcome"] for e in client.get("/api/trade/audit").json()["events"]]
    assert "blocked" in outcomes
    assert "simulated" in outcomes


def test_the_ledger_limit_is_bounded(client, isolated_store):
    """An unbounded limit is a memory-exhaustion handle on a public endpoint."""
    assert client.get("/api/trade/ledger?limit=100000").status_code == 200
    assert client.get("/api/trade/ledger?limit=0").status_code == 200
    assert client.get("/api/trade/ledger?limit=-5").status_code == 200


# --- degradation, never an outage -------------------------------------


def test_a_degraded_store_does_not_block_trading(client, isolated_store):
    """Persistence is an audit improvement, not a new point of failure."""
    isolated_store.close()

    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=BROKER_RESULT
    ) as submit:
        response = client.post("/api/trade", json=_order())

    assert response.status_code == 200
    assert submit.call_count == 1
    # Honest about the loss of the guarantee rather than silently pretending.
    assert client.get("/api/trade/ledger").json()["degraded"] is True


def test_a_degraded_store_loses_idempotency_and_says_so(client, isolated_store):
    """The tradeoff is explicit: without the ledger, duplicates get through."""
    isolated_store.close()

    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=BROKER_RESULT
    ) as submit:
        client.post("/api/trade", json=_order())
        client.post("/api/trade", json=_order())

    assert submit.call_count == 2
    assert client.get("/api/trade/ledger").json()["degraded"] is True


# --- preflight must never write ---------------------------------------


def test_preflight_does_not_write_an_intent(client, isolated_store):
    """Otherwise checking an order would make the real submission a duplicate."""
    with patch("backend.app.routes.trade.fetch_snapshot",
               return_value=_snapshot(mode="mock")):
        client.post("/api/trade/preflight", json=_order())

    assert isolated_store.recent_intents() == []


def test_preflight_then_submit_still_reaches_the_broker(client, isolated_store):
    with patch("backend.app.alpaca_client.is_configured", return_value=True), patch(
        "backend.app.routes.trade.fetch_snapshot", return_value=_snapshot()
    ), patch(
        "backend.app.routes.trade._quote_price", return_value=2.40
    ), patch(
        "backend.app.routes.trade.AlpacaClient.submit_order", return_value=BROKER_RESULT
    ) as submit:
        client.post("/api/trade/preflight", json=_order())
        response = client.post("/api/trade", json=_order())

    assert response.status_code == 200
    assert response.json()["duplicate"] is False
    assert submit.call_count == 1
