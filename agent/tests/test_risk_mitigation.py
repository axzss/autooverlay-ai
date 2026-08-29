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
    # MODIFIED (W0.1): was `assert res == {"halted": False, "reasons": []}`.
    # evaluate_kill_switch now also returns "notes" and "drawdown_basis" so a
    # NAV fallback is visible instead of silent. Assert on the contract fields
    # rather than whole-dict equality, which broke on any additive field.
    assert res["halted"] is False
    assert res["reasons"] == []



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
    # MODIFIED (W0.1): was whole-dict equality. Same reason as
    # test_healthy_portfolio_not_halted — additive "notes"/"drawdown_basis".
    assert res["halted"] is False
    assert res["reasons"] == []
    # An unevaluable drawdown must SAY so rather than pass silently.
    assert any("not evaluated" in n for n in res["notes"])


# --------------------------------------------------------------------------- #
# W0 regression tests — finding A (overlay drawdown) and A1/A2/A3             #
# --------------------------------------------------------------------------- #

def _short_call(symbol="AAPL240119C00200000", collateral=50000.0, qty=-1):
    return {"symbol": symbol, "qty": qty, "collateral": collateral}


def test_overlay_drawdown_no_longer_compares_value_to_itself():
    """Finding A: dd_equity and dd_peak were both overlay_equity → dd == 0.0.

    With a real overlay peak the breach must now fire.
    """
    state = {"equity": 55000.0, "peak_equity": 200000.0,
             "overlay_peak_equity": 100000.0}
    res = evaluate_kill_switch(state, positions=[_short_call(collateral=40000.0)])
    assert res["halted"] is True
    assert res["drawdown_basis"] == "overlay"
    assert any("drawdown" in r for r in res["reasons"])


def test_production_shaped_equity_book_does_not_mask_nav_drawdown():
    """Finding A1 + A3: live positions carry market_value, so the old code took
    the overlay branch on a pure equity book and reported zero drawdown."""
    equity_book = [
        {"symbol": "NVDA", "qty": 100, "current_price": 300.0, "market_value": 30000.0},
        {"symbol": "MSFT", "qty": 100, "current_price": 250.0, "market_value": 25000.0},
    ]
    state = {"equity": 55000.0, "peak_equity": 200000.0}
    res = evaluate_kill_switch(state, positions=equity_book)
    assert res["halted"] is True
    assert res["drawdown_basis"] == "nav"
    assert any("no short-option positions" in n for n in res["notes"])


def test_overlay_exposure_without_peak_falls_back_to_nav_not_zero():
    """Unknown peak must never read as 'no drawdown'."""
    state = {"equity": 55000.0, "peak_equity": 200000.0}  # no overlay_peak_equity
    res = evaluate_kill_switch(state, positions=[_short_call()])
    assert res["halted"] is True
    assert res["drawdown_basis"] == "nav"
    assert any("overlay_peak_equity missing" in n for n in res["notes"])


def test_overlay_only_drawdown_false_is_now_settable():
    """Finding A2: _cfg_get rejects bools, so the documented escape hatch
    returned the default and the flag could never be turned off."""
    cfg = StrategyConfig()
    cfg.overlay_only_drawdown = False
    state = {"equity": 55000.0, "peak_equity": 200000.0,
             "overlay_peak_equity": 55000.0}  # would show 0% on overlay basis
    res = evaluate_kill_switch(state, positions=[_short_call()], config=cfg)
    assert res["halted"] is True
    assert res["drawdown_basis"] == "nav"


def test_long_option_is_not_overlay_exposure():
    """Short detection requires negative qty, not merely an OCC symbol."""
    long_call = {"symbol": "AAPL240119C00200000", "qty": 5, "market_value": 4000.0}
    state = {"equity": 55000.0, "peak_equity": 200000.0}
    res = evaluate_kill_switch(state, positions=[long_call])
    assert res["drawdown_basis"] == "nav"
    assert res["halted"] is True


def test_overlay_book_drawdown_halts_on_overlay_basis():
    """Overlay collateral down 60% against its own peak."""
    state = {"equity": 500000.0, "peak_equity": 500000.0,   # NAV flat
             "overlay_peak_equity": 100000.0}
    res = evaluate_kill_switch(state, positions=[_short_call(collateral=40000.0)])
    assert res["halted"] is True
    assert res["drawdown_basis"] == "overlay"

