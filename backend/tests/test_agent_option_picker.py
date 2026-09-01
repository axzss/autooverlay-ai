"""Unit tests for backend option-contract selection in ``routes/agent.py``.

Covers ``_pick_option_contract`` plus its helpers ``_tier_bands``,
``_occ_expiration`` and ``_safe_float``, which had zero coverage despite two
sign-handling bugs reaching master (both caught by human diff review, not tests):

* **BUG A** (fixed in a8a4047) — the delta-band filter compared the *raw* delta
  against a positive band. Put deltas are negative, so ``0.10 <= -0.15 <= 0.25``
  was always False and no put contract was ever selectable. Fix: ``abs(delta)``.
* **BUG B** (fixed in d052aa2) — the sort key compared the *raw* delta against
  the band centre. A put at -0.15 in band 0.10-0.25 (centre 0.175) scored
  ``abs(-0.15 - 0.175) = 0.325`` instead of ``0.025``, so puts were penalised
  and lost to strictly worse-fitting calls. Fix: ``abs(abs(delta) - centre)``.

The classes below tagged ``Regression`` fail if either fix is reverted.

No network: ``is_configured`` and ``AlpacaClient`` are monkeypatched on the
route module for every test that reaches the fetch. ``backend/tests/conftest.py``
strips ``ALPACA_*`` from the environment, so the real client can never be
constructed with usable credentials here.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.app.alpaca_client import AlpacaAPIError
from backend.app.routes import agent as A

# Tier bands as agent/council/handoff.py defines them, so the fixtures below
# exercise the same numbers production actually passes in.
LOW_BAND = {"delta_min": 0.15, "delta_max": 0.30, "max_dte": 45}
MID_BAND = {"delta_min": 0.10, "delta_max": 0.25, "max_dte": 45}
HIGH_BAND = {"delta_min": 0.05, "delta_max": 0.15, "max_dte": 30}


def occ(
    expiration: date,
    *,
    root: str = "AAPL",
    option_type: str = "C",
    strike: float = 175.0,
) -> str:
    """Build a real OCC symbol: ROOT + YYMMDD + C/P + strike*1000 zero-padded to 8.

    ``occ(date(2026, 8, 31), strike=215.0)`` -> ``AAPL260831C00215000``.
    """
    return (
        f"{root}{expiration.strftime('%y%m%d')}{option_type}{int(round(strike * 1000)):08d}"
    )


def snapshot(
    option_symbol: str,
    *,
    delta: object = 0.20,
    bid: object = 1.20,
    ask: object = 1.30,
    include_greeks: bool = True,
    include_quote: bool = True,
) -> dict:
    """One entry in the list ``AlpacaClient.get_option_snapshots`` returns.

    Shape matches the broker: greeks at the top level, prices nested under
    ``latestQuote`` as ``bp``/``ap``, and ``symbol`` injected by the client.
    """
    snap: dict = {"symbol": option_symbol}
    if include_greeks:
        snap["greeks"] = {"delta": delta}
    if include_quote:
        quote: dict = {}
        if bid is not None:
            quote["bp"] = bid
        if ask is not None:
            quote["ap"] = ask
        snap["latestQuote"] = quote
    return snap


@pytest.fixture
def pick(monkeypatch):
    """Return ``pick(snapshots, params=..., symbol=...)`` with the fetch stubbed.

    Exposes ``pick.calls`` so a test can assert the broker was (or was not) hit.
    """
    monkeypatch.setattr(A, "is_configured", lambda: True)
    calls: list[str] = []

    def _pick(snapshots, params=None, symbol="AAPL"):
        class _StubClient:
            def get_option_snapshots(self, underlying):
                calls.append(underlying)
                if isinstance(snapshots, BaseException):
                    raise snapshots
                return snapshots

        monkeypatch.setattr(A, "AlpacaClient", _StubClient)
        return A._pick_option_contract(symbol, params or dict(MID_BAND))

    _pick.calls = calls
    return _pick


@pytest.fixture
def in_window() -> date:
    """An expiration comfortably inside every tier's max_dte."""
    return date.today() + timedelta(days=21)


