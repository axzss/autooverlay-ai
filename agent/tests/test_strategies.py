"""Unit tests for agent strategy modules: covered call, cash-secured put,
and decision engine.

Contract under test (per current implementations):
- screen()/evaluate() return rows with an integer risk score 0-100,
  a recommendation label, and a written rationale string.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from agent.strategies.covered_call import CoveredCallStrategy  # noqa: E402
from agent.strategies.cash_secured_put import CashSecuredPutStrategy  # noqa: E402
from agent.decision_engine import DecisionEngine  # noqa: E402

VALID_RECS = {"INITIATE_POSITION", "HOLD_POSITION", "MONITOR_CLOSELY"}

AS_OF = datetime(2026, 8, 25, 12, 0, 0)


def _expiry(days_out: int) -> str:
    return (AS_OF + timedelta(days=days_out)).strftime("%Y-%m-%dT12:00:00Z")


def _csp_opp(**overrides):
    """CSP candidate: AAPL @ $180, sell 145 put ~21 DTE."""
    opp = {
        "symbol": "AAPL",
        "option_symbol": "AAPL260918P00145000",
        "underlying_price": 180.0,
        "strike_price": 145.0,
        "last_price": 2.50,          # ~6.3% ann. cash-secured yield... low; use 4.50 below as needed
        "bid": 4.40,
        "ask": 4.60,
        "delta": -0.20,
        "implied_volatility": 0.35,
        "expiration_date": _expiry(21),
    }
    opp.update(overrides)
    return opp


def _cc_opp(**overrides):
    """CC candidate: MSFT held at 400, spot 420, sell 460 call ~21 DTE."""
    opp = {
        "symbol": "MSFT",
        "option_symbol": "MSFT260918C00460000",
        "underlying_price": 420.0,
        "strike_price": 460.0,
        "last_price": 5.00,          # ~1.19%/3wk -> ~20.7% annualized
        "bid": 4.90,
        "ask": 5.10,
        "delta": 0.25,
        "implied_volatility": 0.28,
        "expiration_date": _expiry(21),
    }
    opp.update(overrides)
    return opp


POSITION = {"symbol": "MSFT", "qty": 100, "avg_entry_price": 400.00}


def assert_valid_row(row):
    assert isinstance(row["risk_score"], int), f"risk_score must be int, got {type(row['risk_score'])}"
    assert 0 <= row["risk_score"] <= 100
    assert row["recommendation"] in VALID_RECS
    rationale = row["rationale"]
    assert isinstance(rationale, str) and len(rationale) > 20
    assert row["recommendation"] in rationale, "rationale should state the recommendation"


# ---------------------------------------------------------------------------
# Cash Secured Put
# ---------------------------------------------------------------------------

class TestCashSecuredPut:
    def setup_method(self):
        self.strategy = CashSecuredPutStrategy()

    def test_valid_opportunity_produces_risk_score_rec_and_rationale(self):
        results = self.strategy.screen([_csp_opp()], account_cash=50_000, as_of=AS_OF)
        assert len(results) == 1
        assert_valid_row(results[0])
        assert results[0]["strategy"] == "CASH_SECURED_PUT"
        assert results[0]["symbol"] == "AAPL"

    def test_dte_out_of_range_filtered(self):
        near = _csp_opp(expiration_date=_expiry(3))
        far = _csp_opp(symbol="TSLA", expiration_date=_expiry(90))
        assert self.strategy.screen([near, far], account_cash=50_000, as_of=AS_OF) == []

    def test_delta_out_of_band_filtered(self):
        deep_itm = _csp_opp(delta=-0.80)
        far_otm = _csp_opp(delta=-0.05)
        assert self.strategy.screen(
            [deep_itm, far_otm], account_cash=50_000, as_of=AS_OF
        ) == []

    def test_insufficient_cash_filtered(self):
        assert self.strategy.screen([_csp_opp()], account_cash=1_000, as_of=AS_OF) == []

    def test_zero_premium_filtered(self):
        no_prem = _csp_opp(last_price=0, bid=None, ask=None)
        assert self.strategy.screen([no_prem], account_cash=50_000, as_of=AS_OF) == []

    def test_high_yield_low_risk_initiates(self):
        # premium 5.0 on 145 strike, 30 DTE -> ~8.4%... use bigger premium for >25% ann.
        hot = _csp_opp(last_price=10.0, bid=9.9, ask=10.1,
                       implied_volatility=0.40, delta=-0.20)
        results = self.strategy.screen([hot], account_cash=50_000, as_of=AS_OF)
        assert len(results) == 1
        assert results[0]["recommendation"] == "INITIATE_POSITION"

    def test_extreme_inputs_keep_risk_score_bounded(self):
        spicy = _csp_opp(delta=-0.34, implied_volatility=3.0, expiration_date=_expiry(8))
        results = self.strategy.screen([spicy], account_cash=50_000, as_of=AS_OF)
        assert len(results) == 1
        assert isinstance(results[0]["risk_score"], int)
        assert results[0]["risk_score"] <= 100

    def test_results_sorted_by_annualized_yield_descending(self):
        low = _csp_opp(symbol="LOW", last_price=1.0, bid=0.95, ask=1.05,
                       delta=-0.15, expiration_date=_expiry(44))
        high = _csp_opp(symbol="HIGH", last_price=12.0, bid=11.9, ask=12.1,
                        delta=-0.30, expiration_date=_expiry(10))
        results = self.strategy.screen([high, low], account_cash=200_000, as_of=AS_OF)
        yields = [r["annualized_premium_yield"] for r in results]
        assert yields == sorted(yields, reverse=True)

    def test_malformed_expiry_skipped_not_crash(self):
        bad = _csp_opp(expiration_date="not-a-date")
        assert self.strategy.screen([bad], account_cash=50_000, as_of=AS_OF) == []

    def test_days_to_expiry_key_preferred_over_date_parsing(self):
        fixed = _csp_opp(expiration_date=None, days_to_expiry=21)
        results = self.strategy.screen([fixed], account_cash=50_000, as_of=AS_OF)
        assert len(results) == 1 and results[0]["dte"] == 21

    def test_strike_below_cost_basis_flagged_when_held(self):
        positions = [{"symbol": "AAPL", "qty": 100, "avg_entry_price": 190.0}]
        results = self.strategy.screen([_csp_opp()], account_cash=50_000,
                                       positions=positions, as_of=AS_OF)
        assert results[0]["strike_below_cost_basis"] is True


# ---------------------------------------------------------------------------
# Covered Call
# ---------------------------------------------------------------------------

class TestCoveredCall:
    def setup_method(self):
        self.strategy = CoveredCallStrategy()

    def test_requires_existing_full_lot(self):
        assert self.strategy.screen([_cc_opp()], positions=[], as_of=AS_OF) == []
        partial = [{"symbol": "MSFT", "qty": 50, "avg_entry_price": 400}]
        assert self.strategy.screen([_cc_opp()], positions=partial, as_of=AS_OF) == []
        assert self.strategy.screen(
            [_cc_opp()], positions=[dict(POSITION)], as_of=AS_OF
        ) != []

    def test_wrong_symbol_holding_skipped(self):
        assert self.strategy.screen(
            [_cc_opp()], positions=[{"symbol": "AAPL", "qty": 100}], as_of=AS_OF
        ) == []

    def test_valid_position_produces_risk_rec_and_rationale(self):
        results = self.strategy.screen([_cc_opp()], positions=[dict(POSITION)], as_of=AS_OF)
        assert len(results) == 1
        row = results[0]
        assert_valid_row(row)
        assert row["strategy"] == "COVERED_CALL"
        assert row["contracts"] == 1 and row["shares_covered"] == 100
        assert row["strike_above_cost_basis"] is True

    def test_delta_out_of_band_skipped(self):
        assert self.strategy.screen(
            [_cc_opp(delta=0.05), _cc_opp(delta=0.9)],
            positions=[dict(POSITION)], as_of=AS_OF,
        ) == []

    def test_negative_qty_position_excluded(self):
        neg = {"symbol": "MSFT", "qty": -100, "avg_entry_price": 400}
        assert self.strategy.screen([_cc_opp()], positions=[neg], as_of=AS_OF) == []

    def test_multiple_lots_produce_matching_contract_count(self):
        pos = {"symbol": "MSFT", "qty": 300, "avg_entry_price": 400}
        results = self.strategy.screen([_cc_opp()], positions=[pos], as_of=AS_OF)
        assert results[0]["contracts"] == 3

    def test_strong_yield_strike_above_basis_initiates(self):
        hot = _cc_opp(last_price=8.0, bid=7.9, ask=8.1,
                      implied_volatility=0.25, delta=0.18)
        results = self.strategy.screen([hot], positions=[dict(POSITION)], as_of=AS_OF)
        assert results[0]["recommendation"] == "INITIATE_POSITION"

    def test_low_yield_monitors_closely(self):
        weak = _cc_opp(last_price=0.50, bid=0.45, ask=0.55, delta=0.16)
        results = self.strategy.screen([weak], positions=[dict(POSITION)], as_of=AS_OF)
        assert results[0]["recommendation"] == "MONITOR_CLOSELY"

    def test_strike_below_basis_raises_risk_score(self):
        above = self.strategy.screen([_cc_opp(strike_price=430.0)],
                                     positions=[dict(POSITION)], as_of=AS_OF)[0]
        below = self.strategy.screen([_cc_opp(strike_price=380.0)],
                                     positions=[dict(POSITION)], as_of=AS_OF)[0]
        assert below["strike_above_cost_basis"] is False
        assert below["risk_score"] > above["risk_score"]

    def test_sorted_by_annualized_yield_descending(self):
        a = _cc_opp(symbol="AAA", last_price=0.80, bid=0.75, ask=0.85)
        b = _cc_opp(symbol="BBB", last_price=8.00, bid=7.9, ask=8.1)
        positions = [
            {"symbol": "AAA", "qty": 100, "avg_entry_price": 100},
            {"symbol": "BBB", "qty": 100, "avg_entry_price": 400},
        ]
        results = self.strategy.screen([a, b], positions, as_of=AS_OF)
        yields = [r["annualized_premium_yield"] for r in results]
        assert yields == sorted(yields, reverse=True)

    def test_malformed_expiry_skipped_not_crash(self):
        bad = _cc_opp(expiration_date="garbage")
        assert self.strategy.screen([bad], positions=[dict(POSITION)], as_of=AS_OF) == []


# ---------------------------------------------------------------------------
# Decision Engine
# ---------------------------------------------------------------------------

HOT_CSP = dict(last_price=10.0, bid=9.9, ask=10.1, implied_volatility=0.40, delta=-0.20)
HOT_CC = dict(last_price=8.0, bid=7.9, ask=8.1, implied_volatility=0.25, delta=0.18)


class TestDecisionEngine:
    def setup_method(self):
        self.engine = DecisionEngine(account_cash=100_000)

    def test_evaluate_output_structure(self):
        out = self.engine.evaluate(
            csp_opportunities=[_csp_opp()],
            cc_opportunities=[_cc_opp()],
            positions=[dict(POSITION)],
        )
        for key in ("csp_results", "cc_results", "ranked_recommendations",
                    "actions", "portfolio_health", "timestamp"):
            assert key in out
        assert out["timestamp"].endswith("Z")

    def test_all_screened_rows_have_valid_risk_scores_and_rationales(self):
        out = self.engine.evaluate(
            csp_opportunities=[_csp_opp(), _csp_opp(symbol="NVDA", last_price=15.0,
                                                    bid=14.9, ask=15.1, delta=-0.30,
                                                    underlying_price=200.0,
                                                    strike_price=160.0)],
            cc_opportunities=[_cc_opp()],
            positions=[dict(POSITION)],
        )
        rows = out["ranked_recommendations"]
        assert rows, "expected at least one screened opportunity"
        for r in rows:
            assert isinstance(r["risk_score"], int)
            assert 0 <= r["risk_score"] <= 100
            assert r["recommendation"] in VALID_RECS
            assert isinstance(r["rationale"], str) and r["rationale"]

    def test_actions_derived_only_from_initiate_positions(self):
        out = self.engine.evaluate(
            csp_opportunities=[_csp_opp(**HOT_CSP)],
            cc_opportunities=[_cc_opp(**HOT_CC)],
            positions=[dict(POSITION)],
        )
        actions = out["actions"]
        assert {a["type"] for a in actions} <= {"CASH_SECURED_PUT", "COVERED_CALL"}
        for a in actions:
            assert a["action"] == "SELL_TO_OPEN"
            assert isinstance(a["risk_score"], int) and 0 <= a["risk_score"] <= 100
            assert isinstance(a["rationale"], str) and a["rationale"]
            assert a["rationale"] == a["reasoning"]
        initiated = [r for r in out["ranked_recommendations"]
                     if r["recommendation"] == "INITIATE_POSITION"]
        assert len(actions) == len(initiated)

    def test_no_opportunities_yields_empty_actions_and_neutral_health(self):
        out = self.engine.evaluate(csp_opportunities=[], cc_opportunities=[],
                                   positions=[])
        assert out["actions"] == []
        h = out["portfolio_health"]
        assert h["total_positions"] == 0
        assert h["screened_opportunities"] == 0
        assert h["actionable_opportunities"] == 0
        assert h["average_risk_score_0_100"] == 0.0
        assert h["health"] in ("HEALTHY", "ELEVATED_RISK", "HIGH_RISK")

    def test_portfolio_health_reflects_positions_and_lot_coverage(self):
        positions = [dict(POSITION),
                     {"symbol": "TINY", "qty": 40, "avg_entry_price": 10}]
        out = self.engine.evaluate(
            csp_opportunities=[], cc_opportunities=[], positions=positions
        )
        h = out["portfolio_health"]
        assert h["total_positions"] == 2
        assert h["positions_with_full_lots"] == 1
        assert h["lot_coverage_ratio"] == 0.5
