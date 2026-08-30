"""Order ledger, audit trail and idempotency — `backend/app/store/`.

Store-level tests. Route-level idempotency behaviour is in
`test_trade_idempotency.py`.

Every test constructs its own `:memory:` store, so nothing here touches disk.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.store import (
    DEFAULT_IDEMPOTENCY_WINDOW_SECONDS,
    SCHEMA_VERSION,
    BackendStore,
    get_store,
    idempotency_key,
    reset_store,
)


@pytest.fixture
def store():
    instance = BackendStore(":memory:")
    yield instance
    instance.close()


def _payload(**overrides) -> dict:
    payload = {
        "symbol": "AAPL260929C00250000",
        "qty": 1,
        "side": "sell",
        "type": "limit",
        "limit_price": 2.50,
        "time_in_force": "day",
    }
    payload.update(overrides)
    return payload


# --- schema --------------------------------------------------------------


def test_store_opens_in_memory_and_migrates(store):
    assert store.available is True
    assert store.degraded is False
    assert store.schema_version == SCHEMA_VERSION


def test_every_table_exists(store):
    names = {
        row["name"]
        for row in store._query_all(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"order_intent", "audit_event", "config_history", "broker_call"} <= names


def test_migrate_is_idempotent(tmp_path):
    path = tmp_path / "state.db"
    first = BackendStore(path)
    first.record_audit(route="POST /api/trade", action="submit_order")
    first.close()

    second = BackendStore(path)
    try:
        assert second.schema_version == SCHEMA_VERSION
        assert len(second.recent_audit()) == 1  # data survived
    finally:
        second.close()


def test_on_disk_store_persists_across_reopen(tmp_path):
    path = tmp_path / "state.db"
    first = BackendStore(path)
    first.record_intent(key="k1", payload=_payload(), risk=None, mode="live")
    first.close()

    second = BackendStore(path)
    try:
        assert len(second.recent_intents()) == 1
    finally:
        second.close()


# --- idempotency key ----------------------------------------------------


def test_identical_payloads_produce_the_same_key():
    assert idempotency_key(_payload()) == idempotency_key(_payload())


@pytest.mark.parametrize(
    "field,value",
    [("qty", 2), ("side", "buy"), ("limit_price", 3.0), ("type", "market"),
     ("symbol", "MSFT260929C00250000")],
)
def test_any_economic_field_change_produces_a_new_key(field, value):
    assert idempotency_key(_payload()) != idempotency_key(_payload(**{field: value}))


def test_client_order_id_wins_over_the_derived_key():
    """The client is asserting its own request identity."""
    key = idempotency_key(_payload(), client_order_id="cid-42")
    assert key == "client:cid-42"
    # Different payload, same client id → still the same key.
    assert idempotency_key(_payload(qty=99), client_order_id="cid-42") == key


def test_extended_hours_does_not_change_the_key():
    """Non-economic fields must not defeat duplicate detection."""
    a = idempotency_key(_payload(extended_hours=False))
    b = idempotency_key(_payload(extended_hours=True))
    assert a == b


# --- duplicate detection ------------------------------------------------


def test_a_recorded_intent_is_found_as_a_duplicate(store):
    key = idempotency_key(_payload())
    store.record_intent(key=key, payload=_payload(), risk=None, mode="live",
                        status="submitted")
    assert store.find_recent_intent(key) is not None


def test_an_intent_outside_the_window_is_not_a_duplicate(store):
    key = idempotency_key(_payload())
    old = datetime.now(timezone.utc) - timedelta(
        seconds=DEFAULT_IDEMPOTENCY_WINDOW_SECONDS + 60
    )
    store.record_intent(key=key, payload=_payload(), risk=None, mode="live",
                        status="submitted", now=old)
    assert store.find_recent_intent(key) is None


def test_a_rejected_order_is_not_treated_as_a_duplicate(store):
    """A blocked order was never placed — resubmitting after a fix must work."""
    key = idempotency_key(_payload())
    store.record_intent(key=key, payload=_payload(), risk=None, mode="live",
                        status="rejected")
    assert store.find_recent_intent(key) is None


def test_a_failed_order_is_still_treated_as_a_duplicate(store):
    """A broker failure is ambiguous: the order may or may not exist.

    Suppressing the retry is the safe default; the pending/failed row tells an
    operator to reconcile rather than fire again blindly.
    """
    key = idempotency_key(_payload())
    intent_id = store.record_intent(key=key, payload=_payload(), risk=None,
                                    mode="live")
    store.complete_intent(intent_id, status="failed", error="timeout")
    assert store.find_recent_intent(key) is not None


def test_the_most_recent_intent_wins(store):
    key = idempotency_key(_payload())
    first = store.record_intent(key=key, payload=_payload(), risk=None, mode="live")
    store.complete_intent(first, status="submitted", response={"n": 1})
    second = store.record_intent(key=key, payload=_payload(), risk=None, mode="live")
    store.complete_intent(second, status="submitted", response={"n": 2})
    assert store.find_recent_intent(key)["response"] == {"n": 2}


# --- the crash window ---------------------------------------------------


def test_an_intent_written_before_a_crash_stays_pending(store):
    """The rule that matters: intent row first, broker call second.

    A pending row means an order may exist at the broker whose outcome this
    system never learned. That is recoverable. The reverse ordering loses the
    order entirely.
    """
    store.record_intent(key="k1", payload=_payload(), risk=None, mode="live")
    pending = store.pending_intents()
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"
    assert pending[0]["payload"]["symbol"] == "AAPL260929C00250000"


def test_completing_an_intent_clears_it_from_pending(store):
    intent_id = store.record_intent(key="k1", payload=_payload(), risk=None,
                                    mode="live")
    store.complete_intent(intent_id, status="submitted",
                          response={"submitted": True}, broker_order_id="ord-1")
    assert store.pending_intents() == []
    row = store.recent_intents()[0]
    assert row["status"] == "submitted"
    assert row["broker_order_id"] == "ord-1"
    assert row["response"] == {"submitted": True}


def test_completing_a_none_id_is_a_no_op(store):
    """`record_intent` returns None on a degraded store; the caller must not care."""
    store.complete_intent(None, status="submitted")
    assert store.recent_intents() == []


# --- risk decision and provenance are preserved -------------------------


def test_the_risk_decision_is_stored_with_the_order(store):
    risk = {"allowed": True, "checks": [{"name": "coverage", "passed": True}]}
    store.record_intent(key="k1", payload=_payload(), risk=risk, mode="live",
                        run_id="run-1", directive_ref="directive-7")
    row = store.recent_intents()[0]
    assert row["risk"] == risk
    assert row["run_id"] == "run-1"
    assert row["directive_ref"] == "directive-7"


def test_unserializable_payload_values_do_not_break_the_write(store):
    class Opaque:
        pass

    assert store.record_intent(
        key="k1", payload=_payload(extra=Opaque()), risk=None, mode="live"
    ) is not None


# --- audit trail and config history -------------------------------------


def test_audit_events_are_recorded_newest_first(store):
    store.record_audit(route="POST /api/trade", action="submit_order",
                       outcome="blocked")
    store.record_audit(route="PUT /api/strategy/config", action="update_config",
                       outcome="ok")
    events = store.recent_audit()
    assert [e["action"] for e in events] == ["update_config", "submit_order"]


def test_config_history_records_before_and_after(store):
    store.record_config_change(
        before={"take_profit_pct": 0.60},
        after={"take_profit_pct": 0.75},
        actor="aji",
        warnings=["value outside the recommended band"],
    )
    row = store.config_history()[0]
    assert row["before"]["take_profit_pct"] == 0.60
    assert row["after"]["take_profit_pct"] == 0.75
    assert row["warnings"] == ["value outside the recommended band"]


def test_broker_calls_are_recorded(store):
    store.record_broker_call(endpoint="/v2/orders", method="POST", status=200,
                             duration_ms=132.5, retries=1, request_id="req-1")
    row = store._query_one("SELECT * FROM broker_call")
    assert row["endpoint"] == "/v2/orders"
    assert row["retries"] == 1
    assert row["request_id"] == "req-1"


# --- degradation, never an outage --------------------------------------


def test_a_closed_store_degrades_instead_of_raising(store):
    store.close()
    assert store.available is False
    assert store.record_intent(key="k1", payload=_payload(), risk=None,
                               mode="live") is None
    assert store.find_recent_intent("k1") is None
    assert store.recent_intents() == []
    assert store.pending_intents() == []
    assert store.record_audit(route="r", action="a") is None


def test_a_sql_error_marks_the_store_degraded_without_raising(store):
    assert store._execute("SELECT * FROM table_that_does_not_exist") is None
    assert store.degraded is True
    assert "table_that_does_not_exist" in (store.degraded_reason or "")


def test_an_unwritable_path_falls_back_to_memory_and_says_so(tmp_path, monkeypatch):
    """A container with no mounted volume must not take the API down.

    Simulated by making the directory creation fail: filesystem permissions
    cannot express this test when the suite runs as root, which it does here.
    """
    reset_store()
    real_mkdir = Path.mkdir

    def deny(self, *args, **kwargs):
        if "denied" in str(self):
            raise PermissionError(13, "Permission denied", str(self))
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", deny)
    try:
        instance = get_store(tmp_path / "denied" / "state.db")
        assert instance.available is True       # usable
        assert instance.degraded is True        # but not durable
        assert "in-memory" in (instance.degraded_reason or "")
        assert "Permission denied" in (instance.degraded_reason or "")
        # Still functional, just not persistent.
        assert instance.record_audit(route="r", action="a") is not None
    finally:
        reset_store()


def test_get_store_is_a_singleton_within_the_process(tmp_path):
    reset_store()
    try:
        first = get_store(tmp_path / "state.db")
        second = get_store(tmp_path / "state.db")
        assert first is second
    finally:
        reset_store()


def test_reset_store_releases_the_connection(tmp_path):
    reset_store()
    first = get_store(tmp_path / "state.db")
    reset_store()
    second = get_store(tmp_path / "state.db")
    try:
        assert first is not second
    finally:
        reset_store()