class TestBugARegressionPutDeltaSign:
    """BUG A: negative put deltas must pass a positive delta band."""

    def test_put_with_negative_delta_inside_band_is_selected(self, pick, in_window):
        # |−0.15| = 0.15, inside the mid band 0.10-0.25. The pre-a8a4047 code
        # evaluated `0.10 <= -0.15 <= 0.25` -> False and returned None.
        put = occ(in_window, option_type="P", strike=170.0)

        result = pick([snapshot(put, delta=-0.15)])

        assert result is not None, (
            "BUG A regression: a put with delta -0.15 inside band 0.10-0.25 was "
            "rejected. The band filter is comparing raw delta, not abs(delta)."
        )
        assert result["option_symbol"] == put
        assert result["delta"] == -0.15, "the raw signed delta must be reported through"

    @pytest.mark.parametrize("delta", [-0.10, -0.15, -0.20, -0.25])
    def test_puts_across_the_whole_band_are_selectable(self, pick, in_window, delta):
        put = occ(in_window, option_type="P", strike=170.0)

        assert pick([snapshot(put, delta=delta)]) is not None

    def test_put_outside_band_is_still_rejected(self, pick, in_window):
        # abs(delta) must be *inside* the band; abs() is not a licence to accept
        # everything. 0.45 is outside 0.10-0.25.
        put = occ(in_window, option_type="P", strike=170.0)

        assert pick([snapshot(put, delta=-0.45)]) is None


class TestBugBRegressionSortKeySign:
    """BUG B: ranking must use abs(delta) distance from the band centre."""

    def test_put_closer_to_band_centre_beats_a_worse_fitting_call(self, pick, in_window):
        # Mid band 0.10-0.25 -> centre 0.175.
        #   put  -0.15: correct |0.15 - 0.175| = 0.025  <- best fit, must win
        #   call  0.24: correct |0.24 - 0.175| = 0.065
        # Under the pre-d052aa2 raw-delta key the put scored
        #   abs(-0.15 - 0.175) = 0.325, losing to the call's 0.065.
        call = occ(in_window, option_type="C", strike=175.0)
        put = occ(in_window, option_type="P", strike=170.0)

        result = pick([snapshot(call, delta=0.24), snapshot(put, delta=-0.15)])

        assert result is not None
        assert result["option_symbol"] == put, (
            "BUG B regression: the sort key is penalising the put's negative "
            f"delta. Picked {result['option_symbol']} (delta {result['delta']}); "
            "the put at -0.15 is nearer the 0.175 band centre than the call at 0.24."
        )

    def test_ordering_is_independent_of_input_order(self, pick, in_window):
        call = occ(in_window, option_type="C", strike=175.0)
        put = occ(in_window, option_type="P", strike=170.0)
        snaps = [snapshot(put, delta=-0.15), snapshot(call, delta=0.24)]

        assert pick(snaps)["option_symbol"] == put
        assert pick(list(reversed(snaps)))["option_symbol"] == put

    def test_best_fitting_call_still_wins_against_a_worse_put(self, pick, in_window):
        # Symmetry check: abs() must not hand puts an advantage either.
        #   call 0.18 -> 0.005 (best)   put -0.11 -> 0.065
        call = occ(in_window, option_type="C", strike=175.0)
        put = occ(in_window, option_type="P", strike=170.0)

        result = pick([snapshot(put, delta=-0.11), snapshot(call, delta=0.18)])

        assert result["option_symbol"] == call

    def test_equal_delta_fit_breaks_the_tie_on_shorter_dte(self, pick):
        # Both at the centre; the secondary sort key is dte ascending.
        near = occ(date.today() + timedelta(days=7), strike=175.0)
        far = occ(date.today() + timedelta(days=35), strike=180.0)

        result = pick([snapshot(far, delta=0.175), snapshot(near, delta=0.175)])

        assert result["option_symbol"] == near
        assert result["dte"] == 7

    def test_put_and_call_at_mirrored_deltas_tie_then_sort_on_dte(self, pick):
        # |0.20| == |-0.20|: neither sign may be preferred, so dte decides.
        call_far = occ(date.today() + timedelta(days=30), option_type="C", strike=175.0)
        put_near = occ(date.today() + timedelta(days=10), option_type="P", strike=170.0)

        result = pick([snapshot(call_far, delta=0.20), snapshot(put_near, delta=-0.20)])

        assert result["option_symbol"] == put_near


