"""Tests for the execution gate's kill-switch drawdown detection.

Covers ``backend/app/risk/state._kill_switch_state`` and ``_peak_marks``.

Why this file exists: the gate previously derived its high-water mark from
``max(account["equity"], account["last_equity"])`` — a two-day window. A book
down 72% from a peak set weeks earlier reported ``halted=False`` because
yesterday's close was also low. The verdict depended on which calendar day the
peak happened to fall on, not on the drawdown:

    equity 55000, last_equity 55100   -> halted=False, reasons=[]
    equity 55000, last_equity 200000  -> halted=True

Same book, opposite answer. These tests pin the fix: the mark comes from the
persistent PeakStore, keyed per account.

No network. The autouse ``isolated_peak_store`` fixture in conftest gives each
test its own store file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.config import StrategyConfig  # noqa: E402
from backend.app.risk.state import _kill_switch_state, _peak_marks  # noqa: E402


@pytest.fixture
def config() -> StrategyConfig:
    return StrategyConfig()


def _account(equity: float, last_equity: float, account_id: str = "T") -> dict:
    return {
        "account_id": account_id,
        "equity": str(equity),
        "last_equity": str(last_equity),
    }


# --------------------------------------------------------------------------- #
# The two-day-window regression                                               #
# --------------------------------------------------------------------------- #

def test_a_slow_bleed_halts_even_when_yesterday_was_also_low(config):
    """The exact case the old max(equity, last_equity) missed.

    Four gate calls walking one account 200k -> 55k. Under the old logic only
    cycle 2 halted (because last_equity happened to be the peak); cycles 3 and 4
    reported healthy despite -40% and -72.5%.
    """
    verdicts = []
    for equity, last_equity in [(200_000, 199_800), (190_000, 200_000),
                                (120_000, 121_000), (55_000, 55_100)]:
        halted, reasons = _kill_switch_state(
            [], [], 0.0, _account(equity, last_equity, "BLEED"), config
        )
        verdicts.append((halted, reasons))

    assert verdicts[0][0] is False, "first observation seeds the mark, cannot be a drawdown"
    assert all(v[0] is True for v in verdicts[1:]), \
        "a declining book must stay halted once the peak is known"
    assert any("-72.50%" in r for r in verdicts[3][1])


def test_the_verdict_does_not_depend_on_which_day_the_peak_fell_on(config):
    """Two accounts at identical current equity, differing only in last_equity.

    Both have seen 200k. Both are now at 55k. They must agree.
    """
    for account_id, last_equity in (("A", 200_000), ("B", 56_000)):
        _kill_switch_state([], [], 0.0, _account(200_000, 199_000, account_id), config)

    halted_a, _ = _kill_switch_state([], [], 0.0, _account(55_000, 200_000, "A"), config)
    halted_b, _ = _kill_switch_state([], [], 0.0, _account(55_000, 56_000, "B"), config)
    assert halted_a is halted_b is True


def test_a_healthy_flat_book_does_not_halt(config):
    """A control that cries wolf on a healthy book gets switched off."""
    halted, reasons = _kill_switch_state(
        [], [], 0.0, _account(100_000, 99_900, "HEALTHY"), config
    )
    assert halted is False
    assert reasons == []


def test_recovery_above_the_peak_clears_the_halt(config):
    """Drawdown is measured against the mark, so a new high is not a drawdown."""
    _kill_switch_state([], [], 0.0, _account(100_000, 99_000, "REC"), config)
    halted_down, _ = _kill_switch_state([], [], 0.0, _account(80_000, 100_000, "REC"), config)
    halted_up, reasons_up = _kill_switch_state(
        [], [], 0.0, _account(150_000, 80_000, "REC"), config
    )
    assert halted_down is True
    assert halted_up is False
    assert reasons_up == []


# --------------------------------------------------------------------------- #
# Account isolation                                                            #
# --------------------------------------------------------------------------- #

def test_accounts_do_not_share_a_high_water_mark(config):
    """A large account's peak must not halt a small one."""
    _kill_switch_state([], [], 0.0, _account(500_000, 499_000, "BIG"), config)
    halted, reasons = _kill_switch_state(
        [], [], 0.0, _account(50_000, 49_900, "SMALL"), config
    )
    assert halted is False, f"cross-account contamination: {reasons}"


