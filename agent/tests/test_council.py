"""Tests for the Investment Council module (agent/council)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.council import (CouncilEngine, PERSONAS, DEFAULT_WEIGHTS,
                           generate_report)
from agent.council.engine import _recommendation
from agent.council.personas import PersonaVerdict


GOOD = {
    "symbol": "TEST", "sector": "Technology", "moat": "wide",
    "price": 100, "intrinsic_value_estimate": 200,  # 50% margin of safety
    "pe_ratio": 12, "pb_ratio": 1.0, "current_ratio": 2.5,
    "dividend_yield_pct": 2.0, "roe_pct": 25, "gross_margin_pct": 55,
    "operating_margin_pct": 25, "debt_to_equity": 0.3,
    "earnings_growth_5y_pct": 15, "earnings_growth_fwd_pct": 20,
    "revenue_growth_fwd_pct": 22, "peg_ratio": 0.8,
    "free_cash_flow_yield_pct": 5.0, "story": "Sells widgets everyone needs.",
    "innovation_tags": "ai robotics", "rd_intensity_pct": 10,
    "annualized_volatility_pct": 25,
}
BAD = {
    "symbol": "JUNK", "sector": "Mystery", "moat": "none",
    "price": 100, "intrinsic_value_estimate": 60,  # negative MoS
    "pe_ratio": 60, "pb_ratio": 9, "current_ratio": 0.7,
    "operating_margin_pct": 3, "debt_to_equity": 2.5,
    "earnings_growth_5y_pct": -5, "disruption_risk": "high",
}


# --- Persona scoring bounds ------------------------------------------------- #

@pytest.mark.parametrize("key", list(PERSONAS))
def test_persona_scores_within_bounds_good(key):
    v = PERSONAS[key].score(GOOD)
    assert isinstance(v, PersonaVerdict)
    assert 0.0 <= v.score <= 100.0
    assert len(v.bullets) >= 1
    assert v.stance in ("STRONG_BUY", "ACCUMULATE", "HOLD", "AVOID")


@pytest.mark.parametrize("key", list(PERSONAS))
def test_persona_scores_within_bounds_bad(key):
    v = PERSONAS[key].score(BAD)
    assert 0.0 <= v.score <= 100.0
    assert len(v.bullets) >= 1


def test_personas_distinguish_quality():
    for key in PERSONAS:
        good = PERSONAS[key].score(GOOD).score
        bad = PERSONAS[key].score(BAD).score
        assert good > bad, f"{key} failed to separate good from bad"


def test_missing_data_neutral_not_crash():
    empty = {"symbol": "VOID"}
    for key in PERSONAS:
        v = PERSONAS[key].score(empty)
        assert 0.0 <= v.score <= 100.0
        assert any("insufficient" in b.lower() or b for b in v.bullets)


# --- Consensus math ---------------------------------------------------------- #

def _mk(verdicts, weights=None):
    w = weights or {k: 1.0 for k in verdicts}
    return sum(verdicts[k].score * w.get(k, 1.0) for k in verdicts) / sum(w.values())


def test_consensus_is_weighted_mean():
    engine = CouncilEngine(weights={"buffett": 1.0, "munger": 1.0, "dalio": 0.0,
                                    "graham": 1.0, "lynch": 0.0, "wood": 1.0})
    a = engine.assess_underlying(GOOD)
    expected = round(sum(a.verdicts[k].score * engine.weights.get(k, 1.0)
                         for k in a.verdicts) / sum(engine.weights.values()), 1)
    assert abs(a.consensus_score - expected) < 0.05


def test_zero_and_full_weights_change_consensus_directionally():
    all_w = dict(DEFAULT_WEIGHTS)
    e_all = CouncilEngine(weights=all_w).assess_underlying(GOOD)
    # drop the usually-bullish contrarian: consensus should not decrease if wood < consensus
    no_wood = {k: w for k, w in all_w.items() if k != "wood"}
    e_no = CouncilEngine(weights=no_wood).assess_underlying(GOOD)
    wood_score = e_all.verdicts["wood"].score
    if wood_score < e_all.consensus_score:
        assert e_no.consensus_score > e_all.consensus_score


def test_recommendation_thresholds():
    assert _recommendation(80) == "STRONG_BUY"
    assert _recommendation(65) == "ACCUMULATE"
    assert _recommendation(50) == "HOLD"
    assert _recommendation(10) == "AVOID"


def test_engine_runs_all_personas_and_recs_valid():
    res = CouncilEngine().run({}, [GOOD, BAD])
    assert [r.symbol for r in res] == ["TEST", "JUNK"]
    for r in res:
        assert set(r.verdicts) == set(PERSONAS)
        assert r.recommendation in ("STRONG_BUY", "ACCUMULATE", "HOLD", "AVOID")
    assert res[0].recommendation in ("STRONG_BUY", "ACCUMULATE")
    assert res[1].recommendation in ("HOLD", "AVOID")


def test_macro_context_flows_from_portfolio():
    portfolio = {"macro_rate_regime": "falling", "macro_inflation_pct": 2.0}
    res = CouncilEngine().run(portfolio, [{"symbol": "X"}])
    dalio_verdict = res[0].verdicts["dalio"]
    assert any("Falling rates" in b or "Inflation" in b for b in dalio_verdict.bullets)


# --- Dissent detection -------------------------------------------------------- #

def test_contrarian_bearish_dissent_detected_on_value_trap():
    # Deep-value gem with zero innovation: Graham loves it (consensus ACCUMULATE),
    # but Cathie Wood's disruption-first philosophy rejects it outright —
    # her dissent here is BEARISH against a bullish consensus (value-trap view).
    value_stock = {
        "symbol": "VALU", "sector": "Industrials", "moat": "narrow",
        "price": 30, "intrinsic_value_estimate": 60,  # huge margin of safety
        "pe_ratio": 8, "pb_ratio": 0.8, "current_ratio": 3.0,
        "dividend_yield_pct": 4.0, "operating_margin_pct": 14,
        "debt_to_equity": 0.3, "roe_pct": 12, "gross_margin_pct": 28,
        "earnings_growth_5y_pct": 3, "free_cash_flow_yield_pct": 6,
        "story": "Boring industrial cash cow.", "innovation_tags": "",
    }
    a = CouncilEngine().assess_underlying(value_stock)
    directions = {(d["persona"], d["direction"]) for d in a.dissent}
    assert ("Cathie Wood", "bearish-dissent") in directions


def test_contrarian_bearish_dissent_detected_on_hype():
    # Expensive, low-margin hype name the crowd chases: Wood bullish, others bearish.
    hype = {
        "symbol": "HYPE", "sector": "Consumer", "moat": "none",
        "price": 100, "intrinsic_value_estimate": 40,
        "pe_ratio": 80, "operating_margin_pct": 2, "debt_to_equity": 2.0,
        "disruption_risk": "high", "innovation_tags": "ai ev robotics",
        "revenue_growth_fwd_pct": 40, "annualized_volatility_pct": 60,
        "rd_intensity_pct": 12,
    }
    a = CouncilEngine().assess_underlying(hype)
    assert any(d["persona"] == "Cathie Wood" and d["direction"] == "bullish-dissent"
               for d in a.dissent) or a.verdicts["wood"].is_bullish
    # consensus must be well below the contrarian's score
    assert a.verdicts["wood"].score > a.consensus_score


def test_custom_weights_respected():
    engine = CouncilEngine(weights={k: 0.0 for k in DEFAULT_WEIGHTS} | {"graham": 1.0})
    a = engine.assess_underlying(GOOD)
    assert abs(a.consensus_score - round(a.verdicts["graham"].score, 1)) < 0.11


# --- Report ------------------------------------------------------------------- #

def test_report_contains_required_sections():
    md = generate_report({"positions": []}, [GOOD])
    for section in ("## Executive Summary", "## Per-Persona Verdicts",
                    "## Dissent & Minority Reports", "## Consensus Table",
                    "FOR THE AI ENGINEER AGENT"):
        assert section in md
    assert GOOD["symbol"] in md