class TestDteWindowing:
    """``0 < dte <= max_dte`` — expiring-today and beyond-window are both out."""

    @pytest.mark.parametrize("days", [1, 2, 21, 44, 45])
    def test_dte_inside_window_is_accepted(self, pick, days):
        result = pick([snapshot(occ(date.today() + timedelta(days=days)))])

        assert result is not None
        assert result["dte"] == days

    def test_dte_equal_to_max_dte_is_accepted(self, pick):
        # Upper bound is inclusive: max_dte=45 admits dte==45.
        result = pick([snapshot(occ(date.today() + timedelta(days=45)))])

        assert result is not None and result["dte"] == 45

    def test_dte_one_past_max_dte_is_excluded(self, pick):
        assert pick([snapshot(occ(date.today() + timedelta(days=46)))]) is None

    def test_dte_zero_expiring_today_is_rejected(self, pick):
        # 0DTE carries pin/assignment risk this system does not model.
        assert pick([snapshot(occ(date.today()))]) is None

    def test_already_expired_contract_is_rejected(self, pick):
        assert pick([snapshot(occ(date.today() - timedelta(days=1)))]) is None

    def test_high_tier_uses_its_tighter_30_day_window(self, pick):
        inside = occ(date.today() + timedelta(days=30))
        outside = occ(date.today() + timedelta(days=31))

        assert pick([snapshot(inside, delta=0.10)], dict(HIGH_BAND)) is not None
        assert pick([snapshot(outside, delta=0.10)], dict(HIGH_BAND)) is None

    def test_only_the_in_window_contract_survives_a_mixed_chain(self, pick):
        good = occ(date.today() + timedelta(days=20), strike=175.0)
        snaps = [
            snapshot(occ(date.today(), strike=170.0), delta=0.175),
            snapshot(occ(date.today() + timedelta(days=200), strike=180.0), delta=0.175),
            snapshot(good, delta=0.175),
        ]

        assert pick(snaps)["option_symbol"] == good


