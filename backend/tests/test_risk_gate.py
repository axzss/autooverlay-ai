"""Pre-trade risk gate — one test per check, both directions.

The gate is a pure function, so these tests construct `PortfolioSnapshot`
directly and never touch the network or the route layer. Route-level behaviour
(409 vs 200 vs 502) lives in `test_trade_route_risk.py`.

Every test here fails against ddcc665, where no gate existed.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from agent.config import StrategyConfig
from backend.app.risk import PortfolioSnapshot, TradeIntent, evaluate_trade

TODAY = date(2026, 9, 1)


def _occ(days_out: int, kind: str = "C", strike: float = 175.0, root: str = "AAPL") -> str:
    exp = TODAY + timedelta(days=days_out)
    return f"{root}{exp:%y%m%d}{kind}{int(strike * 1000):08d}"


def _snapshot(**kwargs) -> PortfolioSnapshot:
    defaults = dict(
        available=True,
        equity=100_000.0,
        cash=50_000.0,
        positions=[],
        open_option_positions=[],
        halted=False,
        mode="mock",
    )
    defaults.update(kwargs)
    return PortfolioSnapshot(**defaults)


def _intent(**kwargs) -> TradeIntent:
    defaults = dict(
        symbol=_occ(30),
        qty=1,
        side="sell",
        order_type="limit",
        time_in_force="day",
        limit_price=2.50,
        run_id="run-abc123",
    )
    defaults.update(kwargs)
    return TradeIntent(**defaults)


def _shares(symbol: str, qty: float, market_value: float = 0.0) -> dict:
    return {
        "symbol": symbol,
        "qty": str(qty),
        "asset_class": "us_equity",
        "market_value": str(market_value),
    }


def _short_option(option_symbol: str, contracts: int = 1) -> dict:
    from backend.app.adapters.options import parse_occ

    occ = parse_occ(option_symbol)
    return {
        "symbol": occ.underlying,
        "option_symbol": option_symbol,
        "option_type": occ.option_type,
        "qty": -contracts,
        "strike_price": occ.strike,
    }


def _decide(intent, snapshot, config=None, **kwargs):
    return evaluate_trade(intent, snapshot, config, today=TODAY, **kwargs)


def _check(decision, name):
    return next(c for c in decision.checks if c.name == name)


# --- check 1: state availability (fail closed) ----------------------------


def test_unreadable_portfolio_state_blocks_the_order():
    """A gate that opens when it cannot see manufactures unearned confidence."""
    decision = _decide(
        _intent(),
        _snapshot(available=False, fetch_error="AlpacaAPIError: timed out"),
    )
    assert decision.allowed is False
    assert _check(decision, "state_available").passed is False
    assert "timed out" in _check(decision, "state_available").detail


def test_unreadable_state_cannot_be_overridden():
    decision = _decide(
        _intent(manual_override=True, override_reason="demo"),
        _snapshot(available=False, fetch_error="connection refused"),
    )
    assert decision.allowed is False
    assert decision.override_applied is False


# --- check 2: kill switch -------------------------------------------------


def test_kill_switch_halt_blocks_every_order():
    decision = _decide(
        _intent(),
        _snapshot(halted=True, halt_reasons=["nav drawdown -7.20% breaches -5.00%"]),
    )
    assert decision.allowed is False
    assert _check(decision, "kill_switch").passed is False
    assert "drawdown" in _check(decision, "kill_switch").detail


def test_kill_switch_cannot_be_overridden():
    """The one trade the gate most exists to stop."""
    decision = _decide(
        _intent(manual_override=True, override_reason="I know what I am doing"),
        _snapshot(halted=True, halt_reasons=["3 consecutive stop-losses"]),
    )
    assert decision.allowed is False
    assert decision.override_applied is False
    assert "kill-switch engaged" in _check(decision, "kill_switch").detail


def test_kill_switch_clear_passes():
    decision = _decide(
        _intent(),
        _snapshot(positions=[_shares("AAPL", 100)]),
    )
    assert _check(decision, "kill_switch").passed is True


# --- check 3: coverage — "never naked" ------------------------------------


def test_naked_short_call_is_blocked():
    """D4's exact shape: short calls on a symbol the portfolio does not hold."""
    decision = _decide(
        _intent(symbol=_occ(30, "C", 100.0, root="GME"), qty=500),
        _snapshot(),
    )
    assert decision.allowed is False
    coverage = _check(decision, "coverage")
    assert coverage.passed is False
    assert "NAKED CALL" in coverage.detail
    assert coverage.values["shares_required"] == 50_000
    assert coverage.values["shares_held"] == 0


