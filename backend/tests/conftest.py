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

# alpaca_client.is_configured() reads ALPACA_KEY / ALPACA_SECRET / ALPACA_BASE_URL
# — NOT the APCA_* names set above. If a developer has exported real credentials
# (e.g. `set -a && . ./.env` before running a live check), those leak into pytest
# and every route flips to live mode: four tests then fail asserting
# mode == "mock", and the suite would silently make real network calls.
# Strip them for the whole session so test outcomes never depend on the shell.
for _var in (
    "ALPACA_KEY",
    "ALPACA_SECRET",
    "ALPACA_BASE_URL",
    "APCA_API_DATA_URL",
    "ALPACA_ENDPOINT",
    "ALPACA_DATA_ENDPOINT",
):
    os.environ.pop(_var, None)

try:
    from fastapi.testclient import TestClient  # noqa: F401
    from backend.app import main as main_module  # noqa: F401

    HAS_APP = hasattr(main_module, "app")
except Exception:  # pragma: no cover - implementation not landed yet
    HAS_APP = False


@pytest.fixture(autouse=True)
def isolated_peak_store(tmp_path, monkeypatch):
    """Give every backend test its own kill-switch high-water-mark store.

    ``agent/state/peak.py`` persists NAV and overlay peaks across cycles. Without
    isolation the first request to run would seed a mark that every later test
    inherits, and a peak left behind by a demo (say 100k against the 47k mock
    account) would halt the mock cycle — making the suite's result depend on run
    history rather than on the code.
    """
    from agent.state import PEAK_PATH_ENV
    from agent.council import daily_cycle as dc

    monkeypatch.setenv(PEAK_PATH_ENV, str(tmp_path / "peak_equity.json"))
    monkeypatch.setattr(dc, "_PEAK_STORE", None, raising=False)
    yield
    monkeypatch.setattr(dc, "_PEAK_STORE", None, raising=False)


@pytest.fixture(scope="module")
def client():
    if not HAS_APP:
        pytest.skip("backend.app.main does not expose a FastAPI app yet (implementation in flight)")
    from fastapi.testclient import TestClient

    with TestClient(main_module.app) as c:
        # Clear login rate limiting so tests don't hit 429 from previous test modules
        import backend.app.auth as auth_mod
        auth_mod._login_attempts.clear()

        # Authenticate so tests against protected routes (trade, strategy PUT)
        # do not 401. Uses the hardcoded demo credentials from backend/app/auth.py.
        login_resp = c.post("/api/auth/login", json={"username": "ADIT_IT_BOYS", "password": "ADIT_HATERS_99"})
        assert login_resp.status_code == 200, "demo credentials must work in tests"
        csrf = login_resp.json()["csrf_token"]
        cookie = login_resp.headers.get("set-cookie", "")

        # Extract the session ID from the Set-Cookie header and inject it as a
        # cookie on all subsequent requests. TestClient merges cookies automatically
        # once set on the client, but we also capture the CSRF token for tests
        # that need to send it as a header.
        from http.cookies import SimpleCookie
        sc = SimpleCookie()
        sc.load(cookie)
        session_name = "ao_session"
        if session_name in sc:
            c.cookies.set(session_name, sc[session_name].value)
        c.auth_cookie = cookie.split(";")[0] if cookie else ""
        c.csrf_token = csrf

        # Wrap methods to auto-inject CSRF header for protected routes
        # (not for /api/auth/* which manages its own cookies)
        original_methods = {}
        for m in ("get", "post", "put", "patch", "delete"):
            original_methods[m] = getattr(c, m)

        def make_wrapped(m):
            def wrapped(*args, **kwargs):
                path = args[0] if args else kwargs.get("url", "")
                if isinstance(path, str) and path.startswith("/api/auth"):
                    return original_methods[m](*args, **kwargs)
                hdrs = dict(kwargs.pop("headers", {}) or {})
                if csrf:
                    hdrs["X-CSRF-Token"] = csrf
                kwargs["headers"] = hdrs
                return original_methods[m](*args, **kwargs)
            wrapped.__name__ = f"_auth_wrapped_{m}"
            return wrapped

        for m in ("get", "post", "put", "patch", "delete"):
            setattr(c, m, make_wrapped(m))

        # Ensure mock mode for all tests using this client
        from unittest.mock import patch
        mock_is_configured = patch("backend.app.alpaca_client.is_configured", return_value=False)
        mock_is_configured.start()
        c._mock_is_configured = mock_is_configured

        yield c

        # Cleanup
        mock_is_configured.stop()


@pytest.fixture
def raw_client(main_module):
    """The TestClient without auth injection — for testing 401 on protected routes."""
    from fastapi.testclient import TestClient
    with TestClient(main_module.app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """Headers carrying the CSRF token for protected requests."""
    return {"X-CSRF-Token": client.csrf_token}


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Give every test its own in-memory backend store.

    Without this the process-wide store persists across tests, so an order
    written by one test would look like a duplicate submission to the next.
    """
    from backend.app import store as store_pkg

    store_pkg.reset_store()
    instance = store_pkg.BackendStore(":memory:")
    monkeypatch.setattr(store_pkg, "get_store", lambda path=None: instance)
    monkeypatch.setattr("backend.app.routes.trade.get_store", lambda path=None: instance)
    yield instance
    instance.close()
    store_pkg.reset_store()


@pytest.fixture
def live_credentials(monkeypatch):
    """Opt in to the `is_configured() == True` branch with fake credentials.

    The module-level teardown above strips Alpaca credentials for the entire
    session, which is correct — but it also meant every live-mode code path was
    unreachable from tests. Defects D1, D2 and D3 (docs/BRIEF-BACKEND-V2.md) all
    shipped under a green suite for exactly that reason.

    Request this fixture to exercise the live branch. It never enables network
    access: the caller must still monkeypatch the broker methods it needs.
    """
    monkeypatch.setenv("ALPACA_KEY", "TEST_KEY_NOT_A_SECRET")
    monkeypatch.setenv("ALPACA_SECRET", "TEST_SECRET_NOT_A_SECRET")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.test")
    monkeypatch.setenv("APCA_API_DATA_URL", "https://data.test")

    from backend.app import alpaca_client
    # If another fixture (e.g. client) patched is_configured to return False,
    # restore the genuine credential check for live-mode tests.
    monkeypatch.setattr(
        alpaca_client,
        "is_configured",
        lambda: bool(alpaca_client.get_key() and alpaca_client.get_secret() and alpaca_client.get_base_url()),
    )

    assert alpaca_client.is_configured(), "live_credentials fixture failed to enable live mode"

    def _no_network(*_args, **_kwargs):
        raise AssertionError(
            "test attempted a real HTTP call — monkeypatch the broker method"
        )

    monkeypatch.setattr("backend.app.alpaca_client.httpx.Client", _no_network)
    return True


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