class TestDegenerateSnapshotsAreSkippedNotRaised:
    """Missing or junk fields must drop the contract, never propagate."""

    def test_snapshot_without_greeks_key_is_skipped(self, pick, in_window):
        assert pick([snapshot(occ(in_window), include_greeks=False)]) is None

    def test_delta_none_is_skipped(self, pick, in_window):
        # Critically it must not be coerced to 0.0, which would sit inside no
        # band here but would trivially pass any band containing zero.
        assert pick([snapshot(occ(in_window), delta=None)]) is None

    def test_non_numeric_delta_string_is_skipped(self, pick, in_window):
        assert pick([snapshot(occ(in_window), delta="not-a-number")]) is None

    def test_both_bid_and_ask_none_is_skipped(self, pick, in_window):
        assert pick([snapshot(occ(in_window), bid=None, ask=None)]) is None

    def test_snapshot_with_no_quote_block_is_skipped(self, pick, in_window):
        assert pick([snapshot(occ(in_window), include_quote=False)]) is None

    def test_numeric_strings_in_price_fields_are_coerced(self, pick, in_window):
        # Some feeds stringify prices; a parseable string must still work.
        result = pick([snapshot(occ(in_window), bid="1.20", ask="1.30")])

        assert result is not None
        assert result["bid"] == 1.20 and result["ask"] == 1.30

    def test_non_numeric_price_string_is_dropped_but_the_other_side_is_kept(
        self, pick, in_window
    ):
        result = pick([snapshot(occ(in_window), bid="1.00", ask="wide")])

        assert result is not None
        assert result["bid"] == 1.00
        assert result["ask"] is None

    def test_empty_snapshot_list_returns_none(self, pick):
        assert pick([]) is None

    def test_a_single_bad_contract_does_not_discard_the_good_ones(self, pick, in_window):
        good = occ(in_window, strike=175.0)
        snaps = [
            snapshot("TOTAL-GARBAGE", delta=0.175),
            snapshot(occ(in_window, strike=170.0), delta=None),
            snapshot(occ(in_window, strike=165.0), include_greeks=False),
            snapshot(good, delta=0.175),
        ]

        assert pick(snaps)["option_symbol"] == good

    @pytest.mark.parametrize(
        "boom",
        [AlpacaAPIError("upstream 500"), ValueError("bad json"), TypeError("bad shape")],
    )
    def test_broker_errors_degrade_to_none(self, pick, boom):
        assert pick(boom) is None

    def test_snapshot_for_a_different_underlying_is_ignored(self, pick, in_window):
        # Guards against a chain request leaking another symbol's contracts.
        assert pick([snapshot(occ(in_window, root="MSFT"))], symbol="AAPL") is None


class TestMalformedOccSymbols:
    """A bad OCC symbol skips that contract; it never raises."""

    @pytest.mark.parametrize(
        "bad_symbol",
        [
            "AAPLNOTANOCCSYMBOL",
            "AAPL",
            "",
            "AAPL2608C00215000",      # 4-digit date
            "AAPL260831X00215000",    # neither C nor P
            "AAPL260831C0021500",     # 7-digit strike
            "AAPL260831C002150000",   # 9-digit strike
            "AAPL261331C00215000",    # month 13
            "AAPL260832C00215000",    # day 32
            "1234260831C00215000",    # numeric root
        ],
    )
    def test_malformed_symbol_is_skipped(self, pick, bad_symbol):
        assert pick([snapshot(bad_symbol, delta=0.175)]) is None

    def test_missing_symbol_field_is_skipped(self, pick):
        assert pick([{"greeks": {"delta": 0.175}, "latestQuote": {"bp": 1.2}}]) is None

    def test_lowercase_symbol_is_still_parsed(self, pick, in_window):
        result = pick([snapshot(occ(in_window).lower(), delta=0.175)])

        assert result is not None
        assert result["option_symbol"] == occ(in_window)


class TestOccExpiration:
    """``_occ_expiration`` — the YYMMDD slice of an OCC symbol."""

    def test_parses_a_valid_symbol(self):
        assert A._occ_expiration("AAPL260831C00215000") == date(2026, 8, 31)

    @pytest.mark.parametrize(
        ("symbol", "expected"),
        [
            ("AAPL260831C00215000", date(2026, 8, 31)),
            ("AAPL301231P00175000", date(2030, 12, 31)),
            ("T260116C00020000", date(2026, 1, 16)),
            ("BRK.B270115C00400000", date(2027, 1, 15)),
        ],
    )
    def test_parses_varied_roots_and_dates(self, symbol, expected):
        assert A._occ_expiration(symbol) == expected

    def test_two_digit_year_is_anchored_to_2000(self):
        assert A._occ_expiration("AAPL260831C00215000").year == 2026

    def test_lowercase_and_embedded_spaces_are_tolerated(self):
        assert A._occ_expiration(" aapl260831c00215000 ".strip()) == date(2026, 8, 31)
        assert A._occ_expiration("AAPL 260831C00215000") == date(2026, 8, 31)

    @pytest.mark.parametrize(
        "garbage",
        ["", "GARBAGE", "AAPL", "AAPL2608C00215000", "AAPL261331C00215000", None, 12345],
    )
    def test_garbage_raises_valueerror_only(self, garbage):
        # The call site catches ValueError specifically, so any *other*
        # exception type escapes as an HTTP 500 (that is exactly how defect D3
        # shipped: a TypeError from datetime.date used as a descriptor).
        with pytest.raises(ValueError):
            A._occ_expiration(garbage)

    @pytest.mark.parametrize(
        "garbage", ["", "GARBAGE", "AAPL2608C00215000", None, 12345]
    )
    def test_garbage_never_raises_typeerror(self, garbage):
        try:
            A._occ_expiration(garbage)
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001 - the point is to name the type
            pytest.fail(
                f"_occ_expiration({garbage!r}) raised {type(exc).__name__}: {exc}. "
                "Only ValueError is caught by _pick_option_contract; anything "
                "else becomes an HTTP 500."
            )


