"""Event-loop concurrency for the council routes (D5) and per-request snapshot
isolation (D6).

D5: `_assess` and `council_cycle` called blocking Alpaca code directly from
`async def`, so a single request held the event loop for its whole duration —
8 symbols x 4 HTTP calls each — and every other request, `/health` included,
queued behind it.

D6: `_assessment_to_dict` read a module-level `_snapshots` dict that `_assess`
overwrote per request. Two concurrent requests shared it. This only ever looked
safe because D5 serialised everything, so **fixing D5 without fixing D6 would
have turned a latent bug into live cross-request data leakage** — which is why
both are tested together here.

These tests drive the coroutines through `asyncio.run` rather than
`pytest.mark.asyncio`: `pytest-asyncio` is not installed, and a concurrency fix
is not worth a new test dependency.

Timing assertions use generous margins: a loaded CI box makes tight ones flaky,
and the defect being detected is an 8x serialisation, not a 20% wobble.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

import backend.app.routes.council as council_route

FETCH_DELAY = 0.30


def _snapshot(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "price": 100.0,
        "vol30d_annualized_pct": 20.0,
        "drawdown_from_52w_high_pct": -1.0,
        "recent_prices": [100.0] * 60,
    }


def _slow_fetch(symbols):
    """Stand-in for bars + fundamentals over the network."""
    time.sleep(FETCH_DELAY)
    return {s: _snapshot(s) for s in symbols}


def _request(*symbols):
    return council_route.CouncilAssessRequest(symbols=list(symbols) or None)


@pytest.fixture
def live_council(monkeypatch):
    monkeypatch.setattr(council_route, "is_configured", lambda: True)
    monkeypatch.setattr(council_route, "_fetch_live_snapshots", _slow_fetch)


# --- D5: the event loop stays responsive --------------------------------


def test_two_council_assessments_overlap(live_council):
    """Serialised => ~2x FETCH_DELAY. Concurrent => ~1x."""
    async def scenario():
        started = time.perf_counter()
        await asyncio.gather(
            council_route._assess(_request("AAPL")),
            council_route._assess(_request("TSLA", "NVDA")),
        )
        return time.perf_counter() - started

    elapsed = asyncio.run(scenario())
    assert elapsed < FETCH_DELAY * 1.8, (
        f"{elapsed:.2f}s for two {FETCH_DELAY}s fetches — they did not overlap"
    )


def test_four_council_assessments_overlap(live_council):
    """Scales: four concurrent requests must not cost four fetch delays."""
    async def scenario():
        started = time.perf_counter()
        await asyncio.gather(*[
            council_route._assess(_request(sym))
            for sym in ("AAPL", "MSFT", "NVDA", "TSLA")
        ])
        return time.perf_counter() - started

    elapsed = asyncio.run(scenario())
    assert elapsed < FETCH_DELAY * 2.5, f"{elapsed:.2f}s for four concurrent fetches"


def test_a_trivial_coroutine_is_not_starved_by_a_council_fetch(live_council):
    """The `/health` case: a cheap request must answer while a fetch is running.

    Measured with a ticker that loops on `asyncio.sleep(0.01)` and records the
    largest gap between iterations. A blocking fetch on the loop shows up as one
    gap the length of the whole fetch.

    An earlier version of this test scheduled the fetch with `create_task` and
    then measured a single `sleep(0)` — which passed against the unfixed code,
    because the blocking fetch ran to completion inside the very first `await`
    and there was nothing left to be starved by. A concurrency test that cannot
    fail on the broken version is worse than no test.
    """
    async def scenario():
        gaps: list[float] = []
        stop = asyncio.Event()

        async def ticker():
            last = time.perf_counter()
            while not stop.is_set():
                await asyncio.sleep(0.01)
                now = time.perf_counter()
                gaps.append(now - last)
                last = now

        tick = asyncio.create_task(ticker())
        await asyncio.sleep(0.02)  # let the ticker establish a baseline
        await council_route._assess(_request("AAPL"))
        stop.set()
        await tick
        return max(gaps)

    worst_gap = asyncio.run(scenario())
    assert worst_gap < FETCH_DELAY / 2, (
        f"the loop stalled for {worst_gap:.2f}s during a {FETCH_DELAY}s fetch"
    )


def test_the_cycle_route_also_yields_the_loop(monkeypatch):
    """`council_cycle` runs the portfolio fetch, snapshots and the cycle itself
    in worker threads. `run_daily_cycle` is CPU-bound over six personas."""
    monkeypatch.setattr(council_route, "is_configured", lambda: True)
    monkeypatch.setattr(council_route, "_fetch_live_snapshots", _slow_fetch)

    def slow_portfolio():
        time.sleep(FETCH_DELAY)
        return [], [], {"equity": "100000", "cash": "100000"}

    def slow_cycle(*args, **kwargs):
        time.sleep(FETCH_DELAY)
        return {"halted": False, "directives": [], "steps_run": ["stub"]}

    monkeypatch.setattr(council_route, "_fetch_live_portfolio", slow_portfolio)
    monkeypatch.setattr(council_route, "run_daily_cycle", slow_cycle)

    async def scenario():
        started = time.perf_counter()
        await asyncio.gather(
            council_route.council_cycle(council_route.CouncilCycleRequest()),
            council_route.council_cycle(council_route.CouncilCycleRequest()),
        )
        return time.perf_counter() - started

    elapsed = asyncio.run(scenario())
    # Each request does 3 x FETCH_DELAY of blocking work. Serialised that is 6;
    # concurrent it is ~3.
    assert elapsed < FETCH_DELAY * 4.5, f"{elapsed:.2f}s — the cycle route serialised"


# --- D6: snapshots are per-request -------------------------------------


def test_concurrent_requests_do_not_see_each_others_snapshots(live_council):
    """The leak D5 was hiding.

    Now that the two requests genuinely overlap, a shared dict would show up
    here: the AAPL request would render TSLA/NVDA/JPM data.
    """
    seen: dict[str, list[str]] = {}

    def record_universe(symbol, snapshots):
        seen.setdefault(symbol, sorted(snapshots))
        return {"symbol": symbol, "consensus_score": 50.0}

    async def scenario():
        await asyncio.gather(
            council_route._assess(_request("AAPL")),
            council_route._assess(_request("TSLA", "NVDA", "JPM")),
        )

    with patch.object(council_route, "_assessment_to_dict", record_universe):
        asyncio.run(scenario())

    assert seen["AAPL"] == ["AAPL"]
    assert seen["TSLA"] == ["JPM", "NVDA", "TSLA"]


def test_the_module_no_longer_carries_a_snapshot_global():
    """Guards against the global being reintroduced by a later merge."""
    assert not hasattr(council_route, "_snapshots"), (
        "module-level _snapshots is back — that is D6"
    )


def test_assessment_to_dict_requires_snapshots_explicitly():
    """The signature change is the fix; a positional arg cannot be forgotten."""
    import inspect

    params = list(inspect.signature(council_route._assessment_to_dict).parameters)
    assert params == ["symbol", "snapshots"]


def test_each_request_returns_only_its_own_symbols(live_council):
    async def scenario():
        return await asyncio.gather(
            council_route._assess(_request("AAPL")),
            council_route._assess(_request("KO")),
        )

    a, b = asyncio.run(scenario())
    assert [x["symbol"] for x in a["assessments"]] == ["AAPL"]
    assert [x["symbol"] for x in b["assessments"]] == ["KO"]


def test_a_failed_fetch_in_one_request_does_not_affect_another(monkeypatch):
    """One request's broker failure must not empty another's snapshots."""
    monkeypatch.setattr(council_route, "is_configured", lambda: True)

    def flaky(symbols):
        if "TSLA" in symbols:
            raise RuntimeError("Alpaca data API error 503")
        time.sleep(FETCH_DELAY)
        return {s: _snapshot(s) for s in symbols}

    monkeypatch.setattr(council_route, "_fetch_live_snapshots", flaky)

    async def scenario():
        return await asyncio.gather(
            council_route._assess(_request("AAPL")),
            council_route._assess(_request("TSLA")),
        )

    good, bad = asyncio.run(scenario())
    assert good["count"] == 1
    assert bad["count"] == 0
    assert bad["mode"] == "live"  # a failure is never silently relabelled mock


# --- the route surface still behaves ------------------------------------


def test_the_assess_endpoint_still_returns_assessments(client):
    body = client.get("/api/council/assess?symbols=AAPL,NVDA").json()
    assert body["count"] == 2
    assert {a["symbol"] for a in body["assessments"]} == {"AAPL", "NVDA"}
    assert all(a["verdicts"] for a in body["assessments"])


def test_the_cycle_endpoint_still_halts_on_the_bundled_mock_portfolio(client):
    """The mock account is down 13% from peak, so the kill-switch fires.

    Verified identical on 65f1e41, so this is the pre-existing behaviour, not a
    regression from the threading change. The halt short-circuits before
    `step("kill_switch")` is recorded, which is why `steps_run` is empty.
    """
    body = client.post("/api/council/cycle", json={}).json()
    assert body["halted"] is True
    assert any("drawdown" in r for r in body["halt_reasons"])
    assert body["steps_run"] == []
    assert body["directives"][0]["action"] == "HOLD"


def test_the_cycle_endpoint_runs_every_step_when_not_halted(client):
    """With the drawdown overridden away, all seven steps execute."""
    body = client.post("/api/council/cycle", json={
        "portfolio_state_overrides": {"peak_equity": 41506.28, "prev_equity": 41506.28},
    }).json()
    assert body["halted"] is False
    assert body["steps_run"] == [
        "kill_switch", "snapshots", "mr_market", "council_assessments",
        "exits", "entry_screening", "directives",
    ]
    assert body["assessments"]


def test_a_broker_failure_in_the_cycle_is_still_a_502(client, monkeypatch):
    monkeypatch.setattr(council_route, "is_configured", lambda: True)

    def boom():
        raise RuntimeError("Alpaca request timed out")

    monkeypatch.setattr(council_route, "_fetch_live_portfolio", boom)
    response = client.post("/api/council/cycle", json={})

    assert response.status_code == 502
    assert "timed out" in response.json()["detail"]
