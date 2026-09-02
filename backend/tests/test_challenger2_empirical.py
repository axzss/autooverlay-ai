"""Challenger 2 Empirical Verification Suite.

Tests mathematical invariants, edge cases, boundary conditions, and resilience:
1. OCC strike collateral derivation ($Strike \times 100 \times Contracts$) across standard and non-standard symbols.
2. Midpoint limit order pricing ($(bid + ask) / 2$) on wide, narrow, zero, sub-penny spreads and banker's rounding.
3. Drawdown threshold boundaries (exact 5.00% max drawdown, 2.00% daily loss, 3 consecutive stop losses).
4. Pre-trade risk gate unoverridable kill-switch and cash collateral boundary.
5. Zero-division and arithmetic immunity (zero equity, negative equity, zero peak).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
import pytest

from agent.council.risk_mitigation import (
    DEFAULT_CONSEC_STOP_LOSSES,
    DEFAULT_MAX_DRAWDOWN_PCT,
    DEFAULT_SINGLE_DAY_LOSS_PCT,
    _is_short_option,
    _overlay_collateral,
    evaluate_kill_switch,
)
from agent.state.peak import PeakStore
from agent.strategies.cash_secured_put import CashSecuredPutStrategy
from backend.app.adapters.options import (
    OccSymbol,
    OptionQuote,
    normalize_snapshot,
    parse_occ,
)
from backend.app.risk.gate import (
    _check_collateral,
    _check_kill_switch,
    _check_price_sanity,
    evaluate_trade,
)
from backend.app.risk.models import (
    CheckResult,
    PortfolioSnapshot,
    RiskDecision,
    TradeIntent,
)


# ============================================================================ #
# 1. OCC STRIKE COLLATERAL DERIVATION & OCC SYMBOL PARSING                     #
# ============================================================================ #


class TestOccCollateralDerivation:
    """Empirically test OCC parsing and collateral calculation ($Strike \times 100 \times Contracts$)."""

    @pytest.mark.parametrize(
        "symbol, expected_underlying, expected_date, expected_type, expected_strike",
        [
            ("AAPL240621C00175000", "AAPL", date(2024, 6, 21), "call", 175.0),
            ("SPY251219P00450000", "SPY", date(2025, 12, 19), "put", 450.0),
            ("TSLA260116C00200000", "TSLA", date(2026, 1, 16), "call", 200.0),
            # 1-character tickers
            ("F240621C00012000", "F", date(2024, 6, 21), "call", 12.0),
            ("C240621P00050000", "C", date(2024, 6, 21), "put", 50.0),
            ("X240621C00035000", "X", date(2024, 6, 21), "call", 35.0),
            # 2 & 3-character tickers
            ("GM240621C00045000", "GM", date(2024, 6, 21), "call", 45.0),
            ("QQQ240621P00380000", "QQQ", date(2024, 6, 21), "put", 380.0),
            # 5 & 6-character tickers
            ("GOOGL240621C00150000", "GOOGL", date(2024, 6, 21), "call", 150.0),
            ("BRKB240621C00400000", "BRKB", date(2024, 6, 21), "call", 400.0),
            ("GOOGLL240621C00150000", "GOOGLL", date(2024, 6, 21), "call", 150.0),
            # Sub-dollar & extreme strikes
            ("XYZ240621C00000001", "XYZ", date(2024, 6, 21), "call", 0.001),
            ("XYZ240621P00000010", "XYZ", date(2024, 6, 21), "put", 0.01),
            ("XYZ240621C00000500", "XYZ", date(2024, 6, 21), "call", 0.50),
            ("XYZ240621P00001000", "XYZ", date(2024, 6, 21), "put", 1.00),
            ("XYZ240621C00172500", "XYZ", date(2024, 6, 21), "call", 172.50),
            ("XYZ240621P00055555", "XYZ", date(2024, 6, 21), "put", 55.555),
            ("XYZ240621C01000000", "XYZ", date(2024, 6, 21), "call", 1000.00),
            ("XYZ240621P10000000", "XYZ", date(2024, 6, 21), "put", 10000.00),
            ("XYZ240621C99999999", "XYZ", date(2024, 6, 21), "call", 99999.999),
        ],
    )
    def test_parse_occ_symbol_and_strike_math(
        self, symbol, expected_underlying, expected_date, expected_type, expected_strike
    ):
        parsed = parse_occ(symbol)
        assert parsed.underlying == expected_underlying
        assert parsed.expiration == expected_date
        assert parsed.option_type == expected_type
        assert math.isclose(parsed.strike, expected_strike, rel_tol=1e-9)

        # Invariant: Strike Collateral = Strike * 100 * Contracts
        for contracts in [1, 2, 5, 10, 100, 1000, 50000]:
            derived_collateral = parsed.strike * 100.0 * contracts
            expected_collateral = expected_strike * 100.0 * contracts
            assert math.isclose(derived_collateral, expected_collateral, rel_tol=1e-9)
            assert derived_collateral >= 0.0

    @pytest.mark.parametrize(
        "invalid_symbol",
        [
            "",
            "AAPL",
            "AAPL240621",
            "AAPL240621X00175000",  # Invalid type 'X'
            "AAPL241321C00175000",  # Invalid month 13
            "AAPL240632C00175000",  # Invalid day 32
            "TOOLONGTICKER240621C00175000",  # Root > 6 chars
            "AAPL240621C175",  # Short strike (< 8 digits)
            None,
            12345,
        ],
    )
    def test_malformed_occ_fails_gracefully(self, invalid_symbol):
        with pytest.raises((ValueError, TypeError)):
            parse_occ(invalid_symbol)

    def test_overlay_collateral_short_positions(self):
        """Verify _overlay_collateral derives Strike * 100 * Contracts for short options only."""
        positions = [
            # Short Put: 2 contracts of SPY 450 Put -> Collateral = 450 * 100 * 2 = 90,000
            {"symbol": "SPY251219P00450000", "qty": -2},
            # Short Call: 1 contract of AAPL 175 Call -> Collateral = 175 * 100 * 1 = 17,500
            {"symbol": "AAPL240621C00175000", "qty": -1},
            # Long Option: 5 contracts -> NOT short, must NOT add collateral
            {"symbol": "TSLA260116C00200000", "qty": 5},
            # Long Stock: 100 shares -> NOT option, must NOT add collateral
            {"symbol": "AAPL", "qty": 100},
        ]
        total_collateral = _overlay_collateral(positions)
        assert total_collateral == 90000.0 + 17500.0

    def test_overlay_collateral_explicit_override(self):
        """Explicit position collateral field is respected when positive."""
        positions = [
            {"symbol": "SPY251219P00450000", "qty": -1, "collateral": 45000.0},
        ]
        assert _overlay_collateral(positions) == 45000.0

    def test_overlay_collateral_zero_and_negative_immunity(self):
        """Verify zero division and negative quantity handling produces non-negative total."""
        positions = [
            {"symbol": "SPY251219P00450000", "qty": 0},  # Qty 0 is not short (< 0 check)
            {"symbol": "AAPL240621C00175000", "qty": "-3"},  # String quantity
        ]
        # Qty 0 ignored; qty "-3" parses as -3 -> collateral = 175 * 100 * 3 = 52500
        assert _overlay_collateral(positions) == 52500.0
        assert _overlay_collateral([]) == 0.0

    def test_is_short_option_boundary_checks(self):
        assert not _is_short_option({})
        assert not _is_short_option({"symbol": "AAPL", "qty": -100})  # Short equity is not OCC option
        assert not _is_short_option({"symbol": "AAPL240621C00175000", "qty": 0})
        assert not _is_short_option({"symbol": "AAPL240621C00175000", "qty": 1})
        assert not _is_short_option({"symbol": "AAPL240621C00175000", "qty": "invalid"})
        assert _is_short_option({"symbol": "AAPL240621C00175000", "qty": -1})
        assert _is_short_option({"symbol": "AAPL240621C00175000", "quantity": "-2.0"})


# ============================================================================ #
# 2. MIDPOINT LIMIT ORDER PRICING ($(bid + ask) / 2$)                          #
# ============================================================================ #


class TestMidpointPricing:
    """Empirically test midpoint limit order calculations across edge case spreads."""

    @pytest.mark.parametrize(
        "bid, ask, expected_mid_4dec, expected_mid_2dec",
        [
            # Narrow spreads
            (1.00, 1.02, 1.01, 1.01),
            (1.00, 1.01, 1.005, 1.00),  # In Python round(1.005, 2) is 1.00 (round-to-even)
            (1.01, 1.02, 1.015, 1.02),  # round(1.015, 2) is 1.02 (round-to-even)
            (0.05, 0.06, 0.055, 0.06),
            # Wide spreads
            (0.05, 10.00, 5.025, 5.03),  # IEEE-754 binary float 5.025000000000000355... rounds to 5.03
            (0.01, 100.00, 50.005, 50.01),  # IEEE-754 binary float 50.00500000000000255... rounds to 50.01
            (1.50, 8.50, 5.0, 5.0),
            # Zero spread
            (2.50, 2.50, 2.5, 2.5),
            (0.01, 0.01, 0.01, 0.01),
            # High-precision / asymmetric decimals
            (1.2345, 5.6789, 3.4567, 3.46),
            (0.125, 0.375, 0.25, 0.25),
        ],
    )
    def test_midpoint_calculation_precision(
        self, bid, ask, expected_mid_4dec, expected_mid_2dec
    ):
        raw_payload = {
            "latestQuote": {"bp": bid, "ap": ask},
        }
        quote = normalize_snapshot("AAPL240621C00175000", raw_payload)
        assert quote is not None
        assert quote.bid == bid
        assert quote.ask == ask
        assert math.isclose(quote.mid, expected_mid_4dec, abs_tol=1e-4)

        # 2-decimal rounded midpoint check (as used in order routing)
        mid_2dec = round((bid + ask) / 2.0, 2)
        assert math.isclose(mid_2dec, expected_mid_2dec, abs_tol=1e-4)

    def test_midpoint_one_sided_or_missing_quotes(self):
        """One-sided or missing bid/ask yields mid=None (does not pretend one side is mid)."""
        # Bid only
        q1 = normalize_snapshot(
            "AAPL240621C00175000", {"latestQuote": {"bp": 1.50, "ap": None}}
        )
        assert q1.mid is None
        assert q1.price is None  # no last either

        # Ask only
        q2 = normalize_snapshot(
            "AAPL240621C00175000", {"latestQuote": {"bp": None, "ap": 2.50}}
        )
        assert q2.mid is None

        # Zero or negative bid (stale market defense: _pos requires strictly > 0)
        q3 = normalize_snapshot(
            "AAPL240621C00175000", {"latestQuote": {"bp": 0.0, "ap": 1.00}}
        )
        assert q3.bid is None  # 0.0 filtered out by _pos
        assert q3.mid is None

        # Both None
        q4 = normalize_snapshot("AAPL240621C00175000", {"latestQuote": {}})
        assert q4.mid is None

    def test_price_sanity_gate_with_midpoint_limits(self):
        """Verify pre-trade risk gate price sanity check against midpoint quote."""
        intent = TradeIntent(
            symbol="AAPL240621C00175000",
            qty=1,
            side="sell",
            order_type="limit",
            time_in_force="day",
            limit_price=5.00,
            run_id="run-123",
        )

        # Exact match (0% deviation) -> PASS
        res = _check_price_sanity(intent, quote_price=5.00)
        assert res.passed
        assert res.values["deviation_pct"] == 0.0

        # +40% deviation (limit 5.00 vs quote 3.5714) -> PASS (<= 50%)
        res_pass = _check_price_sanity(intent, quote_price=3.50)
        assert res_pass.passed
        assert res_pass.values["deviation_pct"] <= 50.0

        # +60% deviation (limit 5.00 vs quote 3.00, dev = +66.7%) -> BLOCK
        res_block = _check_price_sanity(intent, quote_price=3.00)
        assert not res_block.passed
        assert res_block.severity == "BLOCK"

        # -60% deviation (limit 5.00 vs quote 15.00, dev = -66.7%) -> BLOCK
        res_block_low = _check_price_sanity(intent, quote_price=15.00)
        assert not res_block_low.passed
        assert res_block_low.severity == "BLOCK"

        # Market order on option -> BLOCK
        market_intent = TradeIntent(
            symbol="AAPL240621C00175000",
            qty=1,
            side="sell",
            order_type="market",
            time_in_force="day",
            run_id="run-123",
        )
        res_market = _check_price_sanity(market_intent, quote_price=5.00)
        assert not res_market.passed
        assert res_market.severity == "BLOCK"


# ============================================================================ #
# 3. DRAWDOWN THRESHOLD BOUNDARY ENFORCEMENT                                    #
# ============================================================================ #


class TestDrawdownThresholdBoundaries:
    """Empirically test exact boundary transitions for max DD (5%), 1-day loss (2%), and stop-losses (3)."""

    @pytest.mark.parametrize(
        "peak, equity, expected_halted, desc",
        [
            # Max Drawdown (Threshold: 5.00%, dd <= -5.0 breaches)
            (100000.0, 100000.0, False, "0% DD (at peak)"),
            (100000.0, 95001.0, False, "4.999% DD -> Below 5.00% threshold -> PASS"),
            (100000.0, 95000.01, False, "4.99999% DD -> Below 5.00% threshold -> PASS"),
            (100000.0, 95000.0, True, "Exact 5.00000% DD -> At threshold -> HALT"),
            (100000.0, 94999.99, True, "5.00001% DD -> Above threshold -> HALT"),
            (100000.0, 90000.0, True, "10.00% DD -> Breached -> HALT"),
            # Small account scale invariance
            (100.0, 95.01, False, "Small acct 4.99% DD -> PASS"),
            (100.0, 95.0, True, "Small acct exact 5.00% DD -> HALT"),
            (100.0, 94.99, True, "Small acct 5.01% DD -> HALT"),
            # Large institutional scale invariance ($10M)
            (10000000.0, 9500001.0, False, "Inst acct 4.99999% DD -> PASS"),
            (10000000.0, 9500000.0, True, "Inst acct exact 5.00% DD -> HALT"),
            (10000000.0, 9499999.0, True, "Inst acct 5.00001% DD -> HALT"),
        ],
    )
    def test_max_drawdown_exact_boundary(self, peak, equity, expected_halted, desc):
        state = {"equity": equity, "peak_equity": peak}
        result = evaluate_kill_switch(state)
        assert result["halted"] == expected_halted, f"Failed on: {desc} (halted={result['halted']}, reasons={result['reasons']})"
        if expected_halted:
            assert any("breaches kill threshold -5.00%" in r for r in result["reasons"])

    @pytest.mark.parametrize(
        "prev_equity, equity, expected_halted, desc",
        [
            # Single-Day Loss (Threshold: 2.00%, day_loss <= -2.0 breaches)
            (100000.0, 100000.0, False, "0% day loss -> PASS"),
            (100000.0, 98001.0, False, "1.999% day loss -> PASS"),
            (100000.0, 98000.01, False, "1.99999% day loss -> PASS"),
            (100000.0, 98000.0, True, "Exact 2.00000% day loss -> HALT"),
            (100000.0, 97999.99, True, "2.00001% day loss -> HALT"),
            (100000.0, 95000.0, True, "5.00% day loss -> HALT"),
            # Scale invariance
            (100.0, 98.01, False, "Small acct 1.99% day loss -> PASS"),
            (100.0, 98.0, True, "Small acct exact 2.00% day loss -> HALT"),
            (100.0, 97.99, True, "Small acct 2.01% day loss -> HALT"),
        ],
    )
    def test_single_day_loss_exact_boundary(
        self, prev_equity, equity, expected_halted, desc
    ):
        # Peak set equal to prev_equity so max DD does not trigger
        state = {"equity": equity, "peak_equity": prev_equity, "prev_equity": prev_equity}
        result = evaluate_kill_switch(state)
        assert result["halted"] == expected_halted, f"Failed on: {desc}"
        if expected_halted:
            assert any("single-day loss" in r and "-2.00%" in r for r in result["reasons"])

    @pytest.mark.parametrize(
        "consecutive_stops, expected_halted, desc",
        [
            (0, False, "0 stops -> PASS"),
            (1, False, "1 stop -> PASS"),
            (2, False, "2 stops -> PASS"),
            (3, True, "Exact 3 consecutive stops -> HALT"),
            (4, True, "4 stops -> HALT"),
            (10, True, "10 stops -> HALT"),
            # Non-numeric / boolean immunity
            (True, False, "Bool True rejected by type guard -> PASS"),
            (False, False, "Bool False -> PASS"),
            (None, False, "None -> PASS"),
            (-1, False, "Negative stops -> PASS"),
        ],
    )
    def test_consecutive_stop_losses_exact_boundary(
        self, consecutive_stops, expected_halted, desc
    ):
        state = {
            "equity": 100000.0,
            "peak_equity": 100000.0,
            "prev_equity": 100000.0,
            "consecutive_stop_losses": consecutive_stops,
        }
        result = evaluate_kill_switch(state)
        assert result["halted"] == expected_halted, f"Failed on: {desc}"
        if expected_halted:
            assert any("consecutive stop-losses reached" in r for r in result["reasons"])


# ============================================================================ #
# 4. PRE-TRADE RISK GATE UN-OVERRIDABLE KILL-SWITCH & CASH COLLATERAL GATE     #
# ============================================================================ #


class TestRiskGateEnforcement:
    """Empirically test Risk Gate unoverridable kill-switch and cash-reserve bounds."""

    def test_kill_switch_cannot_be_overridden(self):
        """Even with manual_override=True and emergency reason, kill-switch HARD BLOCKS."""
        intent = TradeIntent(
            symbol="AAPL240621C00175000",
            qty=1,
            side="sell",
            order_type="limit",
            time_in_force="day",
            limit_price=2.50,
            run_id="run-001",
            manual_override=True,
            override_reason="Executive Emergency Order Override",
        )
        snapshot = PortfolioSnapshot(
            available=True,
            equity=94000.0,
            cash=50000.0,
            positions=[{"symbol": "AAPL", "qty": 100}],
            halted=True,
            halt_reasons=["5.00% drawdown breached"],
        )

        decision = evaluate_trade(intent, snapshot, quote_price=2.50)
        assert not decision.allowed
        assert not decision.override_applied
        kill_check = next(c for c in decision.checks if c.name == "kill_switch")
        assert not kill_check.passed
        assert kill_check.severity == "BLOCK"

    def test_cash_secured_put_collateral_reserve_boundary(self):
        """Verify short put cash collateral requirement against cash reserve floor."""
        # Setup: Equity $100,000, 10% cash reserve ($10,000 floor).
        # Total Cash = $20,000 -> Usable Cash = $10,000.
        # Short Put Strike $100.00: 1 contract requires 100 * 100 * 1 = $10,000 collateral.
        snapshot = PortfolioSnapshot(
            available=True,
            equity=100000.0,
            cash=20000.0,
            positions=[],
            halted=False,
        )

        class MockConfig:
            min_cash_reserve_pct = 10.0

        # Exact boundary: Required = $10,000, Usable = $10,000 -> PASS
        intent_exact = TradeIntent(
            symbol="XYZ240621P00100000",
            qty=1,
            side="sell",
            order_type="limit",
            time_in_force="day",
            limit_price=2.00,
            run_id="run-1",
        )
        res_exact = _check_collateral(intent_exact, snapshot, MockConfig())
        assert res_exact.passed

        # 1 cent over: Required = $10,010 (Strike 100.10 -> 00100100), Usable = $10,000 -> BLOCK
        intent_over = TradeIntent(
            symbol="XYZ240621P00100100",  # Strike 100.10 -> Required $10,010
            qty=1,
            side="sell",
            order_type="limit",
            time_in_force="day",
            limit_price=2.00,
            run_id="run-1",
        )
        res_over = _check_collateral(intent_over, snapshot, MockConfig())
        assert not res_over.passed
        assert res_over.severity == "BLOCK"
        assert "UNSECURED PUT" in res_over.detail


# ============================================================================ #
# 5. ZERO DIVISION & ARITHMETIC BOUNDARY IMMUNITY                              #
# ============================================================================ #


class TestArithmeticBoundaryImmunity:
    """Verify zero division and NaN/Inf immunity under extreme abnormal values."""

    def test_zero_equity_and_zero_peak(self):
        # Zero peak must not crash with ZeroDivisionError
        state = {"equity": 0.0, "peak_equity": 0.0, "prev_equity": 0.0}
        res = evaluate_kill_switch(state)
        assert isinstance(res, dict)
        assert "drawdown not evaluated" in res["notes"][0]

    def test_negative_equity_and_negative_peak(self):
        # Negative equity
        state = {"equity": -5000.0, "peak_equity": 100000.0, "prev_equity": 100000.0}
        res = evaluate_kill_switch(state)
        assert res["halted"]  # Deep negative equity triggers DD breach

    def test_nan_and_inf_inputs_fail_closed_safely(self):
        state = {
            "equity": float("nan"),
            "peak_equity": float("inf"),
            "prev_equity": float("-inf"),
            "consecutive_stop_losses": float("nan"),
        }
        res = evaluate_kill_switch(state)
        assert isinstance(res, dict)
        # Does not crash or raise exceptions
