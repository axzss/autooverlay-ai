"""Unit and integration tests for AI Trading Bot & Autonomous Scheduler."""

from __future__ import annotations

import pytest

from backend.app.scheduler import BotScheduler, get_bot_scheduler


def test_bot_scheduler_initial_state():
    scheduler = BotScheduler()
    status = scheduler.get_status()

    assert "running" in status
    assert "interval_hours" in status
    assert status["interval_hours"] >= 0.1
    assert "autonomous_execution" in status
    assert "alpaca_configured" in status
    assert "run_count" in status
    assert status["run_count"] == 0
    assert scheduler.get_history() == []


def test_bot_scheduler_start_and_stop():
    scheduler = BotScheduler()
    scheduler.start()
    assert scheduler.is_running is True
    assert scheduler.get_status()["running"] is True

    scheduler.stop()
    assert scheduler.is_running is False
    assert scheduler.get_status()["running"] is False


def test_bot_scheduler_configuration():
    scheduler = BotScheduler()
    scheduler.set_interval_hours(2.5)
    assert scheduler.interval_hours == pytest.approx(2.5)

    scheduler.set_autonomous_execution(True)
    assert scheduler.autonomous_execution is True

    scheduler.set_autonomous_execution(False)
    assert scheduler.autonomous_execution is False


def test_bot_scheduler_execute_cycle_mock(monkeypatch):
    scheduler = BotScheduler()
    result = scheduler.execute_cycle(manual=True)

    assert isinstance(result, dict)
    assert "run_id" in result
    assert result["run_id"].startswith("bot-")
    assert "mode" in result
    assert "halted" in result
    assert "orders_evaluated" in result
    assert "orders_submitted" in result
    assert "summary" in result

    history = scheduler.get_history()
    assert len(history) >= 1
    assert history[-1]["run_id"] == result["run_id"]


def test_bot_status_route(client):
    res = client.get("/api/bot/status")
    assert res.status_code == 200
    data = res.json()
    assert "running" in data
    assert "interval_hours" in data
    assert "alpaca_configured" in data


def test_bot_mcp_tools_route(client):
    res = client.get("/api/bot/mcp/tools")
    assert res.status_code == 200
    data = res.json()
    assert data["server_name"] == "autooverlay-ai-agent"
    assert "tools" in data
    tool_names = [t["name"] for t in data["tools"]]
    assert "run_autonomous_cycle" in tool_names
    assert "get_bot_status" in tool_names
    assert "get_portfolio_summary" in tool_names
    assert "screen_options_overlay" in tool_names
    assert "evaluate_risk_gate" in tool_names


def test_bot_cycle_route(client):
    res = client.post("/api/bot/cycle")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert "result" in data
    assert "run_id" in data["result"]


def test_bot_config_route(client):
    res = client.post("/api/bot/config", json={"interval_hours": 1.5, "autonomous_execution": False})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "updated"
    assert data["bot"]["interval_hours"] == pytest.approx(1.5)
    assert data["bot"]["autonomous_execution"] is False
