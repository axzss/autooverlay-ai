"""Auth + CSRF contract for POST /api/agent/run.

The agent run endpoint spins up six council personas, fetches Alpaca + Yahoo
data per symbol, and returns ~40 reasoning lines. It is the most expensive
call in the system, so it must not be callable by an anonymous client — yet
it shipped open, because the brief that added auth to /api/trade and
/api/strategy/config (docs/BRIEF-BACKEND-V2.md D8) omitted the agent route.

These tests pin that the dependency actually fires: 401 without a session,
403 with a bad CSRF token. They do NOT drive the full council cycle (that
needs broker mocking and is covered by test_agent_intents.py); they only
assert the gate fires before any cycle work starts.

The `raw_client` fixture in conftest.py depends on a `main_module` fixture
that was never registered (conftest bug), so this module registers its own.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def unauthed_client():
    """A TestClient with NO session cookie — for asserting 401s."""
    from backend.app import main as main_module
    with patch("backend.app.alpaca_client.is_configured", return_value=False):
        with TestClient(main_module.app) as c:
            yield c


def test_agent_run_rejects_an_anonymous_call(unauthed_client):
    """No session cookie -> 401, before any council work starts."""
    response = unauthed_client.post("/api/agent/run", json={})
    assert response.status_code == 401


def test_agent_run_rejects_a_bad_csrf_token(client):
    """Session present but X-CSRF-Token wrong -> 403.

    The `client` fixture authenticates and auto-injects the *good* CSRF token.
    To test the bad-token path we take that session cookie and replay it on a
    fresh client with an explicit bogus header, bypassing the wrapper.
    """
    from backend.app import main as main_module

    cookie_header = client.auth_cookie
    with TestClient(main_module.app) as fresh:
        fresh.headers.update({"Cookie": cookie_header})
        response = fresh.post(
            "/api/agent/run",
            json={},
            headers={"X-CSRF-Token": "bogus-token"},
        )
    assert response.status_code == 403
