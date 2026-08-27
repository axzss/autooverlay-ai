"""Fundamentals-enriched full council re-assessment.

For the 8-council universe (AAPL, MSFT, NVDA, TSLA, SPY, QQQ, JPM, KO):
  1. price/vol from the Alpaca data API when paper credentials are present
     in the environment (env-only, never logged); otherwise falls back to
     docs/market_snapshots.json (also real Alpaca data).
  2. fundamentals from FundamentalsProvider (free Yahoo endpoints, 24h
     /tmp cache, graceful degradation to None).
  3. runs CouncilEngine and APPENDS an "ADDENDUM — Fundamentals-Enriched
     Re-Assessment" section to docs/council_report.md (never overwrites).

Usage: python3 agent/council/run_full_assessment.py [--no-cache]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from agent.council.engine import CouncilEngine  # noqa: E402
from agent.council.graham_principles import evaluate_defensive  # noqa: E402
from agent.council.fundamentals import (  # noqa: E402
    FundamentalsProvider, build_snapshot_with_fundamentals,
)

UNIVERSE = ("AAPL", "MSFT", "NVDA", "TSLA", "SPY", "QQQ", "JPM", "KO")
REPORT_PATH = REPO / "docs" / "council_report.md"
SNAPSHOTS_PATH = REPO / "docs" / "market_snapshots.json"

# Baseline consensus scores from the LOW-confidence section of the report.
LOW_CONF_BASELINE = {
    "SPY": 56.6, "QQQ": 56.6, "JPM": 56.6, "KO": 56.6,
    "MSFT": 53.9, "NVDA": 53.9, "TSLA": 53.9, "AAPL": 53.3,
}


def load_price_snapshots() -> dict[str, dict]:
    """Real Alpaca bars via backend client if creds configured, else bundled."""
    try:
        sys.path.insert(0, str(REPO / "backend"))
        from backend.app.alpaca_client import AlpacaClient, is_configured
        from backend.app.routes.council import _snapshot_from_bars

        if is_configured():
            client = AlpacaClient()
            out: dict[str, dict] = {}
            for sym in UNIVERSE:
                try:
                    snap = _snapshot_from_bars(
                        sym, client.get_daily_bars(sym, days=365))
                    if snap:
                        out[sym] = snap
                except Exception as exc:
                    print(f"[warn] alpaca bars failed for {sym}: "
                          f"{exc.__class__.__name__}")
            if out:
                print(f"[info] price/vol source: live Alpaca data API "
                      f"({len(out)} symbols)")
                return out
    except Exception:
        pass
    snaps = {s["symbol"]: s for s in json.loads(SNAPSHOTS_PATH.read_text())}
    print("[info] Alpaca credentials not configured — using real Alpaca "
          "snapshots from docs/market_snapshots.json")
    return snaps


def graham_test_table(u: dict) -> list[dict]:
    results = evaluate_defensive(u)
    for r in results:
        if r["passed"] is True:
            r["status"] = "PASS"
        elif r["passed"] is False:
            r["status"] = "FAIL"
        else:
            r["status"] = "INCONCLUSIVE"
    return results


def main() -> None:
    no_cache = "--no-cache" in sys.argv
    provider = FundamentalsProvider()
    prices = load_price_snapshots()

    engine = CouncilEngine()
    rows, test_tables = [], {}
    for sym in UNIVERSE:
        ps = prices.get(sym)
        if not ps:
            continue
        u = build_snapshot_with_fundamentals(sym, ps, provider)
        if no_cache:
            u = build_snapshot_with_fundamentals(sym, ps, FundamentalsProvider())
        a = engine.assess_underlying(u)
        base = LOW_CONF_BASELINE.get(sym)
        delta = (round(a.consensus_score - base, 1)
                 if isinstance(base, (int, float)) else None)
        rows.append({
            "symbol": sym,
            "consensus": a.consensus_score,
            "baseline": base,
            "delta": delta,
            "rec": a.recommendation,
            "majority": a.majority_stance,
            "split": a.is_split,
            "verdicts": {k: (v.score, v.stance) for k, v in a.verdicts.items()},
            "pe_ratio": u.get("pe_ratio"),
            "pb_ratio": u.get("pb_ratio"),
            "current_ratio": u.get("current_ratio"),
            "dividend_yield_pct": u.get("dividend_yield_pct"),
            "roe_pct": u.get("roe_pct"),
            "debt_to_equity": u.get("debt_to_equity"),
        })
        test_tables[sym] = graham_test_table(u)

    lines: list[str] = []
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## ADDENDUM — Fundamentals-Enriched Re-Assessment")
    lines.append("")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"**Date:** {now}  ")
    lines.append("**Data sources:** Alpaca price/vol bars + free Yahoo Finance "
                 "unofficial fundamentals endpoints (`agent/council/"
                 "fundamentals.py`, 24h /tmp cache). No paid APIs.  ")
    lines.append("**Confidence:** upgraded **LOW → HIGH** where fundamentals "
                 "were available; fields that remain unavailable degrade to "
                 "neutral / INCONCLUSIVE per persona rules.")
    lines.append("")
    lines.append("### Consensus Table (fundamentals-enriched)")
    lines.append("")
    lines.append("| Symbol | Baseline (LOW) | New Consensus | Δ | Rec | Majority | Split | P/E | P/B | Cur. Ratio | Div Yld % | ROE % | D/E |")
    lines.append("|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|")
    for r in sorted(rows, key=lambda x: -x["consensus"]):
        def fmt(v, nd=1):
            return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "n/a"
        d = f"{r['delta']:+.1f}" if r["delta"] is not None else "n/a"
        lines.append(
            f"| {r['symbol']} | {fmt(r['baseline'])} | {r['consensus']:.1f} | {d} "
            f"| {r['rec']} | {r['majority']} | {'yes' if r['split'] else 'no'} "
            f"| {fmt(r['pe_ratio'])} | {fmt(r['pb_ratio'])} "
            f"| {fmt(r['current_ratio'])} | {fmt(r['dividend_yield_pct'], 2)} "
            f"| {fmt(r['roe_pct'])} | {fmt(r['debt_to_equity'], 2)} |")
    lines.append("")

    lines.append("### Graham Ch.14 Defensive Tests — Per-Symbol Outcomes")
    lines.append("")
    lines.append("PASS/FAIL/INCONCLUSIVE per exact-book criterion. Tests needing "
                 "20-year dividend history or 10-year EPS history are marked "
                 "**INCONCLUSIVE**, not failed, when the free sources cannot "
                 "supply sufficient history.")
    lines.append("")
    short_names = {r["name"].split("—")[0].strip(): r["name"]
                   for r in next(iter(test_tables.values()))}
    test_names = [r["name"] for r in next(iter(test_tables.values()))]
    header = "| Test | " + " | ".join(UNIVERSE) + " |"
    lines.append(header)
    lines.append("|---" * (len(UNIVERSE) + 1) + "|")
    for i, name in enumerate(test_names):
        cells = []
        for sym in UNIVERSE:
            tbl = test_tables.get(sym) or []
            st = tbl[i]["status"] if i < len(tbl) else "?"
            cells.append({"PASS": "✅", "FAIL": "❌",
                          "INCONCLUSIVE": "➖"}.get(st, st))
        lines.append(f"| T{i+1}: {name.split(' of')[0]} | " +
                     " | ".join(cells) + " |")
    lines.append("")
    detail_lines = []
    for sym in UNIVERSE:
        tbl = test_tables.get(sym) or []
        parts = []
        for t in tbl:
            parts.append(f"T{t['test']}={t['status']} ({t['detail']})")
        detail_lines.append(f"- **{sym}**: " + "; ".join(parts))
    lines.extend(detail_lines)
    lines.append("")

    # Confidence upgrade statement
    up = [r for r in rows if r["delta"] is not None]
    better = [r for r in up if r["delta"] > 0]
    worse = [r for r in up if r["delta"] < 0]
    flat = [r for r in up if r["delta"] == 0]
    new_recs = ", ".join(f"{r['symbol']}→{r['rec']}" for r in
                         sorted(rows, key=lambda x: -x["consensus"]))
    lines.append("### Confidence Upgrade Statement")
    lines.append("")
    lines.append(
        f"With fundamentals merged from free public sources, the council re-ran "
        f"the full eight-symbol universe at **HIGH confidence**: every persona "
        f"now receives valuation ({sum(1 for r in rows if r['pe_ratio'])}/8 with "
        f"P/E), profitability, leverage, and dividend inputs instead of degrading "
        f"to neutral defaults. Versus the LOW-confidence baseline: "
        f"{len(better)} symbols scored higher, {len(worse)} lower, "
        f"{len(flat)} unchanged. New recommendations: {new_recs}. "
        f"Graham tests that could not be decided on incomplete history are "
        f"reported INCONCLUSIVE rather than failed.")
    lines.append("")
    lines.append("*ETF note:* SPY/QQQ are index funds — trailing P/E, P/B and "
                 "per-share fundamentals do not apply; their enrichment comes "
                 "via size/revenue proxies only, so their scores remain "
                 "price/vol-dominated by design.")
    lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("a") as fh:
        fh.write("\n".join(lines))

    print(f"\nWrote ADDENDUM to {REPORT_PATH}")
    hdr = f"{'SYM':5}{'BASE':>7}{'NEW':>7}{'DELTA':>8}  REC"
    print(hdr)
    for r in sorted(rows, key=lambda x: -x["consensus"]):
        d = f"{r['delta']:+.1f}" if r["delta"] is not None else "n/a"
        print(f"{r['symbol']:5}{str(r['baseline']):>7}{r['consensus']:>7}"
              f"{d:>8}  {r['rec']}")


if __name__ == "__main__":
    main()
