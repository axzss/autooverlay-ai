"""Tests for the fundamentals enrichment layer (agent/council/fundamentals.py).

No network in tests — FundamentalsProvider is stubbed with fixture data and
the HTTP methods are monkeypatched. Cache is redirected to tmp_path.
"""

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.council.engine import CouncilEngine
from agent.council.fundamentals import (
    FundamentalsProvider, build_snapshot_with_fundamentals,
)
from agent.council.graham_principles import evaluate_defensive


PRICE_SNAPSHOT = {
    "symbol": "TEST",
    "price": 100.0,
    "day_change_pct": 0.5,
    "vol30d_annualized_pct": 22.0,
    "drawdown_from_52w_high_pct": -5.0,
    "w52_low": 80.0,
    "w52_high": 120.0,
    "n_days_used": 30,
}


def make_provider(tmp_path, cached=None):
    return FundamentalsProvider(
        cache_path=tmp_path / "fundamentals_cache.json", ttl_seconds=3600)


FULL_FUNDAMENTALS = {
    "symbol": "TEST",
    "market_cap": 2_000_000_000_000,
    "pe_ratio": 12.0,
    "forward_pe": 11.0,
    "pb_ratio": 1.0,
    "peg_ratio": 0.8,
    "dividend_yield_pct": 2.0,
    "eps_trailing": 8.33,
    "eps_fwd_estimate": 9.1,
    "book_value_per_share": 100.0,
    "current_ratio": 2.5,
    "quick_ratio": 2.0,
    "debt_to_equity": 0.3,
    "roe_pct": 25.0,
    "gross_margin_pct": 55.0,
    "operating_margin_pct": 28.0,
    "profit_margin_pct": 22.0,
    "total_cash": 50e9,
    "total_debt": 60e9,
    "revenue_ttm": 300e9,
    "free_cash_flow_yield_pct": None,
    "earnings_growth_fwd_pct": 15.0,
    "earnings_growth_5y_pct": 10.0,
    "revenue_growth_fwd_pct": 12.0,
    "dividend_years_paid": [True] * 20,
    "dividend_years_paid_partial": [True] * 20,
    "years_since_dividend_started": 40.0,
    "positive_earnings_years": None,
}


# --------------------------------------------------------------------------- #
# Provider: caching & graceful degradation                                    #
# --------------------------------------------------------------------------- #
class TestProvider:
    def test_cache_hit_avoids_refetch(self, tmp_path, monkeypatch):
        prov = make_provider(tmp_path)
        calls = {"quoteSummary": 0}

        def fake_qs(symbol):
            calls["quoteSummary"] += 1
            return {}

        monkeypatch.setattr(prov, "_fetch_quote_summary", fake_qs)

        first = prov.get_fundamentals("TEST")
        second = prov.get_fundamentals("TEST")
        assert calls["quoteSummary"] == 1          # second call served from cache
        assert first == second
        assert (tmp_path / "fundamentals_cache.json").exists()

    def test_expired_cache_refetches(self, tmp_path, monkeypatch):
        prov = FundamentalsProvider(
            cache_path=tmp_path / "c.json", ttl_seconds=1)
        monkeypatch.setattr(prov, "_fetch_quote_summary", lambda s: {})
        prov.get_fundamentals("TEST")
        # age the cache entry past TTL
        cache = json.loads((tmp_path / "c.json").read_text())
        cache["TEST"]["ts"] = time.time() - 7200
        (tmp_path / "c.json").write_text(json.dumps(cache))
        calls = []
        monkeypatch.setattr(
            prov, "_fetch_quote_summary",
            lambda s: calls.append(s) or {})
        prov.get_fundamentals("TEST")
        assert calls == ["TEST"]                   # refetched after expiry

    def test_total_failure_degrades_to_none_fields(self, tmp_path, monkeypatch):
        prov = make_provider(tmp_path)
        monkeypatch.setattr(prov, "_fetch_quote_summary", lambda s: {})
        monkeypatch.setattr(prov, "_fetch_dividend_history", lambda s, years=25: [])
        f = prov.get_fundamentals("FAIL")
        for key in ("pe_ratio", "pb_ratio", "current_ratio", "roe_pct",
                    "dividend_yield_pct", "debt_to_equity", "market_cap"):
            assert f[key] is None
        assert f["dividend_years_paid"] is None

    def test_short_dividend_history_stays_inconclusive(self, tmp_path):
        """<20y coverage must NOT fail Graham's exact-book test 4."""
        u = build_snapshot_with_fundamentals("TEST", PRICE_SNAPSHOT,
                                             provider=make_provider(tmp_path))
        u.update(FULL_FUNDAMENTALS | {
            "dividend_years_paid": None,
            "dividend_years_paid_partial": [True] * 15,
            "years_since_dividend_started": None})
        results = {r["test"]: r for r in evaluate_defensive(u)}
        assert results[4]["passed"] is None        # inconclusive, not failed

    def test_full_dividend_history_decides_test(self, tmp_path):
        u = build_snapshot_with_fundamentals("TEST", PRICE_SNAPSHOT,
                                             provider=make_provider(tmp_path))
        u.update(dict(FULL_FUNDAMENTALS))          # 20/20 paid -> PASS
        results = {r["test"]: r for r in evaluate_defensive(u)}
        assert results[4]["passed"] is True