def test_covered_short_call_passes():
    decision = _decide(
        _intent(symbol=_occ(30, "C"), qty=1),
        _snapshot(positions=[_shares("AAPL", 100, 23_000)]),
    )
    coverage = _check(decision, "coverage")
    assert coverage.passed is True
    assert coverage.values["shares_held"] == 100


def test_partially_covered_short_call_is_blocked():
    """99 shares does not cover one contract; there is no partial coverage."""
    decision = _decide(
        _intent(symbol=_occ(30, "C"), qty=1),
        _snapshot(positions=[_shares("AAPL", 99)]),
    )
    assert _check(decision, "coverage").passed is False


def test_existing_short_calls_consume_the_shares_that_back_them():
    """300 shares back 3 contracts; a 4th is naked even though shares exist."""
    decision = _decide(
        _intent(symbol=_occ(30, "C"), qty=1),
        _snapshot(
            positions=[_shares("AAPL", 300)],
            open_option_positions=[_short_option(_occ(45, "C", 180.0), contracts=3)],
        ),
    )
    coverage = _check(decision, "coverage")
    assert coverage.passed is False
    assert coverage.values["contracts_already_short"] == 3
    assert coverage.values["shares_required"] == 400


def test_buying_to_close_a_call_needs_no_coverage():
    decision = _decide(
        _intent(symbol=_occ(30, "C"), side="buy"),
        _snapshot(),
    )
    assert _check(decision, "coverage").passed is True
    assert _check(decision, "coverage").values["applies"] is False


def test_equity_order_needs_no_coverage():
    decision = _decide(_intent(symbol="AAPL", order_type="market", limit_price=None), _snapshot())
    assert _check(decision, "coverage").values["applies"] is False


# --- check 4: collateral — cash-secured puts ------------------------------


def test_unsecured_short_put_is_blocked():
    decision = _decide(
        _intent(symbol=_occ(30, "P", 300.0), qty=1),
        _snapshot(cash=10_000.0),
    )
    assert decision.allowed is False
    collateral = _check(decision, "collateral")
    assert collateral.passed is False
    assert "UNSECURED PUT" in collateral.detail
    assert collateral.values["collateral_required"] == 30_000.0


def test_cash_secured_short_put_passes():
    decision = _decide(
        _intent(symbol=_occ(30, "P", 150.0), qty=1),
        _snapshot(cash=50_000.0),
    )
    assert _check(decision, "collateral").passed is True


def test_cash_reserve_floor_is_respected():
    """$16,000 cash covers a $15,000 put outright, but not after a 10% reserve."""
    config = StrategyConfig(min_cash_reserve_pct=10.0)
    decision = _decide(
        _intent(symbol=_occ(30, "P", 150.0), qty=1),
        _snapshot(cash=16_000.0, equity=100_000.0),
        config,
    )
    collateral = _check(decision, "collateral")
    assert collateral.passed is False
    assert collateral.values["cash_reserve_floor"] == 10_000.0
    assert collateral.values["cash_available_after_reserve"] == 6_000.0


def test_unknown_cash_blocks_a_short_put():
    decision = _decide(
        _intent(symbol=_occ(30, "P", 150.0)),
        _snapshot(cash=None),
    )
    assert _check(decision, "collateral").passed is False
    assert "cash balance unknown" in _check(decision, "collateral").detail


# --- check 5: concentration ----------------------------------------------


def test_concentration_cap_blocks_an_oversized_cash_secured_put():
    """A short put commits new capital, so it can breach the cap."""
    config = StrategyConfig(max_concentration_pct=25.0)
    decision = _decide(
        _intent(symbol=_occ(30, "P", 300.0), qty=1),
        _snapshot(equity=100_000.0, cash=100_000.0,
                  positions=[_shares("AAPL", 100, 23_000)]),
        config,
    )
    concentration = _check(decision, "concentration")
    assert concentration.passed is False
    assert concentration.severity == "BLOCK"
    assert concentration.values["added_exposure"] == 30_000.0
    assert concentration.values["projected_pct"] == pytest.approx(53.0)


