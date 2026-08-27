"""Tests for the recommendation-only agent run endpoint."""

from __future__ import annotations


def test_agent_run_returns_recommendations_without_order_submission(client):
    response = client.post("/api/agent/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["mode"] == "mock"
    assert isinstance(body["run_id"], str) and body["run_id"]
    assert body["orders_ready"] is False
    assert isinstance(body["recommendations"], list)
    assert isinstance(body["risk_summary"], dict)
    assert isinstance(body["reasoning_trace"], list)
    assert "directives" in body["cycle"]


def test_agent_run_accepts_cycle_overrides(client):
    response = client.post(
        "/api/agent/run",
        json={"candidates": ["AAPL"], "cash_override": 25000},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "mock"
    assert body["cycle"]["portfolio_state"]["equity"] >= 25000
    assert all("reasoning_trace" in recommendation for recommendation in body["recommendations"])


def test_agent_run_does_not_expose_order_execution_route(client):
    assert client.post("/api/agent/run/order", json={}).status_code == 404
    assert client.post("/api/agent/run", json={"unexpected": True}).status_code == 200
