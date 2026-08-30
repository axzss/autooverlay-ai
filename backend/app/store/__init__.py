"""Backend persistence: order ledger, audit trail, config history.

Deliberately the backend's **own** store. It never reads or writes the agent
layer's `agent_state.db` — cross-layer database sharing is how a boundary
violation becomes a data-corruption bug. If backend code needs agent state, it
calls an agent function.

See docs/BRIEF-BACKEND-V2.md B3.
"""

from .store import (
    DEFAULT_IDEMPOTENCY_WINDOW_SECONDS,
    SCHEMA_VERSION,
    BackendStore,
    StoreUnavailable,
    default_db_path,
    get_store,
    idempotency_key,
    reset_store,
)

__all__ = [
    "DEFAULT_IDEMPOTENCY_WINDOW_SECONDS",
    "SCHEMA_VERSION",
    "BackendStore",
    "StoreUnavailable",
    "default_db_path",
    "get_store",
    "idempotency_key",
    "reset_store",
]
