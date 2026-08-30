#!/usr/bin/env python3
"""Reproduce the live-mode backend defects listed in docs/BRIEF-BACKEND-V2.md.

Run from the repo root:  python backend/tests/repro_live_defects.py

This is a demonstration script, not a pytest module — it deliberately sets fake
Alpaca credentials so the `is_configured() == True` branches execute, which the
real test suite never does (backend/tests/conftest.py strips them). No network
calls are made: every broker response is stubbed.

Expected output against ddcc665: D1, D2, D3, D4, D5 and D6 all FAIL.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

os.environ.update(
    ALPACA_KEY="FAKE_KEY_NOT_A_SECRET",
    ALPACA_SECRET="FAKE_SECRET_NOT_A_SECRET",
    ALPACA_BASE_URL="https://paper-api.alpaca.markets",
)

# Shape as Alpaca actually returns it: snapshots is a DICT keyed by OCC symbol,
# quote is camelCase `latestQuote` with bp/ap, no `details`, no `underlying_asset`.
REAL_PAYLOAD = {
    "snapshots": {
        "AAPL301231C00175000": {
            "greeks": {"delta": 0.22, "gamma": 0.01, "theta": -0.05, "vega": 0.10},
            "impliedVolatility": 0.24,
            "latestQuote": {"ap": 1.30, "as": 5, "bp": 1.20, "bs": 7,
                            "t": "2026-08-29T15:00:00Z"},
            "latestTrade": {"p": 1.25, "s": 1, "t": "2026-08-29T15:00:00Z"},
        }
    }
}

results: list[tuple[str, bool, str]] = []


def record(tag: str, ok: bool, detail: str) -> None:
    results.append((tag, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {tag}: {detail}")


def stub_httpx(payload: dict) -> None:
    import httpx

    class _Resp:
        status_code = 200
        content = b"x"

        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, *a, **k):
            return _Resp()

    httpx.Client = _Client


def d1_snapshot_parsing() -> None:
    stub_httpx(REAL_PAYLOAD)
    from backend.app import alpaca_client as ac

    try:
        out = ac.AlpacaClient().get_option_snapshots("AAPL")
        record("D1 get_option_snapshots parses dict payload", bool(out),
               f"returned {len(out)} snapshot(s)")
    except Exception as exc:
        record("D1 get_option_snapshots parses dict payload", False,
               f"{type(exc).__name__}: {exc}")


def d2_candidate_mapping() -> None:
    from backend.app.routes.strategy import _candidate_from_snapshot

    raw = dict(REAL_PAYLOAD["snapshots"]["AAPL301231C00175000"],
               symbol="AAPL301231C00175000")
    cand = _candidate_from_snapshot("AAPL", 300, raw)
    record("D2 _candidate_from_snapshot maps real fields", cand is not None,
           "built a candidate" if cand else "returned None (dropped at details.type)")


def d3_occ_expiration() -> None:
    from backend.app.routes.agent import _occ_expiration

    try:
        exp = _occ_expiration("AAPL301231C00175000")
        record("D3 _occ_expiration returns a date", True, f"parsed {exp}")
    except Exception as exc:
        record("D3 _occ_expiration returns a date", False,
               f"{type(exc).__name__}: {exc}")


def d3b_agent_run_status() -> None:
    from fastapi.testclient import TestClient
    from backend.app.main import app
    import backend.app.routes.agent as A

    snap = {"symbol": "AAPL301231C00175000", "greeks": {"delta": 0.22},
            "bid_price": 1.2, "ask_price": 1.3}
    A.AlpacaClient.get_option_snapshots = lambda self, s: [snap]

    async def fake_cycle(_req):
        return {
            "halted": False,
            "steps_run": ["stub"],
            "directives": [{
                "action": "INITIATE",
                "symbol": "AAPL",
                "params": {"delta_min": 0.1, "delta_max": 0.35, "max_dte": 600,
                           "strategy_allowed": ["COVERED_CALL"], "size": 1},
                "reasoning_trace": [],
            }],
        }

    A.council_cycle = fake_cycle
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/agent/run", json={})
    record("D3b POST /api/agent/run with a live chain", resp.status_code == 200,
           f"HTTP {resp.status_code}")


def d4_naked_order() -> None:
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)
    resp = client.post("/api/trade", json={
        "symbol": "GME301231C00100000", "qty": 500, "side": "sell",
        "type": "limit", "limit_price": 2.5, "time_in_force": "day",
    })
    blocked = resp.status_code in (403, 409)
    record("D4 500 naked short calls on an unheld symbol are blocked", blocked,
           f"HTTP {resp.status_code} — expected 409 from a pre-trade risk gate")


def d5_d6_concurrency() -> None:
    import backend.app.routes.council as CO

    def slow_fetch(symbols):
        time.sleep(0.4)  # stands in for bars + fundamentals over the network
        return {s: {"symbol": s, "price": 100.0, "vol30d_annualized_pct": 20.0,
                    "drawdown_from_52w_high_pct": -1.0,
                    "recent_prices": [100.0] * 60} for s in symbols}

    CO._fetch_live_snapshots = slow_fetch
    # `snapshots` is now passed in explicitly rather than read from a module
    # global — that signature change IS the D6 fix.
    CO._assessment_to_dict = lambda sym, snapshots: {
        "symbol": sym, "seen_universe": sorted(snapshots)
    }

    async def main():
        started = time.perf_counter()
        a, _b = await asyncio.gather(
            CO._assess(CO.CouncilAssessRequest(symbols=["AAPL"])),
            CO._assess(CO.CouncilAssessRequest(symbols=["TSLA", "NVDA", "JPM"])),
        )
        elapsed = time.perf_counter() - started
        # Serialized => ~0.8s. Concurrent => ~0.4s.
        record("D5 concurrent council requests overlap", elapsed < 0.6,
               f"{elapsed:.2f}s wall clock for two 0.4s requests")
        seen = a["assessments"][0]["seen_universe"] if a["assessments"] else []
        # Now a real check rather than one masked by D5: the two requests
        # genuinely overlap, so a shared snapshot dict would leak here.
        record("D6 per-request snapshot isolation", seen == ["AAPL"],
               f"request asking for AAPL saw {seen}")

    asyncio.run(main())


if __name__ == "__main__":
    d1_snapshot_parsing()
    d2_candidate_mapping()
    d3_occ_expiration()
    d3b_agent_run_status()
    d4_naked_order()
    d5_d6_concurrency()

    failed = [tag for tag, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks pass")
    if failed:
        print("open defects: " + ", ".join(failed))
    sys.exit(1 if failed else 0)