def test_a_missing_account_id_falls_back_to_the_default_key(config):
    halted, _ = _kill_switch_state(
        [], [], 0.0, {"equity": "100000", "last_equity": "99000"}, config
    )
    assert halted is False


# --------------------------------------------------------------------------- #
# Fail-closed behaviour                                                        #
# --------------------------------------------------------------------------- #

def test_an_unevaluable_kill_switch_reports_halted(config, monkeypatch):
    """"The kill-switch is unreadable" must never read as "the kill-switch is clear"."""
    import backend.app.risk.state as state_mod

    def boom(*_args, **_kwargs):
        raise RuntimeError("state store on fire")

    monkeypatch.setattr(state_mod, "_overlay_collateral_for", boom)
    halted, reasons = _kill_switch_state([], [], 0.0, _account(100_000, 99_000), config)
    assert halted is True
    assert any("could not be evaluated" in r for r in reasons)


def test_peak_marks_degrades_to_the_two_day_window_when_the_store_is_gone(monkeypatch):
    """With no store the gate still answers, and says the mark is untracked."""
    import builtins

    real_import = builtins.__import__

    def no_state(name, *args, **kwargs):
        if name == "agent.state" or name.startswith("agent.state."):
            raise ImportError("simulated: state package unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_state)
    peak, overlay, source = _peak_marks(55_000.0, 200_000.0, 0.0)
    assert peak == 200_000.0
    assert overlay is None
    assert source == "absent", "an untracked mark must be labelled, not presented as tracked"


def test_provenance_is_surfaced_alongside_a_breach(config):
    """A halt carries its notes so a NAV fallback is visible in the reasons.

    The note only exists when there are positions to classify: with an empty
    book ``evaluate_kill_switch`` has nothing to say about the basis. Here the
    book holds equities but no short options, so the overlay basis is
    unavailable and the drawdown falls back to NAV — exactly the case that must
    not be silent.
    """
    long_equity = [{"symbol": "AAPL", "qty": 100, "market_value": 20_000.0}]
    _kill_switch_state(long_equity, [], 0.0, _account(200_000, 199_000, "PROV"), config)
    halted, reasons = _kill_switch_state(
        long_equity, [], 0.0, _account(100_000, 101_000, "PROV"), config
    )
    assert halted is True
    assert any(r.startswith("note:") for r in reasons), \
        f"expected provenance notes in the halt reasons, got {reasons}"
    assert any("full NAV" in r for r in reasons)



def test_a_clean_verdict_is_not_padded_with_notes(config):
    """Notes ride along with breaches; they do not manufacture halt reasons."""
    halted, reasons = _kill_switch_state(
        [], [], 0.0, _account(100_000, 99_900, "CLEAN"), config
    )
    assert halted is False
    assert reasons == []


# --------------------------------------------------------------------------- #
# Overlay basis                                                                #
# --------------------------------------------------------------------------- #

def test_overlay_collateral_is_observed_from_short_options(config):
    """The overlay mark is now fed, where before it was always missing.

    ``overlay_peak_equity`` appeared only in the agent layer's own tests: the
    gate never supplied it, so the overlay basis was unreachable in production
    and every evaluation silently fell back to NAV.
    """
    short_call = {
        "symbol": "AAPL251219C00250000",
        "qty": -2,
        "market_value": -1_200.0,
        "asset_class": "us_option",
    }
    _, _, source = _peak_marks(100_000.0, 99_000.0, 50_000.0, account_id="OV")
    assert source in ("seeded", "store")

    halted, _ = _kill_switch_state([], [short_call], 0.0, _account(100_000, 99_000, "OV2"), config)
    assert halted is False
