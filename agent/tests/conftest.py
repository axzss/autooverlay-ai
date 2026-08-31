"""Shared fixtures for agent-layer tests.

No network, no credentials, no writes outside ``tmp_path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def isolated_peak_store(tmp_path, monkeypatch):
    """Give every test its own high-water-mark store.

    ``_build_portfolio_state`` persists NAV and overlay peaks across cycles, so
    without this fixture the first test to run would seed a mark that every
    later test silently inherits — and the suite's outcome would depend on test
    ordering and on whatever ``docs/.cache/peak_equity.json`` happened to hold
    from a previous run. A safety control's tests must not share mutable state.
    """
    from agent.council import daily_cycle as dc
    from agent.state import PeakStore

    store = PeakStore(tmp_path / "peak_equity.json")
    monkeypatch.setattr(dc, "_PEAK_STORE", store, raising=False)
    yield store
    monkeypatch.setattr(dc, "_PEAK_STORE", None, raising=False)
