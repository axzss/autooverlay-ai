"""Tests for exit_manager and portfolio_analyst."""

import sys
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR.parent))

from agent.exit_manager import ExitManager  # noqa: E402
from agent.portfolio_analyst import PortfolioAnalyst, get_sector  # noqa: E402


def _pos(**kw):
    base = {
        "symbol": "AAPL",
        "strategy": "SHORT_CALL",
        "contracts": 1,
        "strike_price": 190.0,
        "expiration_date": "2026-09-15T12:00:00Z",
        "initial_premium": 2.50,
        "current_premium": 2.00,
        "delta": 0.28,
        "days_to_expiry": 21,
    }
    base.update(kw)
    return base


class TestExitManager:
    def setup_method(self):
        self.em = ExitManager()

    def test_hold_when_no_condition_met(self):
        out = self.em.evaluate_position(_pos())
        assert out["action"] == "HOLD"
        assert out["rule_triggered"] is None
        assert len(out["reasoning_trace"]) >= 3

    def test_take_profit_at_60pct_captured(self):
        # initial 2.50, current 1.00 -> 60% captured
        out = self.em.evaluate_position(_pos(current_premium=1.00))
        assert out["action"] == "TAKE_PROFIT"
        assert "60%" in out["rationale"]
        assert out["order_side"] == "BUY_TO_CLOSE"

    def test_stop_loss_at_200pct_rule(self):
        # initial 2.50, current 7.50 -> loss of 2x initial (200% rule)
        out = self.em.evaluate_position(_pos(current_premium=7.51))
        assert out["action"] == "STOP_LOSS"
        assert out["current_loss_multiple"] >= 2.0

    def test_roll_on_delta_breach(self):
        out = self.em.evaluate_position(_pos(delta=0.45))
        assert out["action"] == "ROLL"
        assert "delta" in out["rationale"].lower()

    def test_roll_on_low_dte(self):
        out = self.em.evaluate_position(_pos(days_to_expiry=5))
        assert out["action"] == "ROLL"
        assert out["dte"] == 5

    def test_profit_takes_priority_over_roll(self):
        out = self.em.evaluate_position(_pos(current_premium=0.80, delta=0.55,
                                             days_to_expiry=3))
        assert out["action"] == "TAKE_PROFIT"

    def test_structured_output_fields(self):
        out = self.em.evaluate_position(_pos())
        for key in ("symbol", "action", "rationale", "reasoning_trace",
                    "premium_captured_pct", "delta", "dte", "order_side"):
            assert key in out

    def test_evaluate_positions_batch(self):
        outs = self.em.evaluate_positions([_pos(), _pos(symbol="MSFT")])
        assert [o["symbol"] for o in outs] == ["AAPL", "MSFT"]


class TestPortfolioAnalyst:
    def setup_method(self):
        self.pa = PortfolioAnalyst()

    def test_sector_map_common_tickers(self):
        assert get_sector("AAPL") == "tech"
        assert get_sector("JPM") == "finance"
        assert get_sector("XOM") == "energy"
        assert get_sector("UNKNOWN_TICKER") == "other"

    def test_concentration_breach_blocks_new_position(self):
        allowed, trace = self.pa.check_new_position(
            symbol="AAPL", collateral_required=20_000,
            existing_overlay_value_for_symbol=10_000,
            portfolio_value=100_000, account_cash=50_000)
        assert not allowed  # 30% > 25%
        assert any("concentration" in t.lower() for t in trace)

    def test_concentration_ok_when_under_limit(self):
        allowed, trace = self.pa.check_new_position(
            symbol="AAPL", collateral_required=14_500,
            existing_overlay_value_for_symbol=5_000,
            portfolio_value=100_000, account_cash=50_000)
        assert allowed  # 19.5% <= 25%
        assert any("✓" in t for t in trace)

    def test_cash_reserve_rule_blocks(self):
        # cash after collateral < 10% of portfolio value
        allowed, trace = self.pa.check_new_position(
            symbol="MSFT", collateral_required=46_000,
            existing_overlay_value_for_symbol=0,
            portfolio_value=100_000, account_cash=50_000)
        assert not allowed  # leaves $4k < $10k floor
        assert any("cash reserve" in t.lower() for t in trace)

    def test_cash_reserve_ok(self):
        allowed, _ = self.pa.check_new_position(
            symbol="MSFT", collateral_required=24_000,
            existing_overlay_value_for_symbol=0,
            portfolio_value=100_000, account_cash=50_000)
        assert allowed  # 24% <= 25% conc; leaves $26k >= $10k floor

    def test_assess_snapshot_structure(self):
        positions = [
            {"symbol": "AAPL", "qty": 200, "avg_entry_price": 180},
            {"symbol": "JPM", "qty": 100, "avg_entry_price": 200},
        ]
        snap = self.pa.assess(positions, portfolio_value=150_000,
                              account_cash=40_000)
        for key in ("concentration", "sector_exposure", "reasoning_trace",
                    "cash_available"):
            assert key in snap
        assert snap["sector_exposure"]["tech"]["value"] == 36_000
        assert snap["sector_exposure"]["finance"]["value"] == 20_000
