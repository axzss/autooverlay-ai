"""Tests for `_pick_option_contract`, `_tier_bands`, `_occ_expiration`.

Per ROADMAP §5 / docs/BRIEF-BACKEND-V2.md B1: this is the most intricate
function in the backend and had zero coverage. Two sign bugs in it already
reached master and were caught by human diff review, and `_occ_expiration`
raised TypeError on every call (D3) without a single test noticing.

All offline: `get_option_snapshots` is monkeypatched and credentials are faked.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.routes import agent as agent_route


@pytest.fixture
def live_mode(monkeypatch):
    """Force `is_configured()` true so the live branch is exercised.

    conftest.py strips Alpaca credentials for the whole session, which is why
    every live-mode path in this module was previously unreachable from tests.
    """
    monkeypatch.setattr(agent_route, "is_configured", lambda: True)


def _occ(days_out: int, kind: str = "C", strike: float = 175.0) -> str:
    exp = datetime.now(timezone.utc).date() + timedelta(days=days_out)
    return f"AAPL{exp:%y%m%d}{kind}{int(strike * 1000):08d}"


def _snap(
    symbol: str,
    delta: float | None,
    bid: float | None = 1.20,
    ask: float | None = 1.30,
) -> dict:
    raw: dict = {"symbol": symbol, "latestQuote": {}}
    if delta is not None:
        raw["greeks"] = {"delta": delta}
    if bid is not None:
        raw["latestQuote"]["bp"] = bid
    if ask is not None:
        raw["latestQuote"]["ap"] = ask
    return raw


def _serve(monkeypatch, snapshots: list[dict]) -> None:
    monkeypatch.setattr(
        agent_route.AlpacaClient,
        "get_option_snapshots",
        lambda self, symbol: list(snapshots),
    )


BAND = {"delta_min": 0.10, "delta_max": 0.35, "max_dte": 45}


# --- _occ_expiration (D3) -------------------------------------------------


def test_occ_expiration_returns_a_date():
    """Regression for D3: this raised TypeError on every call."""
    assert agent_route._occ_expiration("AAPL240621C00175000") == date(2024, 6, 21)


def test_occ_expiration_raises_value_error_on_garbage():
    with pytest.raises(ValueError):
        agent_route._occ_expiration("NOPE")


# --- _tier_bands ----------------------------------------------------------


def test_tier_bands_reads_explicit_min_max():
    assert agent_route._tier_bands(BAND) == (0.10, 0.35, 45)


def test_tier_bands_reads_delta_band_pair():
    assert agent_route._tier_bands(
        {"delta_band": [0.15, 0.30], "max_dte": 30}
    ) == (0.15, 0.30, 30)


@pytest.mark.parametrize(
    "params",
    [
        {"delta_min": 0.35, "delta_max": 0.10, "max_dte": 45},  # inverted
        {"delta_min": 0.35, "delta_max": 0.35, "max_dte": 45},  # equal
        {"delta_min": 0.10, "delta_max": 0.35, "max_dte": 0},   # no DTE window
        {"delta_min": 0.0, "delta_max": 0.35, "max_dte": 45},   # non-positive
        {},                                                      # nothing at all
        {"delta_min": "x", "delta_max": "y", "max_dte": 45},    # wrong types
    ],
)
def test_tier_bands_rejects_unusable_policy(params):
    assert agent_route._tier_bands(params) == (None, None, None)


# --- _pick_option_contract ------------------------------------------------


def test_returns_none_without_credentials(monkeypatch):
    """Documented gap: the order preview is invisible in mock mode."""
    monkeypatch.setattr(agent_route, "is_configured", lambda: False)
    _serve(monkeypatch, [_snap(_occ(30), 0.22)])
    assert agent_route._pick_option_contract("AAPL", BAND) is None


def test_picks_a_contract_inside_the_band(live_mode, monkeypatch):
    symbol = _occ(30)
    _serve(monkeypatch, [_snap(symbol, 0.22)])
    picked = agent_route._pick_option_contract("AAPL", BAND)
    assert picked is not None
    assert picked["option_symbol"] == symbol
    assert picked["dte"] == 30
    assert picked["limit_price"] == pytest.approx(1.25)  # bid + 0.05


def test_negative_put_delta_is_selected_via_absolute_value(live_mode, monkeypatch):
    """Regression for the abs-delta sign bug: short put deltas are negative."""
    symbol = _occ(30, "P", 150.0)
    _serve(monkeypatch, [_snap(symbol, -0.22)])
    picked = agent_route._pick_option_contract("AAPL", BAND)
    assert picked is not None
    assert picked["option_symbol"] == symbol
    assert picked["delta"] == -0.22


def test_sorting_prefers_the_candidate_nearest_the_band_centre(live_mode, monkeypatch):
    """Band centre is 0.225; the -0.23 put is nearest even though it is a put."""
    near = _occ(30, "P", 150.0)
    far = _occ(30, "C", 200.0)
    _serve(monkeypatch, [_snap(far, 0.11), _snap(near, -0.23)])
    picked = agent_route._pick_option_contract("AAPL", BAND)
    assert picked is not None
    assert picked["option_symbol"] == near


def test_ties_on_delta_break_toward_the_shorter_dte(live_mode, monkeypatch):
    short_dte = _occ(10)
    long_dte = _occ(40, "C", 180.0)
    _serve(monkeypatch, [_snap(long_dte, 0.225), _snap(short_dte, 0.225)])
    picked = agent_route._pick_option_contract("AAPL", BAND)
    assert picked is not None
    assert picked["option_symbol"] == short_dte


@pytest.mark.parametrize("days_out", [0, 46, -5])
def test_contracts_outside_the_dte_window_are_excluded(live_mode, monkeypatch, days_out):
    """dte == 0 is rejected too: an option expiring today cannot be overlaid."""
    _serve(monkeypatch, [_snap(_occ(days_out), 0.22)])
    assert agent_route._pick_option_contract("AAPL", BAND) is None


@pytest.mark.parametrize("delta", [0.05, 0.60, -0.60])
def test_contracts_outside_the_delta_band_are_excluded(live_mode, monkeypatch, delta):
    _serve(monkeypatch, [_snap(_occ(30), delta)])
    assert agent_route._pick_option_contract("AAPL", BAND) is None


def test_missing_delta_is_skipped_not_treated_as_zero(live_mode, monkeypatch):
    """A None delta must not pass the band as if it were 0.0."""
    _serve(monkeypatch, [_snap(_occ(30), None)])
    assert agent_route._pick_option_contract("AAPL", BAND) is None


def test_contract_with_no_bid_and_no_ask_is_skipped(live_mode, monkeypatch):
    _serve(monkeypatch, [_snap(_occ(30), 0.22, bid=None, ask=None)])
    assert agent_route._pick_option_contract("AAPL", BAND) is None


def test_ask_only_contract_is_usable(live_mode, monkeypatch):
    _serve(monkeypatch, [_snap(_occ(30), 0.22, bid=None, ask=2.00)])
    picked = agent_route._pick_option_contract("AAPL", BAND)
    assert picked is not None
    assert picked["bid"] is None
    assert picked["limit_price"] == pytest.approx(2.05)


def test_malformed_occ_symbols_are_skipped_not_raised(live_mode, monkeypatch):
    good = _occ(30)
    _serve(monkeypatch, [_snap("GARBAGE", 0.22), _snap(good, 0.22)])
    picked = agent_route._pick_option_contract("AAPL", BAND)
    assert picked is not None
    assert picked["option_symbol"] == good


def test_other_underlyings_in_the_payload_are_ignored(live_mode, monkeypatch):
    """A prefix match would let AAPLW (adjusted) contracts through; the adapter
    compares the parsed OCC root instead."""
    exp = datetime.now(timezone.utc).date() + timedelta(days=30)
    foreign = f"MSFT{exp:%y%m%d}C00175000"
    _serve(monkeypatch, [_snap(foreign, 0.22)])
    assert agent_route._pick_option_contract("AAPL", BAND) is None


def test_broker_failure_degrades_to_none(live_mode, monkeypatch):
    def boom(self, symbol):
        raise agent_route.AlpacaAPIError("Alpaca data API error 503")

    monkeypatch.setattr(agent_route.AlpacaClient, "get_option_snapshots", boom)
    assert agent_route._pick_option_contract("AAPL", BAND) is None


def test_no_symbol_returns_none(live_mode, monkeypatch):
    _serve(monkeypatch, [_snap(_occ(30), 0.22)])
    assert agent_route._pick_option_contract(None, BAND) is None


# --- _order_intents end to end -------------------------------------------


def test_order_intents_resolves_a_real_contract(live_mode, monkeypatch):
    """The D3b failure: this path returned HTTP 500 via _occ_expiration."""
    symbol = _occ(30)
    _serve(monkeypatch, [_snap(symbol, 0.22)])
    intents = agent_route._order_intents([{
        "action": "INITIATE",
        "symbol": "AAPL",
        "params": {**BAND, "strategy_allowed": ["COVERED_CALL"], "size": 1},
    }])
    assert len(intents) == 1
    intent = intents[0]
    assert intent["option_symbol"] == symbol
    assert intent["type"] == "limit"
    assert intent["limit_price"] == pytest.approx(1.25)
    assert intent["requires_approval"] is True
    assert intent["submitted"] is False


def test_order_intents_falls_back_to_market_when_no_contract_resolves(live_mode, monkeypatch):
    _serve(monkeypatch, [])
    intents = agent_route._order_intents([{
        "action": "INITIATE",
        "symbol": "AAPL",
        "params": {**BAND, "strategy_allowed": ["COVERED_CALL"], "size": 1},
    }])
    assert len(intents) == 1
    assert intents[0]["option_symbol"] is None
    assert intents[0]["type"] == "market"


def test_order_intents_ignores_non_initiate_directives(live_mode, monkeypatch):
    _serve(monkeypatch, [_snap(_occ(30), 0.22)])
    assert agent_route._order_intents([
        {"action": "HOLD", "symbol": "AAPL", "params": {}},
        {"action": "MONITOR", "symbol": "AAPL", "params": {}},
    ]) == []