def test_a_covered_call_adds_no_concentration_exposure():
    """The shares are already counted; writing a call commits no new capital.

    Adding the strike notional again double-counts the same holding: $69,750 of
    AAPL is 17.4% of a $400k portfolio and passes, but adding a $25,000 strike
    notional on top would put it at 23.7% and eventually block every legitimate
    covered call on a normally-sized position.
    """
    config = StrategyConfig(max_concentration_pct=25.0)
    decision = _decide(
        _intent(symbol=_occ(30, "C", 250.0), qty=1),
        _snapshot(equity=400_000.0, positions=[_shares("AAPL", 300, 69_750)]),
        config,
    )
    concentration = _check(decision, "concentration")
    assert concentration.passed is True
    assert concentration.values["added_exposure"] == 0.0
    assert concentration.values["projected_pct"] == pytest.approx(17.44)


def test_an_already_overweight_holding_warns_but_does_not_block_an_overlay():
    """Refusing the overlay would leave the position more exposed, not less."""
    config = StrategyConfig(max_concentration_pct=25.0)
    decision = _decide(
        _intent(symbol=_occ(30, "C", 250.0), qty=1),
        _snapshot(equity=100_000.0, positions=[_shares("AAPL", 300, 69_750)]),
        config,
    )
    concentration = _check(decision, "concentration")
    assert concentration.passed is False
    assert concentration.severity == "WARN"
    assert decision.allowed is True
    assert concentration.values["existing_pct"] == pytest.approx(69.75)


def test_concentration_within_the_cap_passes():
    config = StrategyConfig(max_concentration_pct=25.0)
    decision = _decide(
        _intent(symbol=_occ(30, "C", 175.0), qty=1),
        _snapshot(equity=200_000.0, positions=[_shares("AAPL", 100, 20_000)]),
        config,
    )
    assert _check(decision, "concentration").passed is True


def test_concentration_not_evaluated_without_equity_warns_but_does_not_block():
    decision = _decide(
        _intent(symbol=_occ(30, "C"), qty=1),
        _snapshot(equity=None, positions=[_shares("AAPL", 100)]),
        StrategyConfig(),
    )
    concentration = _check(decision, "concentration")
    assert concentration.severity == "WARN"
    assert "not evaluated" in concentration.detail


# --- check 6: contract sanity --------------------------------------------


def test_expired_contract_is_blocked():
    decision = _decide(
        _intent(symbol=_occ(-1, "C")),
        _snapshot(positions=[_shares("AAPL", 100)]),
    )
    assert decision.allowed is False
    assert "expired" in _check(decision, "contract_sanity").detail


def test_contract_expiring_today_is_blocked():
    decision = _decide(
        _intent(symbol=_occ(0, "C")),
        _snapshot(positions=[_shares("AAPL", 100)]),
    )
    assert decision.allowed is False
    assert "expires today" in _check(decision, "contract_sanity").detail


def test_dte_outside_the_config_band_warns_but_does_not_block():
    """The DTE band is an entry preference, not a safety property."""
    config = StrategyConfig(dte_min=7, dte_max=45)
    decision = _decide(
        _intent(symbol=_occ(120, "C")),
        _snapshot(positions=[_shares("AAPL", 100)]),
        config,
    )
    sanity = _check(decision, "contract_sanity")
    assert sanity.passed is False
    assert sanity.severity == "WARN"
    assert decision.allowed is True


# --- check 7: price sanity ----------------------------------------------


def test_market_order_on_an_option_is_blocked():
    decision = _decide(
        _intent(symbol=_occ(30, "C"), order_type="market", limit_price=None),
        _snapshot(positions=[_shares("AAPL", 100)]),
    )
    assert decision.allowed is False
    assert "market order on an option" in _check(decision, "price_sanity").detail


def test_limit_price_far_from_the_quote_is_blocked():
    decision = _decide(
        _intent(symbol=_occ(30, "C"), limit_price=10.0),
        _snapshot(positions=[_shares("AAPL", 100)]),
        quote_price=2.0,
    )
    assert decision.allowed is False
    assert _check(decision, "price_sanity").values["deviation_pct"] == pytest.approx(400.0)


def test_limit_price_near_the_quote_passes():
    decision = _decide(
        _intent(symbol=_occ(30, "C"), limit_price=2.10),
        _snapshot(positions=[_shares("AAPL", 100)]),
        quote_price=2.00,
    )
    assert _check(decision, "price_sanity").passed is True