class TestTierBands:
    """``_tier_bands`` — band/DTE extraction and its all-or-nothing contract."""

    def test_low_tier_bands(self):
        assert A._tier_bands(dict(LOW_BAND)) == (0.15, 0.30, 45)

    def test_mid_tier_bands(self):
        assert A._tier_bands(dict(MID_BAND)) == (0.10, 0.25, 45)

    def test_high_tier_bands(self):
        assert A._tier_bands(dict(HIGH_BAND)) == (0.05, 0.15, 30)

    def test_delta_band_list_form_is_accepted(self):
        assert A._tier_bands({"delta_band": [0.10, 0.25], "max_dte": 45}) == (
            0.10,
            0.25,
            45,
        )

    def test_delta_band_list_takes_precedence_over_scalars(self):
        params = {
            "delta_band": [0.05, 0.15],
            "delta_min": 0.10,
            "delta_max": 0.25,
            "max_dte": 30,
        }

        assert A._tier_bands(params) == (0.05, 0.15, 30)

    def test_min_equal_to_max_is_rejected(self):
        # A zero-width band can only ever match an exactly-equal delta; treated
        # as misconfiguration rather than a filter.
        assert A._tier_bands({"delta_min": 0.20, "delta_max": 0.20, "max_dte": 45}) == (
            None,
            None,
            None,
        )

    def test_min_greater_than_max_is_rejected(self):
        assert A._tier_bands({"delta_min": 0.30, "delta_max": 0.20, "max_dte": 45}) == (
            None,
            None,
            None,
        )

    @pytest.mark.parametrize(
        "params",
        [
            {"delta_min": 0.0, "delta_max": 0.25, "max_dte": 45},
            {"delta_min": -0.10, "delta_max": 0.25, "max_dte": 45},
            {"delta_min": 0.10, "delta_max": 0.0, "max_dte": 45},
            {"delta_min": 0.10, "delta_max": -0.25, "max_dte": 45},
            {"delta_min": 0.10, "delta_max": 0.25, "max_dte": 0},
            {"delta_min": 0.10, "delta_max": 0.25, "max_dte": -5},
            {"delta_min": 0.10, "delta_max": 0.25},
            {"max_dte": 45},
            {},
        ],
    )
    def test_degenerate_params_return_all_none(self, params):
        # All-or-nothing: the caller checks `None in (...)`, so a partial tuple
        # would let an unvalidated band through.
        assert A._tier_bands(params) == (None, None, None)

    @pytest.mark.parametrize(
        "params",
        [
            {"delta_band": ["a", "b"], "max_dte": 45},
            {"delta_min": "abc", "delta_max": 0.25, "max_dte": 45},
            {"delta_min": 0.10, "delta_max": None, "max_dte": 45},
            {"delta_min": 0.10, "delta_max": 0.25, "max_dte": "abc"},
            {"delta_min": 0.10, "delta_max": 0.25, "max_dte": None},
        ],
    )
    def test_non_numeric_params_return_all_none_without_raising(self, params):
        assert A._tier_bands(params) == (None, None, None)

    def test_numeric_strings_are_coerced(self):
        assert A._tier_bands(
            {"delta_min": "0.10", "delta_max": "0.25", "max_dte": "45"}
        ) == (0.10, 0.25, 45)

    def test_float_max_dte_is_truncated_to_int(self):
        assert A._tier_bands(
            {"delta_min": 0.10, "delta_max": 0.25, "max_dte": 45.9}
        ) == (0.10, 0.25, 45)

    def test_wrong_length_delta_band_falls_back_to_scalars(self):
        params = {
            "delta_band": [0.10, 0.20, 0.30],
            "delta_min": 0.15,
            "delta_max": 0.30,
            "max_dte": 45,
        }

        assert A._tier_bands(params) == (0.15, 0.30, 45)


