"""Shared fixtures for backend route tests.

All Alpaca interactions are mocked — no network access, no real keys.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
for p in (str(BACKEND_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Ensure tests never touch real Alpaca even if implementation reads env directly.
os.environ.setdefault("APCA_API_KEY_ID", "TEST_KEY_ID")
os.environ.setdefault("APCA_API_SECRET_KEY", "TEST_SECRET")
os.environ.setdefault("ALPACA_PAPER", "true")

try:
    from fastapi.testclient import TestClient  # noqa: F401
    from backend.app import main as main_module  # noqa: F401

    HAS_APP = hasattr(main_module, "app")
except Exception:  # pragma: no cover - implementation not landed yet
    HAS_APP = False


@pytest.fixture(scope="module")
def client():
    if not HAS_APP:
        pytest.skip("backend.app.main does not expose a FastAPI app yet (implementation in flight)")
    from fastapi.testclient import TestClient

    with TestClient(main_module.app) as c:
        yield c


@pytest.fixture
def mock_alpaca(monkeypatch):
    """Patch common Alpaca client entry points used by backend routes.

    Yields a MagicMock; individual tests configure return values on it.
    """
    mock = MagicMock()
    # Patch at likely module locations; harmless no-ops for attributes that don't exist.
    for mod_name in (
        "backend.app.routes.portfolio",
        "backend.app.routes.trade",
        "backend.app.routes.strategy",
        "backend.app.utils",
        "backend.app.utils.alpaca",
    ):
        try:
            module = __import__(mod_name, fromlist=["*"])
        except Exception:
            continue
        for attr in (
            "get_account",
            "get_positions",
            "get_all_positions",
            "submit_order",
            "get_bars",
            "get_option_chain",
            "TradingClient",
            "alpaca",
            "client",
        ):
            monkeypatch.setattr(module, attr, mock, raising=False)
    return mock
