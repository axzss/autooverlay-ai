"""Tests for approval-gated order intents."""

from unittest.mock import AsyncMock, patch


def test_agent_run_exposes_order_intent_without_submitting(client):
    cycle = {
        "halted": False,
        "directives": [{
            "action": "INITIATE",
            "symbol": "AAPL",
            "params": {
                "strategy_allowed": ["covered_call"],
                "option_symbol": "AAPL240621C00175000",
                "contracts": 1,
                "limit_price": 2.5,
            },
            "reasoning_trace": ["all gates passed"],
            "provenance": [{"source": "test"}],
        }],
        "portfolio_state": {},
        "blocked_entries": {},
    }
    with patch("backend.app.routes.agent.council_cycle", new=AsyncMock(return_value=cycle)), patch(
        "backend.app.routes.agent.is_configured", return_value=False
    ):
        response = client.post("/api/agent/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["orders_ready"] is False
    assert body["order_intents"] == [{
        "action": "SELL_TO_OPEN",
        "strategy": "covered_call",
        "symbol": "AAPL",
        "option_symbol": "AAPL240621C00175000",
        "contracts": 1,
        "qty": 1,
        "side": "sell",
        "type": "limit",
        "time_in_force": "day",
        "limit_price": 2.5,
        "requires_approval": True,
        "submitted": False,
    }]


def test_agent_run_does_not_create_intent_for_hold(client):
    cycle = {"halted": False, "directives": [{"action": "HOLD", "symbol": "AAPL", "params": {}}]}
    with patch("backend.app.routes.agent.council_cycle", new=AsyncMock(return_value=cycle)):
        response = client.post("/api/agent/run", json={})

    assert response.status_code == 200
    assert response.json()["order_intents"] == []


def test_agent_run_intent_generation_never_calls_trade(client):
    cycle = {"halted": False, "directives": [{"action": "INITIATE", "symbol": "AAPL", "params": {"strategy": "covered_call"}}]}
    with patch("backend.app.routes.agent.council_cycle", new=AsyncMock(return_value=cycle)):
        response = client.post("/api/agent/run", json={})

    assert response.status_code == 200
    assert response.json()["orders_ready"] is False
    assert response.json()["order_intents"][0]["requires_approval"] is True
    assert client.post("/api/trade", json={"symbol": "AAPL", "qty": 1, "side": "buy"}).status_code == 200
    assert response.json()["order_intents"][0]["submitted"] is False


def test_agent_run_rejects_halted_cycle_as_not_ready(client):
    cycle = {
        "halted": True,
        "directives": [{"action": "HOLD", "symbol": "*", "params": {}}],
        "kill_switch": {"halted": True, "reasons": ["drawdown"]},
        "portfolio_state": {},
        "blocked_entries": {},
    }
    with patch("backend.app.routes.agent.council_cycle", new=AsyncMock(return_value=cycle)):
        response = client.post("/api/agent/run", json={})

    assert response.status_code == 200
    assert response.json()["order_intents"] == []
    assert response.json()["orders_ready"] is False
    assert response.json()["risk_summary"]["halted"] is True