class TestSafeFloat:
    """``_safe_float`` — coerce or give up; no exceptions, no silent zeros."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1.5, 1.5),
            (0, 0.0),
            (-0.15, -0.15),
            ("1.5", 1.5),
            ("-0.15", -0.15),
            ("  2.5  ", 2.5),
            (True, 1.0),
            (3, 3.0),
        ],
    )
    def test_coercible_values(self, value, expected):
        assert A._safe_float(value) == expected

    @pytest.mark.parametrize(
        "value",
        [None, "", "abc", "1.2.3", [], {}, object(), float("inf"), float("-inf"), float("nan")],
    )
    def test_uncoercible_and_non_finite_values_return_none(self, value):
        # None rather than 0.0 matters: a defaulted 0.0 delta would slip through
        # any band bracketing zero and a 0.0 price would look like a free option.
        assert A._safe_float(value) is None

    def test_nan_is_rejected_even_though_float_accepts_it(self):
        assert A._safe_float("nan") is None
        assert A._safe_float("inf") is None


class TestLimitPriceDerivation:
    """``limit_price`` = bid + $0.05, falling back to ask when bid is absent."""

    def test_limit_price_is_bid_plus_five_cents(self, pick, in_window):
        result = pick([snapshot(occ(in_window), bid=1.20, ask=1.30)])

        assert result["limit_price"] == 1.25
        assert result["bid"] == 1.20 and result["ask"] == 1.30

    def test_ask_is_used_when_bid_is_absent(self, pick, in_window):
        result = pick([snapshot(occ(in_window), bid=None, ask=2.00)])

        assert result["limit_price"] == 2.05
        assert result["bid"] is None and result["ask"] == 2.00

    def test_bid_is_preferred_over_ask_when_both_present(self, pick, in_window):
        result = pick([snapshot(occ(in_window), bid=0.80, ask=5.00)])

        assert result["limit_price"] == 0.85

    def test_zero_bid_falls_through_to_ask(self, pick, in_window):
        # A 0.00 bid is not a real bid; it must not produce a $0.05 limit.
        result = pick([snapshot(occ(in_window), bid=0.0, ask=2.00)])

        assert result["bid"] is None
        assert result["limit_price"] == 2.05

    def test_limit_price_is_rounded_to_cents(self, pick, in_window):
        result = pick([snapshot(occ(in_window), bid=1.234, ask=1.30)])

        assert result["limit_price"] == 1.28

    def test_flat_five_cent_pad_is_a_large_fraction_of_a_cheap_contract(
        self, pick, in_window
    ):
        # AUDIT (documented, not a failure): the pad is absolute, so its
        # relative size scales inversely with premium — 25% on a $0.20 contract
        # versus 1% on a $5.00 one. See the audit notes in the task report.
        cheap = pick([snapshot(occ(in_window, strike=175.0), bid=0.20, ask=0.30)])
        rich = pick([snapshot(occ(in_window, strike=180.0), bid=5.00, ask=5.10)])

        assert cheap["limit_price"] == 0.25
        assert rich["limit_price"] == 5.05
        assert (cheap["limit_price"] - 0.20) / 0.20 == pytest.approx(0.25)
        assert (rich["limit_price"] - 5.00) / 5.00 == pytest.approx(0.01)


class TestBandBoundaryInclusivity:
    """Both band edges are inclusive — documented here so a change is visible."""

    @pytest.mark.parametrize("delta", [0.10, 0.25])
    def test_call_exactly_on_a_band_edge_is_accepted(self, pick, in_window, delta):
        assert pick([snapshot(occ(in_window), delta=delta)]) is not None

    @pytest.mark.parametrize("delta", [-0.10, -0.25])
    def test_put_exactly_on_a_band_edge_is_accepted(self, pick, in_window, delta):
        put = occ(in_window, option_type="P", strike=170.0)

        assert pick([snapshot(put, delta=delta)]) is not None

    @pytest.mark.parametrize("delta", [0.0999, 0.2501, -0.0999, -0.2501])
    def test_just_outside_either_edge_is_rejected(self, pick, in_window, delta):
        assert pick([snapshot(occ(in_window), delta=delta)]) is None

    def test_an_edge_contract_can_actually_be_returned(self, pick, in_window):
        # Confirms inclusivity is reachable end-to-end, not just past the filter:
        # the only candidate sits on the upper edge and is still selected.
        result = pick([snapshot(occ(in_window), delta=0.25)])

        assert result is not None and result["delta"] == 0.25


class TestShortCircuitsBeforeAnyFetch:
    """Guard clauses must return None without touching the broker."""

    def test_unconfigured_credentials_skip_the_fetch_entirely(self, monkeypatch):
        monkeypatch.setattr(A, "is_configured", lambda: False)
        calls: list[str] = []

        class _NeverCalled:
            def get_option_snapshots(self, underlying):
                calls.append(underlying)
                raise AssertionError(
                    "get_option_snapshots was called despite is_configured() == False"
                )

        monkeypatch.setattr(A, "AlpacaClient", _NeverCalled)

        assert A._pick_option_contract("AAPL", dict(MID_BAND)) is None
        assert calls == [], "no broker call may be attempted when unconfigured"

    @pytest.mark.parametrize("symbol", [None, ""])
    def test_missing_symbol_short_circuits_before_is_configured(
        self, monkeypatch, symbol
    ):
        def _boom():
            raise AssertionError("is_configured() called for an empty symbol")

        monkeypatch.setattr(A, "is_configured", _boom)

        assert A._pick_option_contract(symbol, dict(MID_BAND)) is None

    def test_invalid_bands_short_circuit_before_is_configured(self, monkeypatch):
        # Band validation precedes the credential check, so a misconfigured
        # tier costs nothing.
        def _boom():
            raise AssertionError("is_configured() called with an invalid delta band")

        monkeypatch.setattr(A, "is_configured", _boom)

        assert (
            A._pick_option_contract(
                "AAPL", {"delta_min": 0.30, "delta_max": 0.20, "max_dte": 45}
            )
            is None
        )

    def test_configured_path_does_call_the_fetch_once(self, pick, in_window):
        pick([snapshot(occ(in_window))])

        assert pick.calls == ["AAPL"]


class TestReturnedContractShape:
    """The dict handed to ``_order_intents`` must carry every key it reads."""

    def test_result_contains_the_expected_keys(self, pick, in_window):
        result = pick([snapshot(occ(in_window), delta=0.18, bid=1.20, ask=1.30)])

        assert set(result) == {
            "symbol",
            "option_symbol",
            "delta",
            "dte",
            "limit_price",
            "bid",
            "ask",
        }

    def test_underlying_symbol_is_echoed_not_the_occ_symbol(self, pick, in_window):
        result = pick([snapshot(occ(in_window), delta=0.18)])

        assert result["symbol"] == "AAPL"
        assert result["option_symbol"].startswith("AAPL")
        assert len(result["option_symbol"]) > len("AAPL")

    def test_dte_is_a_positive_int(self, pick):
        result = pick([snapshot(occ(date.today() + timedelta(days=14)))])

        assert isinstance(result["dte"], int) and result["dte"] == 14
