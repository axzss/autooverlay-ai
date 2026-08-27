"""Book-accurate Graham persona + Mr. Market tests (The Intelligent Investor,
Ch. 8 / Ch. 14 / Ch. 20 thresholds)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.council.graham_principles import (
    DEFENSIVE_CRITERIA, evaluate_defensive, inversion_checks,
    margin_of_safety_pct, MARGIN_OF_SAFETY,
)
from agent.council.mr_market import classify_market_mood, mr_market_context
from agent.council.personas import PERSONAS


# --- Chapter 14 constants transcribed correctly ------------------------------ #

def test_book_thresholds():
    assert DEFENSIVE_CRITERIA[1]["min_annual_sales_musd_industrial"] == 100
    assert DEFENSIVE_CRITERIA[2]["min_current_ratio"] == 2.0
    assert DEFENSIVE_CRITERIA[3]["required_positive_earnings_years"] == 10
    assert DEFENSIVE_CRITERIA[4]["required_uninterrupted_dividend_years"] == 20
    assert DEFENSIVE_CRITERIA[5]["min_10y_eps_growth_pct"] >= 33
    assert DEFENSIVE_CRITERIA[6]["max_pe_on_avg_earnings"] == 15.0
    assert DEFENSIVE_CRITERIA[7]["max_price_to_book"] == 1.5
    assert DEFENSIVE_CRITERIA[7]["max_pe_times_pb"] == 22.5
    assert MARGIN_OF_SAFETY["min_margin_of_safety_pct"] >= 33


# --- evaluate_defensive ------------------------------------------------------- #

def _full_passing():
    return {
        "annual_sales_musd": 5000, "current_ratio": 2.5,
        "long_term_debt_to_working_capital": 0.4,
        "positive_earnings_years": [1] * 10,
        "dividend_years_paid": [True] * 20,
        "earnings_growth_10y_pct": 40.0,
        "pe_ratio": 12, "pb_ratio": 1.2,
    }


def test_all_seven_tests_pass():
    res = {r["test"]: r for r in evaluate_defensive(_full_passing())}
    assert len(res) == 7
    assert all(res[n]["passed"] for n in range(1, 8))


def test_each_failure_is_detected_individually():
    base = _full_passing()
    mutations = {
        1: {"annual_sales_musd": 50},
        2: {"current_ratio": 1.2},
        3: {"positive_earnings_years": [1] * 9 + [-1]},
        4: {"dividend_years_paid": [True] * 19 + [False]},
        5: {"earnings_growth_10y_pct": 10.0},
        6: {"pe_ratio": 20},
        7: {"pb_ratio": 2.0},
    }
    for n, m in mutations.items():
        u = dict(base); u.update(m)
        res = {r["test"]: r for r in evaluate_defensive(u)}
        assert res[n]["passed"] is False, f"test {n} should fail on mutation"
        others = [res[k]["passed"] for k in res if k != n]
        # test 7 interacts with test 6 via PExPB; everything else must still pass
        if n != 7:
            assert all(others), f"mutation for test {n} leaked into other tests"


def test_pe_pb_product_tradeoff_ch14():
    """9x earnings may justify 2.5x assets (product <= 22.5)."""
    u = dict(_full_passing()); u.update({"pb_ratio": 2.4})
    res = {r["test"]: r for r in evaluate_defensive(u)}
    assert res[7]["passed"] is False  # 1.5 < 2.4 and 12*2.4=28.8 > 22.5

    u2 = dict(_full_passing()); u2.update({"pe_ratio": 9, "pb_ratio": 2.4})
    res2 = {r["test"]: r for r in evaluate_defensive(u2)}
    assert res2[7]["passed"] is True   # 9*2.4=21.6 <= 22.5

    u3 = dict(_full_passing()); u3.update({"pe_ratio": 14, "pb_ratio": 1.8})
    res3 = {r["test"]: r for r in evaluate_defensive(u3)}
    assert res3[7]["passed"] is False  # 1.8 > 1.5 and 25.2 > 22.5


def test_missing_data_is_inconclusive_not_failing():
    res = evaluate_defensive({})
    assert all(r["passed"] is None for r in res)


# --- Margin of safety & inversion (Ch. 20) ------------------------------------ #

def test_margin_of_safety_math():
    assert margin_of_safety_pct(60, 180) == pytest.approx(66.67, abs=0.01)
    assert margin_of_safety_pct(200, 100) < 0
    assert margin_of_safety_pct(None, 100) is None


def test_inversion_checks_flag_thin_cushion_and_rich_pe():
    thin = {"price": 95, "intrinsic_value_estimate": 100}
    notes = " ".join(inversion_checks(thin))
    assert "margin" in notes.lower()

    rich = {"price": 100, "pe_ratio": 45}
    notes = " ".join(inversion_checks(rich))
    assert "downside" in notes and "-6" in notes  # reversion to 15x => ~-67%


def test_inversion_flags_growth_dependence():
    u = {"eps_trailing": 1.0, "eps_fwd_estimate": 1.5}
    notes = " ".join(inversion_checks(u))
    assert "growth" in notes.lower()


# --- Graham persona scoring ---------------------------------------------------- #

BOOK_GRAHAM = dict(
    _full_passing(),
    symbol="GVAL", price=65, intrinsic_value_estimate=120,
    earnings_yield_pct=8.5, bond_yield_pct=4.5,
)

def test_graham_persona_bullets_cite_tests():
    v = PERSONAS["graham"].score(BOOK_GRAHAM)
    text = " ".join(v.bullets)
    for n in range(1, 8):
        assert f"test {n}" in text
    assert "Margin of safety" in text or "margin of safety" in text.lower()
    assert any("Inversion" in b for b in v.bullets)


def test_graham_persona_separates_book_good_from_book_bad():
    bad = {
        "symbol": "JUNK", "annual_sales_musd": 40, "current_ratio": 0.9,
        "long_term_debt_to_working_capital": 3.0,
        "positive_earnings_years": [-1, -1, 1, 0, -2],
        "dividend_years_paid": [True] * 5 + [False] * 15,
        "earnings_growth_10y_pct": -10.0,
        "pe_ratio": 40, "pb_ratio": 8,
        "price": 100, "intrinsic_value_estimate": 55,
    }
    good = PERSONAS["graham"].score(dict(BOOK_GRAHAM)).score
    junk = PERSONAS["graham"].score(bad).score
    assert good > junk + 25
    assert good >= 70 and junk <= 35


def test_graham_fails_test_4_bullet_present():
    u = dict(BOOK_GRAHAM)
    u["dividend_years_paid"] = [True] * 18  # interrupted/insufficient record
    v = PERSONAS["graham"].score(u)
    assert any("test 4" in b and ("Fails" in b) for b in v.bullets)


# --- Mr. Market module (Ch. 8) -------------------------------------------------- #

def test_mr_market_panicky_when_crashing():
    prices = [100, 97, 92, 85, 80]
    mood = classify_market_mood(prices)
    assert mood.mood == "panicky"
    assert mood.is_favorable_for_buying
    assert any("businessman" in g.lower() for g in mood.guidance)


def test_mr_market_euphoric_after_runup():
    prices = [100, 105, 112, 118, 125]
    mood = classify_market_mood(prices)
    assert mood.mood == "euphoric"
    assert mood.is_warning_against_buying
    assert any("wary" in g.lower() or "refrain" in g.lower() for g in mood.guidance)


def test_mr_market_indifferent_in_quiet_tape():
    prices = [100, 101, 100, 102, 101]
    mood = classify_market_mood(prices)
    assert mood.mood == "indifferent"
    assert not mood.is_favorable_for_buying and not mood.is_warning_against_buying


def test_mr_market_unknown_without_data():
    mood = classify_market_mood([])
    assert mood.mood == "unknown"


def test_engine_wires_mr_market_context():
    from agent.council import CouncilEngine
    eng = CouncilEngine()
    a = eng.assess_underlying({
        **dict(BOOK_GRAHAM),
        "recent_prices": [100, 98, 90, 84, 78],
    })
    ctx = a.mr_market_context
    assert isinstance(ctx, dict) and ctx["mood"] == "panicky"
    assert "guidance" in ctx