def test_missing_quote_warns_rather_than_passing_silently():
    decision = _decide(
        _intent(symbol=_occ(30, "C")),
        _snapshot(positions=[_shares("AAPL", 100)]),
        quote_price=None,
    )
    sanity = _check(decision, "price_sanity")
    assert sanity.severity == "WARN"
    assert "not sanity-checked" in sanity.detail
    assert decision.allowed is True


# --- check 8: duplicate --------------------------------------------------


def test_existing_short_position_on_the_same_contract_warns():
    contract = _occ(30, "C")
    decision = _decide(
        _intent(symbol=contract),
        _snapshot(
            positions=[_shares("AAPL", 300)],
            open_option_positions=[_short_option(contract, contracts=1)],
        ),
    )
    duplicate = _check(decision, "duplicate")
    assert duplicate.passed is False
    assert duplicate.severity == "WARN"
    assert duplicate.values["contracts_already_short"] == 1
    assert decision.allowed is True  # scaling in is legitimate


# --- check 9: provenance -------------------------------------------------


def test_order_without_a_run_id_is_blocked():
    decision = _decide(
        _intent(run_id=None),
        _snapshot(positions=[_shares("AAPL", 100)]),
    )
    assert decision.allowed is False
    assert _check(decision, "provenance").passed is False


def test_manual_override_without_a_reason_is_blocked():
    """An override nobody can audit later is the same as no gate."""
    decision = _decide(
        _intent(run_id=None, manual_override=True, override_reason=None),
        _snapshot(positions=[_shares("AAPL", 100)]),
    )
    assert decision.allowed is False
    assert "without override_reason" in _check(decision, "provenance").detail


def test_manual_override_with_a_reason_is_allowed_and_recorded():
    decision = _decide(
        _intent(run_id=None, manual_override=True, override_reason="demo rehearsal"),
        _snapshot(positions=[_shares("AAPL", 100)]),
    )
    assert decision.allowed is True
    assert _check(decision, "provenance").severity == "WARN"


def test_override_clears_ordinary_blocks_and_is_visible_in_the_decision():
    decision = _decide(
        _intent(symbol=_occ(30, "C", 100.0, root="GME"), qty=5,
                run_id=None, manual_override=True, override_reason="hedge unwind"),
        _snapshot(),
    )
    assert decision.allowed is True
    assert decision.override_applied is True
    override = _check(decision, "manual_override")
    assert "coverage" in override.values["overridden"]
    assert override.values["reason"] == "hedge unwind"
    # The block is still recorded — an override hides nothing.
    assert _check(decision, "coverage").passed is False


# --- decision shape -----------------------------------------------------


def test_a_clean_covered_call_is_allowed():
    decision = _decide(
        _intent(symbol=_occ(30, "C", 250.0), qty=1),
        _snapshot(equity=200_000.0, positions=[_shares("AAPL", 100, 23_000)]),
        StrategyConfig(),
        quote_price=2.40,
    )
    assert decision.allowed is True
    assert decision.hard_failures == []
    assert decision.override_applied is False


def test_decision_serializes_with_every_check_and_a_snapshot_hash():
    decision = _decide(_intent(), _snapshot(positions=[_shares("AAPL", 100)]))
    payload = decision.to_dict()
    assert {c["name"] for c in payload["checks"]} >= {
        "state_available", "kill_switch", "contract_sanity", "coverage",
        "collateral", "concentration", "duplicate", "price_sanity", "provenance",
    }
    assert len(payload["snapshot_hash"]) == 16
    assert payload["evaluated_at"].endswith("+00:00")


def test_snapshot_hash_changes_when_state_changes():
    a = _snapshot(positions=[_shares("AAPL", 100)])
    b = _snapshot(positions=[_shares("AAPL", 200)])
    assert a.hash() != b.hash()


def test_every_check_reports_its_numbers_not_just_a_boolean():
    """A rejection nobody can diagnose gets overridden blind."""
    decision = _decide(
        _intent(symbol=_occ(30, "C", 100.0, root="GME"), qty=500),
        _snapshot(),
    )
    coverage = _check(decision, "coverage")
    assert coverage.values["shares_held"] is not None
    assert coverage.values["shares_required"] > 0
    assert coverage.values["contracts_requested"] == 500
