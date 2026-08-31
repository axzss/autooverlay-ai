"""Tests for the persistent kill-switch high-water-mark store.

No network. Every test writes inside ``tmp_path``.

The class of bug these cover has now appeared three times:

    finding A   overlay equity compared against itself     -> dd always 0.00%
    finding B   backend passed CURRENT equity as the peak  -> dd always 0.00%
    8fc3928     an `equity` override made both sides equal -> dd always 0.00%

Each fix addressed one route into the same failure. The store removes the class:
a caller can raise the mark, never lower it, and never supply it outright.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.state import PEAK_PATH_ENV, PeakStore  # noqa: E402


@pytest.fixture
def store(tmp_path) -> PeakStore:
    return PeakStore(tmp_path / "peak.json")


# --------------------------------------------------------------------------- #
# The mark itself                                                              #
# --------------------------------------------------------------------------- #

def test_first_observation_seeds_rather_than_reporting_a_drawdown(store):
    """A fresh install has no history; inventing one would be worse than a gap."""
    record = store.observe(100_000.0)
    assert record.nav_peak == 100_000.0
    assert record.tracked is False
    assert record.source == "seeded"


def test_the_mark_survives_a_new_store_instance(store, tmp_path):
    store.observe(200_000.0)
    store.observe(150_000.0)
    reopened = PeakStore(tmp_path / "peak.json")
    record = reopened.read()
    assert record.nav_peak == 200_000.0
    assert record.tracked is True
    assert record.source == "store"


def test_a_lower_observation_never_lowers_the_mark(store):
    store.observe(200_000.0)
    for equity in (190_000.0, 120_000.0, 55_000.0):
        record = store.observe(equity)
        assert record.nav_peak == 200_000.0


def test_a_higher_observation_raises_the_mark(store):
    store.observe(100_000.0)
    record = store.observe(250_000.0)
    assert record.nav_peak == 250_000.0


def test_nav_and_overlay_marks_are_tracked_independently(store):
    store.observe(100_000.0, 40_000.0)
    record = store.observe(90_000.0, 60_000.0)
    assert record.nav_peak == 100_000.0     # NAV fell, mark holds
    assert record.overlay_peak == 60_000.0  # overlay grew, mark rises


def test_absent_store_reports_untracked_not_zero(tmp_path):
    """The distinction the whole module exists for: unknown is not healthy."""
    record = PeakStore(tmp_path / "never-written.json").read()
    assert record.nav_peak is None
    assert record.tracked is False
    assert record.source == "absent"


# --------------------------------------------------------------------------- #
# Hostile input                                                                #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bad", [None, "abc", float("nan"), float("inf"), -5.0, 0.0, True])
def test_unusable_observations_are_ignored(store, bad):
    store.observe(100_000.0)
    record = store.observe(bad)
    assert record.nav_peak == 100_000.0


def test_a_corrupt_store_file_degrades_to_absent(tmp_path):
    path = tmp_path / "peak.json"
    path.write_text("{not json at all")
    record = PeakStore(path).read()
    assert record.tracked is False
    assert record.source == "absent"


def test_a_store_file_of_the_wrong_shape_degrades_to_absent(tmp_path):
    path = tmp_path / "peak.json"
    path.write_text('["a", "list", "not", "a", "mapping"]')
    assert PeakStore(path).read().source == "absent"


def test_accounts_do_not_share_marks(store):
    store.observe(500_000.0, account_id="big")
    assert store.read(account_id="small").source == "absent"
    assert store.read(account_id="big").nav_peak == 500_000.0


def test_reset_clears_the_mark(store):
    store.observe(100_000.0)
    store.reset()
    assert store.read().source == "absent"


def test_env_override_selects_the_path(tmp_path, monkeypatch):
    target = tmp_path / "from-env.json"
    monkeypatch.setenv(PEAK_PATH_ENV, str(target))
    PeakStore().observe(100_000.0)
    assert target.is_file()


def test_an_unwritable_path_does_not_raise(tmp_path):
    """A cycle must complete even when the mark cannot be persisted."""
    blocked = tmp_path / "ro"
    blocked.mkdir()
    os.chmod(blocked, 0o500)
    try:
        record = PeakStore(blocked / "peak.json").observe(100_000.0)
        assert record.nav_peak == 100_000.0  # in-memory answer still correct
    finally:
        os.chmod(blocked, 0o700)


# --------------------------------------------------------------------------- #
# Regression: the three routes into "drawdown always 0.00%"                    #
# --------------------------------------------------------------------------- #

def test_backend_pattern_equity_equals_peak_still_detects_a_drawdown(tmp_path, monkeypatch):
    """8fc3928 + finding B: the caller sends equity == peak_equity every cycle.

    The store must remember the earlier, higher value regardless.
    """
    monkeypatch.setenv(PEAK_PATH_ENV, str(tmp_path / "peak.json"))
    from agent.council import daily_cycle as dc

    monkeypatch.setattr(dc, "_PEAK_STORE", None, raising=False)

    book = [{"symbol": "NVDA", "qty": 100, "current_price": 300.0,
             "market_value": 30_000.0}]

    def cycle(equity: float) -> dict:
        return dc.run_daily_cycle(
            book, 0.0,
            portfolio_state_overrides={"equity": equity, "peak_equity": equity},
            candidate_snapshots={}, candidates=[],
        )

    first = cycle(200_000.0)
    assert first["halted"] is False
    assert first["portfolio_state"]["peak_source"] == "seeded"

    later = cycle(55_000.0)
    assert later["halted"] is True
    assert later["portfolio_state"]["peak_equity"] == 200_000.0
    assert later["portfolio_state"]["peak_source"] == "store"
    assert any("drawdown -72.50%" in r for r in later["halt_reasons"])

    monkeypatch.setattr(dc, "_PEAK_STORE", None, raising=False)


def test_a_slow_bleed_across_cycles_is_caught(tmp_path, monkeypatch):
    """max(equity, last_equity) is a two-day window and misses a slow decline.

    Five cycles of -2% each: no single day breaches the 2% daily threshold at
    exactly -2.0%, but cumulative drawdown passes 5%.
    """
    monkeypatch.setenv(PEAK_PATH_ENV, str(tmp_path / "peak.json"))
    from agent.council import daily_cycle as dc

    monkeypatch.setattr(dc, "_PEAK_STORE", None, raising=False)

    book = [{"symbol": "SPY", "qty": 100, "current_price": 500.0,
             "market_value": 50_000.0}]
    halted_at = None
    equity = 100_000.0
    for day in range(1, 6):
        result = dc.run_daily_cycle(
            book, 0.0,
            portfolio_state_overrides={"equity": equity, "peak_equity": equity},
            candidate_snapshots={}, candidates=[],
        )
        if result["halted"] and halted_at is None:
            halted_at = day
        equity *= 0.98

    assert halted_at is not None, "a 5-cycle slow bleed was never caught"
    monkeypatch.setattr(dc, "_PEAK_STORE", None, raising=False)
