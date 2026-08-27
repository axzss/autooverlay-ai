"""Tests for the daily cycle orchestrator — fully mocked, no network."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.council.daily_cycle import run_daily_cycle  # noqa: E402
from agent.council.engine import UnderlyingAssessment, PersonaVerdict  # noqa: E402

VALID_ACTIONS = ("EXIT", "ROLL", "INITIATE", "HOLD", "MONITOR")


def _snapshot(symbol: str, price: float = 100.0, vol: float = 18.0,
              drawdown: float = -3.0, recent_prices: list[float] | None = None) -> dict:
    # Build recent_prices if not provided: 20-day series from price*(1+drawdown/100) up to price
    if recent_prices is None:
        start = price / (1 + drawdown / 100)
        recent_prices = [start * (1 + i * drawdown / 100 / 19) for i in range(20)]
    return {
        "symbol": symbol,
        "price": price,
        "vol30d_annualized_pct": vol,
        "drawdown_from_52w_high_pct": drawdown,
        "w52_high": price / (1 + drawdown / 100),
        "w52_low": price * 0.8,
        "annualized_volatility_pct": vol,
        "recent_prices": recent_prices,
    }


def _fake_engine(consensus: float = 80.0):
    """CouncilEngine stand-in that returns a fixed bullish assessment."""

    class _FakeEngine:
        def __init__(self, *a, **k):
            pass

        def assess_underlying(self, underlying):
            verdicts = {
                "graham": PersonaVerdict("Benjamin Graham", 85.0, "STRONG_BUY",
                                         ["graham test 1 passed",
                                          "graham test 4 passed"]),
                "buffett": PersonaVerdict("Warren Buffett", 90.0, "STRONG_BUY",
                                          ["wide moat"]),
            }
            return UnderlyingAssessment(
                underlying.get("symbol", "?"), verdicts, consensus,
                "STRONG_BUY" if consensus >= 75 else "ACCUMULATE"
                if consensus >= 60 else "AVOID", "ACCUMULATE", False, [],
                mr_market_context={"mood": "indifferent"})

    return _FakeEngine


@pytest.fixture
def bullish_engine(monkeypatch):
    monkeypatch.setattr("agent.council.daily_cycle.CouncilEngine",
                        _fake_engine(80.0))


def _run(**kw) -> dict:
    snaps: dict = kw.pop("candidate_snapshots") if "candidate_snapshots" in kw else {
        s: _snapshot(s) for s in ("AAPL", "MSFT")}
    defaults: dict = dict(
        portfolio_positions=[{"symbol": "AAPL", "qty": 50,
                              "current_price": 100.0}],
        cash=50000.0,
        open_option_positions=[],
        candidate_snapshots=snaps,
        candidates=["MSFT"],
    )
    defaults.update(kw)
    return run_daily_cycle(**defaults)


# --------------------------------------------------------------------------- #
# Kill switch short-circuit                                                    #
# --------------------------------------------------------------------------- #

def test_kill_switch_short_circuits_everything():
    r = _run(portfolio_state_overrides={"consecutive_stop_losses": 3})
    assert r["halted"] is True
    assert r["kill_switch"]["halted"] is True
    assert any("stop-loss" in reason or "consecutive" in reason
               for reason in r["kill_switch"]["reasons"])
    # Nothing else ran — no assessments, no mr_market step.
    assert r["steps_run"] == []
    assert r["assessments"] == []
    assert len(r["directives"]) == 1
    d = r["directives"][0]
    assert d["action"] == "HOLD"
    assert any(p["source"] == "kill-switch" for p in d["provenance"])
    assert any("HALT" in line for line in d["reasoning_trace"])


def test_drawdown_breach_halts():
    r = _run(portfolio_state_overrides={
        "peak_equity": 200000.0})  # equity ~55000 → -72% drawdown
    assert r["halted"] is True


def test_healthy_portfolio_does_not_halt(bullish_engine):
    r = _run()
    assert r["halted"] is False
    assert "kill_switch" in r["steps_run"]
    assert r["steps_run"][0] == "kill_switch"


# --------------------------------------------------------------------------- #
# Directive structure / provenance / ordering                                  #
# --------------------------------------------------------------------------- #

def test_directive_structure_and_provenance(bullish_engine):
    r = _run(open_option_positions=[
        {"symbol": "AAPL", "strategy": "COVERED_CALL", "contracts": 1,
         "strike_price": 110, "expiration_date": "2099-01-01",
         "initial_premium": 2.0, "current_premium": 0.5, "delta": 0.15}])
    assert r["directives"], "expected at least one directive"
    for d in r["directives"]:
        assert set(d) >= {"action", "symbol", "params", "priority",
                          "reasoning_trace", "provenance"}
        assert d["action"] in VALID_ACTIONS
        assert isinstance(d["priority"], int) and 1 <= d["priority"] <= 5
        assert d["reasoning_trace"] and all(isinstance(t, str)
                                            for t in d["reasoning_trace"])
        assert isinstance(d["provenance"], list) and d["provenance"]
        for p in d["provenance"]:
            assert isinstance(p, dict) and p.get("source")


def test_exit_take_profit_maps_to_exit_directive_with_provenance(bullish_engine):
    r = _run(open_option_positions=[
        {"symbol": "AAPL", "strategy": "COVERED_CALL", "contracts": 1,
         "strike_price": 110, "expiration_date": "2099-01-01",
         "initial_premium": 2.0, "current_premium": 0.5, "delta": 0.15}])
    exit_d = [d for d in r["directives"] if d["action"] == "EXIT"]
    assert exit_d and exit_d[0]["symbol"] == "AAPL"
    assert exit_d[0]["priority"] == 1
    assert any(p["source"].startswith("exit:")
               for p in exit_d[0]["provenance"])


def test_roll_directive_on_delta_breach(bullish_engine):
    r = _run(open_option_positions=[
        {"symbol": "AAPL", "strategy": "SHORT_PUT", "contracts": 1,
         "initial_premium": 1.0, "current_premium": 1.0, "delta": -0.55}])
    rolls = [d for d in r["directives"] if d["action"] == "ROLL"]
    assert rolls and any("delta" in ln.lower()
                         for ln in rolls[0]["reasoning_trace"])


def test_priorities_sorted_exits_before_initiates(bullish_engine):
    r = _run(open_option_positions=[
        {"symbol": "AAPL", "strategy": "COVERED_CALL", "contracts": 1,
         "strike_price": 110, "expiration_date": "2099-01-01",
         "initial_premium": 2.0, "current_premium": 0.5, "delta": 0.15}])
    prios = [d["priority"] for d in r["directives"]]
    assert prios == sorted(prios)
    actions = [d["action"] for d in r["directives"]]
    assert actions.index("EXIT") < actions.index(
        next(a for a in actions if a != "EXIT"))


# --------------------------------------------------------------------------- #
# Entry screening                                                              #
# --------------------------------------------------------------------------- #

def test_initiate_directive_carries_tier_and_graham_provenance(bullish_engine):
    r = _run(
        portfolio_positions=[],
        # include SPY so it is loaded into the snapshot pool and used as the
        # market proxy for Mr. Market mood classification
        candidates=["SPY", "MSFT"],
        candidate_snapshots={
            "MSFT": _snapshot("MSFT"),
            "SPY": _snapshot("SPY", vol=10.0, drawdown=-2.0),
        },
    )
    init = [d for d in r["directives"] if d["action"] == "INITIATE"]
    assert init, [d["action"] for d in r["directives"]]
    d = init[0]
    srcs = {p["source"] for p in d["provenance"]}
    assert any(s.startswith("tier:") for s in srcs)
    assert any("graham" in s for s in srcs)
    assert d["params"]["size_multiplier"] in (0.5, 1.0)


def test_blocked_entry_returns_monitor_with_cited_traces(monkeypatch):
    # Huge tech holdings force the council §6 sector cap to block MSFT entry.
    monkeypatch.setattr("agent.council.daily_cycle.CouncilEngine",
                        _fake_engine(80.0))
    r = run_daily_cycle(
        portfolio_positions=[
            {"symbol": "NVDA", "qty": 400, "current_price": 100.0},
            {"symbol": "AAPL", "qty": 400, "current_price": 100.0},
        ],
        cash=100000.0,
        candidate_snapshots={"MSFT": _snapshot("MSFT")},
        candidates=["MSFT"],
    )
    blocked = [d for d in r["directives"]
               if d["action"] == "MONITOR" and d["params"].get("blocked")]
    assert blocked, [d["action"] for d in r["directives"]]
    d = blocked[0]
    assert d["params"]["blocking_rules"], "blocked entry must cite rules"
    joined = "\n".join(d["reasoning_trace"])
    assert "BLOCKED" in joined
    srcs = {p["source"] for p in d["provenance"]}
    assert any("§6" in s or "sector cap" in s for s in srcs)
    assert r["blocked_entries"].get("MSFT")


def test_euphoric_market_blocks_new_entries(monkeypatch):
    """Mr. Market euphoric → no INITIATE directives even on bullish council."""
    monkeypatch.setattr("agent.council.daily_cycle.CouncilEngine",
                        _fake_engine(80.0))
    spy = _snapshot("SPY", vol=10.0)
    base = spy["price"] * 1.30  # +30% run-up → euphoric
    # Need at least 5 price points for vol calculation
    spy["recent_prices"] = [base / 1.3, base / 1.25, base / 1.2, base / 1.1, base]
    r = run_daily_cycle(
        portfolio_positions=[{"symbol": "JPM", "qty": 50, "current_price": 100.0}],
        cash=50000.0,
        candidate_snapshots={"SPY": spy, "JPM": _snapshot("JPM", vol=10.0)},
        candidates=["SPY", "JPM"],
    )
    # Mr. Market should at minimum warn against buying under this euphoric series;
    # the integration assertion that matters is: no INITIATE directives are emitted.
    assert r["mr_market"]["warning_against_buying"] is True
    assert not [d for d in r["directives"] if d["action"] == "INITIATE"]


def test_provider_failure_degrades_gracefully():
    """No injected snapshot + no provider → missing symbols reported, no raise."""
    r = run_daily_cycle(
        portfolio_positions=[], cash=10000.0,
        candidates=["ZZZZ"], candidate_snapshots={}, allow_provider=False)
    assert r["halted"] is False
    assert "ZZZZ" in r["snapshot_symbols_missing"]
