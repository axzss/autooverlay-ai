"""Options adapter tests, driven by a payload captured from the live Alpaca API.

``fixtures/options_snapshots_aapl.json`` is a real response from
``GET /v1beta1/options/snapshots/AAPL?feed=indicative`` (public market data, no
account identifiers), trimmed to 8 contracts: 4 calls, 2 puts, and 2 contracts
that carry no greeks at all.

Hand-written fixtures are what let D1 and D2 ship green — they only prove the
parser agrees with the author's assumptions. Every shape assertion here is
anchored to the captured file.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from backend.app.adapters.options import (
    iter_snapshot_entries,
    normalize_snapshot,
    normalize_snapshots,
    parse_occ,
)

FIXTURE = Path(__file__).parent / "fixtures" / "options_snapshots_aapl.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(FIXTURE.read_text())


# --- OCC parsing ----------------------------------------------------------


def test_parse_occ_call():
    occ = parse_occ("AAPL240621C00175000")
    assert occ.underlying == "AAPL"
    assert occ.expiration == date(2024, 6, 21)
    assert occ.option_type == "call"
    assert occ.strike == 175.0


def test_parse_occ_put_and_fractional_strike():
    occ = parse_occ("AAPL260902P00327500")
    assert occ.option_type == "put"
    assert occ.strike == 327.5


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "AAPL",
        "AAPL240621X00175000",       # not C or P
        "TOOLONGROOT240621C00175000",
        "AAPL24062C00175000",        # short date
        "AAPL241332C00175000",       # month 13 / day 32
    ],
)
def test_parse_occ_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_occ(bad)


# --- payload shape --------------------------------------------------------


def test_snapshots_container_is_a_dict_keyed_by_option_symbol(payload):
    """The shape D1 got wrong: a dict, not a list."""
    assert isinstance(payload["snapshots"], dict)
    entries = iter_snapshot_entries(payload)
    assert len(entries) == len(payload["snapshots"])
    for symbol, raw in entries:
        assert symbol.startswith("AAPL")
        assert isinstance(raw, dict)


def test_iter_snapshot_entries_also_accepts_list_form():
    entries = iter_snapshot_entries([
        {"symbol": "AAPL301231C00175000", "greeks": {"delta": 0.2}},
        {"greeks": {"delta": 0.2}},   # no symbol — unusable, skipped
        "garbage",
    ])
    assert entries == [
        ("AAPL301231C00175000", {"symbol": "AAPL301231C00175000", "greeks": {"delta": 0.2}})
    ]


def test_normalize_snapshots_parses_the_whole_captured_chain(payload):
    quotes = normalize_snapshots(payload)
    assert len(quotes) == len(payload["snapshots"])
    assert {q.option_type for q in quotes} == {"call", "put"}
    assert all(q.underlying == "AAPL" for q in quotes)
    # Strike and expiry come from the OCC symbol, which is always present —
    # the payload has no `details` block to read them from.
    assert all(q.strike > 0 for q in quotes)
    assert all(isinstance(q.expiration, date) for q in quotes)


def test_camelcase_quote_fields_are_read(payload):
    raw = payload["snapshots"]["AAPL260831C00330000"]
    quote = normalize_snapshot("AAPL260831C00330000", raw)
    assert quote is not None
    # latestQuote.bp / .ap — the field names D2 missed.
    assert quote.bid == raw["latestQuote"]["bp"]
    assert quote.ask == raw["latestQuote"]["ap"]
    assert quote.mid == pytest.approx((quote.bid + quote.ask) / 2)
    assert quote.last == raw["latestTrade"]["p"]
    assert quote.implied_volatility == raw["impliedVolatility"]
    assert quote.delta == raw["greeks"]["delta"]
    assert quote.theta == raw["greeks"]["theta"]
    assert quote.as_of is not None and quote.as_of.tzinfo is not None


def test_snake_case_spellings_are_also_accepted():
    quote = normalize_snapshot("AAPL301231C00175000", {
        "latest_quote": {"bid_price": 1.20, "ask_price": 1.30},
        "implied_volatility": 0.24,
        "greeks": {"delta": 0.22},
        "open_interest": 8700,
    })
    assert quote is not None
    assert (quote.bid, quote.ask, quote.mid) == (1.20, 1.30, 1.25)
    assert quote.implied_volatility == 0.24
    assert quote.open_interest == 8700


# --- the None discipline --------------------------------------------------


def test_missing_greeks_yield_none_not_zero(payload):
    """A contract with no greeks block must not report delta 0.0.

    This is D2's mechanism: a defaulted 0.0 delta passes any delta band
    trivially, so an unknown contract would be selected as if it were the
    safest one available.
    """
    raw = payload["snapshots"]["AAPL260902C00395000"]
    assert "greeks" not in raw
    quote = normalize_snapshot("AAPL260902C00395000", raw)
    assert quote is not None
    assert quote.delta is None
    assert quote.gamma is None
    assert quote.theta is None
    assert quote.vega is None
    assert quote.implied_volatility is None


def test_zero_bid_is_treated_as_absent_not_as_a_price(payload):
    """`bp: 0` in the captured payload means "no bid", not "free"."""
    raw = payload["snapshots"]["AAPL260902C00395000"]
    assert raw["latestQuote"]["bp"] == 0
    quote = normalize_snapshot("AAPL260902C00395000", raw)
    assert quote is not None
    assert quote.bid is None
    assert quote.ask == 1.05
    # One-sided book: no mid is claimed, but `price` still falls back sensibly.
    assert quote.mid is None
    assert quote.price is None  # no trade in this payload either


def test_open_interest_is_absent_from_the_indicative_feed(payload):
    """Verified against the live API: the indicative feed carries no OI.

    Recorded here so a liquidity filter is never written against a field that
    does not arrive. (The OPRA feed, which would carry it, returns HTTP 403
    "OPRA agreement is not signed" on this account.)
    """
    assert all(
        "openInterest" not in raw and "open_interest" not in raw
        for raw in payload["snapshots"].values()
    )
    assert all(q.open_interest is None for q in normalize_snapshots(payload))


def test_nan_and_infinity_are_rejected():
    quote = normalize_snapshot("AAPL301231C00175000", {
        "greeks": {"delta": float("nan"), "vega": float("inf")},
        "latestQuote": {"bp": float("-inf"), "ap": 1.3},
    })
    assert quote is not None
    assert quote.delta is None
    assert quote.vega is None
    assert quote.bid is None
    assert quote.ask == 1.3


# --- failure handling -----------------------------------------------------


def test_malformed_symbol_is_skipped_not_raised():
    assert normalize_snapshot("NOT-AN-OCC-SYMBOL", {"greeks": {"delta": 0.2}}) is None


def test_non_mapping_payload_is_skipped():
    assert normalize_snapshot("AAPL301231C00175000", ["unexpected"]) is None
    assert normalize_snapshot("AAPL301231C00175000", None) is None


def test_one_bad_contract_does_not_abort_the_chain():
    quotes = normalize_snapshots({"snapshots": {
        "AAPL301231C00175000": {"greeks": {"delta": 0.2}},
        "BROKEN": {"greeks": {"delta": 0.2}},
        "AAPL301231C00180000": {"greeks": {"delta": 0.1}},
    }})
    assert [q.option_symbol for q in quotes] == [
        "AAPL301231C00175000",
        "AAPL301231C00180000",
    ]


def test_nanosecond_timestamps_parse(payload):
    """Alpaca sends nanosecond precision; fromisoformat accepts microseconds."""
    raw = payload["snapshots"]["AAPL260831C00330000"]
    assert len(raw["latestQuote"]["t"].split(".")[1]) > 7  # more than micros
    quote = normalize_snapshot("AAPL260831C00330000", raw)
    assert quote is not None and quote.as_of is not None


def test_days_to_expiry_uses_the_occ_date():
    quote = normalize_snapshot("AAPL301231C00175000", {"greeks": {"delta": 0.2}})
    assert quote is not None
    assert quote.days_to_expiry(date(2030, 12, 1)) == 30
    assert quote.days_to_expiry(date(2031, 1, 1)) == -1