# --------------------------------------------------------------------------- #
# build_snapshot_with_fundamentals                                            #
# --------------------------------------------------------------------------- #
class TestBuildSnapshot:
    def test_merges_price_and_fundamentals(self, tmp_path):
        prov = make_provider(tmp_path)
        monkey_full = dict(FULL_FUNDAMENTALS)
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            prov, "get_fundamentals", lambda s, use_cache=True: dict(monkey_full))
        u = build_snapshot_with_fundamentals("TEST", PRICE_SNAPSHOT, prov)
        # bar-derived fields preserved
        assert u["price"] == PRICE_SNAPSHOT["price"]
        assert u["annualized_volatility_pct"] == 22.0
        # fundamentals merged
        assert u["pe_ratio"] == 12.0
        assert u["current_ratio"] == 2.5
        # derived persona-facing fields
        assert u["earnings_yield_pct"] == pytest.approx(100 * 8.33 / 100, rel=1e-3)
        assert u["intrinsic_value_estimate"] == pytest.approx(8.33 * 15, rel=1e-3)
        assert u["annual_sales_musd"] == pytest.approx(300_000, rel=1e-3)
        monkeypatch.undo()

    def test_engine_runs_on_enriched_snapshot(self, tmp_path):
        prov = make_provider(tmp_path)
        pytest.MonkeyPatch().setattr(
            prov, "get_fundamentals",
            lambda s, use_cache=True: dict(FULL_FUNDAMENTALS))
        u = build_snapshot_with_fundamentals("TEST", PRICE_SNAPSHOT, prov)
        a = CouncilEngine().assess_underlying(u)
        assert 0 <= a.consensus_score <= 100
        assert len(a.verdicts) == 6

    def test_none_fundamentals_never_breaks_engine(self, tmp_path):
        prov = make_provider(tmp_path)
        pytest.MonkeyPatch().setattr(
            prov, "get_fundamentals",
            lambda s, use_cache=True: {"symbol": s})
        u = build_snapshot_with_fundamentals("TEST", PRICE_SNAPSHOT, prov)
        a = CouncilEngine().assess_underlying(u)   # must not raise
        assert a.verdicts

    def _num_normalization(self):
        pass


# --------------------------------------------------------------------------- #
# Yahoo response parsing (unit-level, offline fixtures)                       #
# --------------------------------------------------------------------------- #
class TestParsing:
    def test_num_handles_raw_dicts_and_bad_values(self):
        from agent.council.fundamentals import _num
        assert _num({"raw": 5}) == 5.0
        assert _num(7) == 7.0
        assert _num(None) is None
        assert _num(float("nan")) is None
        assert _num(True) is None                  # bools are not numbers here
        assert _num("abc") is None

    def test_dividend_yearly_aggregation_from_fixture(self, tmp_path, monkeypatch):
        import types
        prov = make_provider(tmp_path)

        class FakeResp:
            status_code = 200
            def json(self):
                base_ts = 1_600_000_000  # 2020-09; gmtime year boundaries below
                evs = {}
                for i, yr in enumerate([2019, 2019, 2020, 2020]):
                    evs[str(i)] = {"amount": 0.5 + i * 0.1,
                                   "date": base_ts - (2026 - yr) * 31_557_600}
                return {"chart": {"result": [{"events": {"dividends": evs}}]}}

        class FakeSession:
            def get(self, url, params=None, timeout=None):
                return FakeResp()

        monkeypatch.setattr(prov, "_get_session", lambda: FakeSession())
        hist = prov._fetch_dividend_history("KO")
        assert len(hist) == 2                      # two distinct calendar years
        assert all(h > 0 for h in hist)
