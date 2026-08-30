"""SQLite-backed order ledger, audit trail and config history.

Design rules, each of which exists because of a specific failure mode:

* **Write the intent row BEFORE the broker call, update it after.** Reverse the
  order and a timeout leaves you with a live order you have no record of. That
  is the one case in this whole file that costs real money.
* **Idempotency returns the original response, not an error.** A client that
  legitimately retries after a network timeout must be able to converge.
  Idempotency that 409s on retry is not idempotency.
* **Never raise into a request path.** A broken store must not take the API down
  with it: every method degrades and reports ``degraded``. Persistence is an
  audit improvement, not a new single point of failure.
* **`:memory:` constructible** so tests never touch disk.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1

# How long an identical order payload is considered a duplicate submission.
DEFAULT_IDEMPOTENCY_WINDOW_SECONDS = 300


class StoreUnavailable(RuntimeError):
    """Raised only by explicit callers that require durability."""


def default_db_path() -> Path:
    return Path(__file__).resolve().parents[3] / "backend" / ".cache" / "backend_state.db"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def idempotency_key(payload: dict, client_order_id: str | None = None) -> str:
    """Deterministic key for an order.

    A client-supplied ``client_order_id`` wins — the client is asserting its own
    identity for the request. Otherwise the key is derived from the economically
    meaningful fields plus the UTC date, so the same order tomorrow is a new
    order rather than a suppressed duplicate.
    """
    if client_order_id:
        return f"client:{client_order_id}"
    material = "|".join(
        str(payload.get(field, ""))
        for field in ("symbol", "side", "qty", "type", "limit_price")
    )
    material += "|" + _utcnow().strftime("%Y-%m-%d")
    return "auto:" + hashlib.sha256(material.encode()).hexdigest()[:32]


class BackendStore:
    """Thin, synchronous SQLite wrapper. Safe to share across threads."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._degraded = False
        self.degraded_reason: str | None = None
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._open()

    @property
    def degraded(self) -> bool:
        """True when durability or idempotency guarantees do not hold.

        Includes the closed/unopened case: a store with no connection silently
        drops every write, and a caller that reads only ``degraded_reason``
        would otherwise believe the ledger is intact.
        """
        return self._degraded or self._conn is None

    @degraded.setter
    def degraded(self, value: bool) -> None:
        self._degraded = bool(value)

    # -- lifecycle ---------------------------------------------------------

    def _open(self) -> None:
        try:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            # check_same_thread=False: FastAPI serves requests from a thread
            # pool, and every write here is guarded by self._lock.
            self._conn = sqlite3.connect(
                self.path, check_same_thread=False, timeout=5.0
            )
            self._conn.row_factory = sqlite3.Row
            if self.path != ":memory:":
                # WAL lets a reader run while a writer holds the write lock.
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._migrate()
        except (sqlite3.Error, OSError) as exc:
            self._conn = None
            self.degraded = True
            self.degraded_reason = f"{type(exc).__name__}: {exc}"

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    @property
    def available(self) -> bool:
        return self._conn is not None

    def _migrate(self) -> None:
        assert self._conn is not None
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS order_intent (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key   TEXT NOT NULL,
                    created_at        TEXT NOT NULL,
                    updated_at        TEXT NOT NULL,
                    status            TEXT NOT NULL,
                    mode              TEXT NOT NULL,
                    symbol            TEXT NOT NULL,
                    side              TEXT NOT NULL,
                    qty               REAL NOT NULL,
                    order_type        TEXT NOT NULL,
                    limit_price       REAL,
                    run_id            TEXT,
                    directive_ref     TEXT,
                    request_id        TEXT,
                    payload_json      TEXT NOT NULL,
                    risk_json         TEXT,
                    response_json     TEXT,
                    broker_order_id   TEXT,
                    error             TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_order_intent_key
                    ON order_intent (idempotency_key, created_at);

                CREATE TABLE IF NOT EXISTS audit_event (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at  TEXT NOT NULL,
                    route       TEXT NOT NULL,
                    action      TEXT NOT NULL,
                    actor       TEXT,
                    request_id  TEXT,
                    outcome     TEXT,
                    detail_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_audit_created
                    ON audit_event (created_at);

                CREATE TABLE IF NOT EXISTS config_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at  TEXT NOT NULL,
                    actor       TEXT,
                    request_id  TEXT,
                    before_json TEXT NOT NULL,
                    after_json  TEXT NOT NULL,
                    warnings_json TEXT
                );

                CREATE TABLE IF NOT EXISTS broker_call (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at  TEXT NOT NULL,
                    endpoint    TEXT NOT NULL,
                    method      TEXT NOT NULL,
                    status      INTEGER,
                    duration_ms REAL,
                    retries     INTEGER DEFAULT 0,
                    request_id  TEXT,
                    error       TEXT
                );
                """
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @property
    def schema_version(self) -> int:
        row = self._query_one("SELECT value FROM schema_meta WHERE key = 'version'")
        return int(row["value"]) if row else 0

    # -- order ledger ------------------------------------------------------

    def find_recent_intent(
        self,
        key: str,
        *,
        window_seconds: int = DEFAULT_IDEMPOTENCY_WINDOW_SECONDS,
        now: datetime | None = None,
    ) -> dict | None:
        """Most recent intent for this key inside the window, if any.

        ``rejected`` rows are excluded: a blocked order was never placed, so
        resubmitting it after fixing the portfolio must not be suppressed.
        """
        cutoff = _iso((now or _utcnow()) - timedelta(seconds=window_seconds))
        row = self._query_one(
            """
            SELECT * FROM order_intent
            WHERE idempotency_key = ? AND created_at >= ? AND status != 'rejected'
            ORDER BY id DESC LIMIT 1
            """,
            (key, cutoff),
        )
        return _row_to_dict(row) if row else None

    def record_intent(
        self,
        *,
        key: str,
        payload: dict,
        risk: dict | None,
        mode: str,
        status: str = "pending",
        run_id: str | None = None,
        directive_ref: str | None = None,
        request_id: str | None = None,
        now: datetime | None = None,
    ) -> int | None:
        """Insert an intent row. Call this BEFORE the broker call.

        Returns the row id, or None when the store is unavailable.
        """
        stamp = _iso(now or _utcnow())
        return self._execute(
            """
            INSERT INTO order_intent (
                idempotency_key, created_at, updated_at, status, mode,
                symbol, side, qty, order_type, limit_price,
                run_id, directive_ref, request_id, payload_json, risk_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key, stamp, stamp, status, mode,
                str(payload.get("symbol", "")),
                str(payload.get("side", "")),
                float(payload.get("qty") or 0),
                str(payload.get("type") or payload.get("order_type") or ""),
                _maybe_float(payload.get("limit_price")),
                run_id, directive_ref, request_id,
                _dumps(payload), _dumps(risk) if risk is not None else None,
            ),
        )

    def complete_intent(
        self,
        intent_id: int | None,
        *,
        status: str,
        response: dict | None = None,
        broker_order_id: str | None = None,
        error: str | None = None,
        now: datetime | None = None,
    ) -> None:
        """Update an intent row after the broker call resolves."""
        if intent_id is None:
            return
        self._execute(
            """
            UPDATE order_intent
               SET status = ?, updated_at = ?, response_json = ?,
                   broker_order_id = ?, error = ?
             WHERE id = ?
            """,
            (
                status, _iso(now or _utcnow()),
                _dumps(response) if response is not None else None,
                broker_order_id, error, intent_id,
            ),
        )

    def pending_intents(self) -> list[dict]:
        """Rows written before a broker call that never resolved.

        A non-empty result after a crash means "an order may exist at the broker
        that this system does not know the outcome of" — reconcile, do not
        assume.
        """
        return [
            _row_to_dict(row)
            for row in self._query_all(
                "SELECT * FROM order_intent WHERE status = 'pending' ORDER BY id"
            )
        ]

    def recent_intents(self, limit: int = 50) -> list[dict]:
        return [
            _row_to_dict(row)
            for row in self._query_all(
                "SELECT * FROM order_intent ORDER BY id DESC LIMIT ?", (int(limit),)
            )
        ]

    # -- audit trail -------------------------------------------------------

    def record_audit(
        self,
        *,
        route: str,
        action: str,
        outcome: str | None = None,
        actor: str | None = None,
        request_id: str | None = None,
        detail: dict | None = None,
        now: datetime | None = None,
    ) -> int | None:
        return self._execute(
            """
            INSERT INTO audit_event
                (created_at, route, action, actor, request_id, outcome, detail_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _iso(now or _utcnow()), route, action, actor, request_id, outcome,
                _dumps(detail) if detail is not None else None,
            ),
        )

    def recent_audit(self, limit: int = 50) -> list[dict]:
        return [
            _row_to_dict(row)
            for row in self._query_all(
                "SELECT * FROM audit_event ORDER BY id DESC LIMIT ?", (int(limit),)
            )
        ]

    # -- config history ----------------------------------------------------

    def record_config_change(
        self,
        *,
        before: dict,
        after: dict,
        actor: str | None = None,
        request_id: str | None = None,
        warnings: list[str] | None = None,
        now: datetime | None = None,
    ) -> int | None:
        return self._execute(
            """
            INSERT INTO config_history
                (created_at, actor, request_id, before_json, after_json, warnings_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _iso(now or _utcnow()), actor, request_id,
                _dumps(before), _dumps(after),
                _dumps(warnings) if warnings else None,
            ),
        )

    def config_history(self, limit: int = 50) -> list[dict]:
        return [
            _row_to_dict(row)
            for row in self._query_all(
                "SELECT * FROM config_history ORDER BY id DESC LIMIT ?", (int(limit),)
            )
        ]

    # -- broker calls ------------------------------------------------------

    def record_broker_call(
        self,
        *,
        endpoint: str,
        method: str,
        status: int | None = None,
        duration_ms: float | None = None,
        retries: int = 0,
        request_id: str | None = None,
        error: str | None = None,
        now: datetime | None = None,
    ) -> int | None:
        return self._execute(
            """
            INSERT INTO broker_call
                (created_at, endpoint, method, status, duration_ms, retries,
                 request_id, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _iso(now or _utcnow()), endpoint, method, status, duration_ms,
                int(retries), request_id, error,
            ),
        )

    # -- internals ---------------------------------------------------------

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> int | None:
        with self._lock:
            if self._conn is None:
                return None
            try:
                with self._conn:
                    cursor = self._conn.execute(sql, tuple(params))
                return cursor.lastrowid
            except sqlite3.Error as exc:
                # Degrade, never raise into a request path.
                self.degraded = True
                self.degraded_reason = f"{type(exc).__name__}: {exc}"
                return None

    def _query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            if self._conn is None:
                return None
            try:
                return self._conn.execute(sql, tuple(params)).fetchone()
            except sqlite3.Error as exc:
                self.degraded = True
                self.degraded_reason = f"{type(exc).__name__}: {exc}"
                return None

    def _query_all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            if self._conn is None:
                return []
            try:
                return list(self._conn.execute(sql, tuple(params)).fetchall())
            except sqlite3.Error as exc:
                self.degraded = True
                self.degraded_reason = f"{type(exc).__name__}: {exc}"
                return []


def _row_to_dict(row: sqlite3.Row) -> dict:
    out = dict(row)
    for field in ("payload_json", "risk_json", "response_json", "detail_json",
                  "before_json", "after_json", "warnings_json"):
        if field in out and out[field]:
            try:
                out[field[:-5]] = json.loads(out[field])
            except (TypeError, ValueError):
                out[field[:-5]] = None
    return out


def _dumps(value: Any) -> str:
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return json.dumps({"unserializable": str(type(value))})


def _maybe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# -- process-wide accessor -------------------------------------------------

_store: BackendStore | None = None
_store_lock = threading.Lock()


def get_store(path: str | Path | None = None) -> BackendStore:
    """Process-wide store.

    Falls back to an in-memory store when the on-disk path is unwritable — for
    example a container without a mounted volume. Auditing then survives only
    for the process lifetime, and ``degraded`` says so rather than the API
    failing.
    """
    global _store
    with _store_lock:
        if _store is not None and _store.available:
            return _store
        target = Path(path) if path is not None else default_db_path()
        candidate = BackendStore(target)
        if not candidate.available:
            reason = candidate.degraded_reason
            candidate = BackendStore(":memory:")
            candidate.degraded = True
            candidate.degraded_reason = (
                f"on-disk store unavailable ({reason}); using in-memory store — "
                "audit history will not survive a restart"
            )
        _store = candidate
        return _store


def reset_store() -> None:
    """Drop the process-wide store. Tests use this for isolation."""
    global _store
    with _store_lock:
        if _store is not None:
            _store.close()
        _store = None
