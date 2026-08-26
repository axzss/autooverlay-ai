"""Tests for council handoff consumption: parsing, tier mapping, sector cap."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.council.handoff import (
    DEFAULT_TIER_POLICY, TECH_COMPLEX, TierPolicy,
    effective_policy_for_symbol, get_tier_for_symbol, handoff_as_dicts,
    load_council_handoff, parse_handoff,
)
from agent.config import StrategyConfig
from agent.portfolio_analyst import PortfolioAnalyst
from agent.strategies.covered_call import CoveredCallStrategy
from agent.strategies.cash_secured_put import CashSecuredPutStrategy


# --- Handoff parsing --------------------------------------------------------- #

def test_parse_real_report_matches_council_recommendations():
    policies = load_council_handoff()
    low = policies["low"]
    assert (low.delta_min, low.delta_max) == (0.15, 0.30)
    assert set(low.allowed_strategies) == {"CSP", "COVERED_CALL"}
    assert low.size_multiplier == 1.0
    mid = policies["mid"]
    assert (mid.delta_min, mid.delta_max) == (0.10, 0.25)
    assert mid.size_multiplier == 0.5  # reduced size
    high = policies["high"]
    assert (high.delta_min, high.delta_max) == (0.05, 0.15)
    assert high.max_dte == 30
    assert high.allowed_strategies == ("COVERED_CALL",)   # covered-call only


def test_parse_falls_back_to_defaults_on_garbage():
    policies = parse_handoff("no handoff section here at all")
    for tier in ("low", "mid", "high"):
        d = policies[tier].to_dict()
        ref = DEFAULT_TIER_POLICY[tier].to_dict()
        for key in ("delta_min", "delta_max", "max_dte", "size_multiplier"):
            assert d[key] == ref[key]


def test_tsla_override_parsed_and_applied():
    pol, notes = effective_policy_for_symbol("TSLA", 59.1)
    assert pol.delta_max <= 0.10          # council TSLA override
    assert pol.size_multiplier == 0.5     # half-size
    assert any("OVERRIDE" in n for n in notes)
    # ...but the override lifts once vol < 45%
    pol2, _ = effective_policy_for_symbol("TSLA", 44.0)
    assert pol2.delta_max == pytest.approx(0.15)


# --- Tier mapping ------------------------------------------------------------ #

VOLS = {"SPY": 12.2, "JPM": 17.6, "QQQ": 21.5, "KO": 24.4, "AAPL": 30.5,
        "NVDA": 35.9, "MSFT": 48.9, "TSLA": 59.1}
EXPECTED = {"SPY": "low", "JPM": "low", "QQQ": "mid", "KO": "mid",
            "AAPL": "mid", "NVDA": "high", "MSFT": "high", "TSLA": "high"}


@pytest.mark.parametrize("sym", list(VOLS))
def test_tier_boundaries_match_report(sym):
    assert get_tier_for_symbol(sym, VOLS[sym]) == EXPECTED[sym]


def test_boundary_values():
    assert get_tier_for_symbol("X", 19.99) == "low"
    assert get_tier_for_symbol("X", 20.0) == "mid"
    assert get_tier_for_symbol("X", 35.0) == "mid"
    assert get_tier_for_symbol("X", 35.01) == "high"


def test_bad_vol_is_conservative_high():
    assert get_tier_for_symbol("X", None) == "high"
    assert get_tier_for_symbol("X", "n/a") == "high"


# --- Strategies consume tier policy ------------------------------------------ #

def _put(strike=100, delta=0.20, dte=30, price=100, premium=3.0):
    return {"symbol": "TEST", "strike_price": strike, "delta": delta,
            "days_to_expiry": dte, "underlying_price": price,
            "premium_received_per_share": premium}


def _call(delta=0.20, **kw):
    return _put(**kw) | {"delta": delta}


def test_config_defaults_win_without_policy():
    s = CashSecuredPutStrategy()
    assert (s.min_delta, s.max_delta) == (0.15, 0.35)


def test_mid_tier_shifts_delta_band_and_size():
    pol = DEFAULT_TIER_POLICY["mid"]
    s = CashSecuredPutStrategy(tier_policy=pol, config=None)
    assert (s.min_delta, s.max_delta) == (0.10, 0.25)
    assert s.size_multiplier == 0.5
    res = s.screen([_put(premium=5.0)], account_cash=1_000_000)
    assert res and res[0]["tier_size_multiplier"] == 0.5
    assert any("council tier sizing" in line
               for line in res[0]["reasoning_trace"])


def test_explicit_args_beat_tier_policy():
    s = CashSecuredPutStrategy(min_delta=0.30, max_delta=0.31,
                               tier_policy=DEFAULT_TIER_POLICY["high"])
    assert (s.min_delta, s.max_delta) == (0.30, 0.31)


def test_high_tier_blocks_csp_with_council_trace():
    s = CashSecuredPutStrategy(tier_policy=DEFAULT_TIER_POLICY["high"])
    res = s.screen([_put(delta=0.10)], account_cash=1_000_000)
    assert len(res) == 1
    r = res[0]
    assert r["recommendation"] == "BLOCKED_BY_COUNCIL_TIER"
    joined = " ".join(r["reasoning_trace"])
    assert "council" in joined.lower() and "blocked" in joined.lower()


def test_covered_call_high_tier_delta_band_and_dte():
    s = CoveredCallStrategy(tier_policy=DEFAULT_TIER_POLICY["high"])
    assert (s.min_delta, s.max_delta) == (0.05, 0.15)
    assert s.max_dte == 30
    pos = [{"symbol": "TEST", "qty": 100, "avg_entry_price": 90}]
    ok = s.screen([_call(delta=0.10, strike=105, premium=4.0)],
                  positions=pos)
    too_far = s.screen([_call(delta=0.10, strike=105, premium=4.0, dte=40)],
                       positions=pos)
    too_rich = s.screen([_call(delta=0.20, strike=105, premium=4.0)],
                        positions=pos)
    assert ok and not too_far and not too_rich


# --- Sector concentration cap ------------------------------------------------ #

def _tech_positions():
    # AAPL $50k + MSFT $30k + NVDA $10k tech = $90k of $210k deployed (~42.9%)
    return [
        {"symbol": "AAPL", "market_value": 50_000},
        {"symbol": "MSFT", "market_value": 30_000},
        {"symbol": "NVDA", "market_value": 10_000},
        {"symbol": "JPM", "market_value": 60_000},
        {"symbol": "KO", "market_value": 60_000},
    ]


def test_sector_cap_blocks_fourth_tech_entry():
    pa = PortfolioAnalyst(config=StrategyConfig())
    allowed, trace = pa.check_new_position(
        "QQQ", collateral_required=20_000,
        existing_overlay_value_for_symbol=0.0,
        portfolio_value=250_000, account_cash=200_000,
        existing_positions=_tech_positions())
    assert not allowed
    joined = " ".join(trace)
    assert "council" in joined.lower() and "40%" in joined


def test_sector_cap_allows_nontech_entry():
    pa = PortfolioAnalyst(config=StrategyConfig())
    allowed, trace = pa.check_new_position(
        "JPM", collateral_required=20_000,
        existing_overlay_value_for_symbol=0.0,
        portfolio_value=250_000, account_cash=200_000,
        existing_positions=_tech_positions())
    assert allowed
    assert any("sector-cap" in line for line in trace)


def test_sector_cap_configurable():
    pa = PortfolioAnalyst(config=StrategyConfig(
        max_sector_concentration_pct=10.0))
    allowed, _ = pa.check_sector_cap("AAPL", 5_000, _tech_positions())
    assert not allowed


def test_qqq_counts_as_tech_not_diversifier():
    pa = PortfolioAnalyst(config=StrategyConfig())
    positions = [{"symbol": "QQQ", "market_value": 80_000}] * 1 + \
                [{"symbol": "SPY", "market_value": 120_000}]
    allowed, trace = pa.check_sector_cap("AAPL", 10_000, positions)
    assert not allowed  # QQQ $80k + new AAPL $10k vs deployed $210k ≈ 42.9%


def test_strategyconfig_has_default_sector_fields():
    cfg = StrategyConfig()
    assert cfg.max_sector_concentration_pct == 40.0
    assert tuple(cfg.sector_cap_group) == TECH_COMPLEX
