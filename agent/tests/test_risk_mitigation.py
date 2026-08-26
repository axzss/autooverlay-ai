"""Unit tests for agent.council.risk_mitigation.evaluate_kill_switch."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.config import StrategyConfig  # noqa: E402
from agent.council.risk_mitigation import evaluate_kill_switch  # noqa: E402


def test_healthy_portfolio_not_halted():
    state = {"equity": 100000.0, "peak_equity": 101000.0,
             "prev_equity": 99800.0, "consecutive_stop_losses": 0}
    res = evaluate_kill_switch(state)
    assert res == {"halted": False, "reasons": []}


def test_drawdown_breach_halts():
    state = {"equity": 94900.0, "peak_equity": 100000.0}   # -5.1%
    res = evaluate_kill_switch(state)
    assert res["halted"] is True
    assert any("drawdown" in r for r in res["reasons"])


def test_single_day_loss_halts():
    state = {"equity": 97000.0, "prev_equity": 100000.0}   # -3%
    res = evaluate_kill_switch(state)
    assert res["halted"] is True
    assert any("single-day" in r for r in res["reasons"])


def test_consecutive_stop_losses_halts():
    state = {"equity": 99000.0, "prev_equity": 99500.0,
             "consecutive_stop_losses": 3}
    res = evaluate_kill_switch(state)
    assert res["halted"] is True
    assert any("stop-loss" in r for r in res["reasons"])


def test_configurable_thresholds():
    state = {"equity": 97000.0, "peak_equity": 100000.0,   # -3% dd
             "consecutive_stop_losses": 2}
    strict_cfg = StrategyConfig()
    strict_cfg.kill_max_drawdown_pct = 2.5
    strict_cfg.kill_max_single_day_loss_pct = 2.0
    strict_cfg.kill_consecutive_stop_losses = 2
    res = evaluate_kill_switch(state, config=strict_cfg)
    assert res["halted"] is True
    assert len(res["reasons"]) == 2


def test_missing_inputs_are_ignored():
    res = evaluate_kill_switch({})
    assert res == {"halted": False, "reasons": []}
