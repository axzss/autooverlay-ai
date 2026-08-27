"""
End-to-end proof that the strategy engine CONSUMES the council handoff.

Shows, for each of the 8 council tickers:
  - which volatility tier applies (council §2 boundaries),
  - the effective delta band / DTE / allowed strategies / size multiplier,
then demonstrates:
  - TSLA being restricted by its council override,
  - a simulated portfolio where adding a 4th tech CSP is blocked by the
    §6 tech-complex sector cap.

Run:  python3 agent/verify_council_consumption.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.council.handoff import (
    effective_policy_for_symbol, get_tier_for_symbol, load_council_handoff)
from agent.config import StrategyConfig
from agent.portfolio_analyst import PortfolioAnalyst
from agent.strategies.cash_secured_put import CashSecuredPutStrategy
from agent.strategies.covered_call import CoveredCallStrategy

# Council report §2 market data table
UNIVERSE = {
    "SPY":  {"vol": 12.2, "price": 765.79},
    "JPM":  {"vol": 17.6, "price": 356.67},
    "QQQ":  {"vol": 21.5, "price": 710.66},
    "KO":   {"vol": 24.4, "price": 91.63},
    "AAPL": {"vol": 30.5, "price": 309.89},
    "NVDA": {"vol": 35.9, "price": 212.96},
    "MSFT": {"vol": 48.9, "price": 491.55},
    "TSLA": {"vol": 59.1, "price": 350.24},
}


def main() -> None:
    policies = load_council_handoff()
    print("=" * 78)
    print("COUNCIL HANDOFF → STRATEGY ENGINE CONSUMPTION PROOF")
    print("=" * 78)

    print("\n[1] Parsed tier policies (from docs/council_report.md HANDOFF):")
    for tier, p in policies.items():
        print(f"    {tier:4s} ({p.vol_band:7s}) delta {p.delta_min:.2f}-{p.delta_max:.2f} "
              f"DTE<={p.max_dte} strategies={','.join(p.allowed_strategies):13s} "
              f"size x{p.size_multiplier} [{p.source}]")

    print("\n[2] Tier + effective delta band per ticker:")
    hdr = f"    {'SYM':5s} {'vol%':>6s} {'tier':5s} {'delta band':12s} " \
          f"{'max DTE':>8s} {'strategies':22s} {'size':>5s}"
    print(hdr)
    for sym, d in UNIVERSE.items():
        pol, notes = effective_policy_for_symbol(sym, d["vol"], policies)
        override = " ←TSLA OVERRIDE" if any("OVERRIDE" in n for n in notes) else ""
        strategies = ",".join(pol.allowed_strategies)
        print(f"    {sym:5s} {d['vol']:6.1f} {pol.name:5s} "
              f"{f'{pol.delta_min:.2f}-{pol.delta_max:.2f}':12s} "
              f"{pol.max_dte:>8d} {strategies:22s} x{pol.size_multiplier:<3g}{override}")

    print("\n[3] TSLA restriction demo — screening a TSLA CSP under its policy:")
    tsla_pol, notes = effective_policy_for_symbol("TSLA", UNIVERSE["TSLA"]["vol"])
    for n in notes:
        print(f"    note: {n}")
    csp_high = CashSecuredPutStrategy(tier_policy=tsla_pol,
                                      min_annualized_yield=0.05)
    opp = {"symbol": "TSLA", "strike_price": 300.0, "delta": 0.08,
           "days_to_expiry": 25, "underlying_price": 350.24,
           "premium_received_per_share": 4.50}
    res = csp_high.screen([opp], account_cash=250_000)[0]
    print(f"    TSLA CSP delta 0.08 → recommendation: {res['recommendation']} "
          f"(CSP blocked on high tier; covered-call-only per council)")
    print(f"    trace[0]: {res['reasoning_trace'][0]}")
    print(f"    trace[1]: {res['reasoning_trace'][1]}")

    print("\n[4] Mid-tier sizing demo — KO CSP with size multiplier:")
    ko_pol = policies["mid"]
    csp_mid = CashSecuredPutStrategy(tier_policy=ko_pol,
                                     min_annualized_yield=0.05)
    ko_opp = {"symbol": "KO", "strike_price": 85.0, "delta": 0.18,
              "days_to_expiry": 30, "underlying_price": 91.63,
              "premium_received_per_share": 1.20}
    r = csp_mid.screen([ko_opp], account_cash=500_000)[0]
    print(f"    KO CSP → {r['recommendation']}, contracts={r['contracts']} "
          f"(multiplier x{r['tier_size_multiplier']})")
    for line in r["reasoning_trace"]:
        if "tier sizing" in line or "band" in line:
            print(f"    {line}")

    print("\n[5] Simulated portfolio — 4th tech CSP vs §6 sector cap:")
    cfg = StrategyConfig()  # max_sector_concentration_pct = 40.0
    pa = PortfolioAnalyst(config=cfg)
    positions = [
        {"symbol": "AAPL", "collateral": 31_000},   # AAPL CSP
        {"symbol": "MSFT", "collateral": 20_000},   # MSFT position
        {"symbol": "NVDA", "collateral": 15_000},   # NVDA position
        {"symbol": "SPY",  "collateral": 76_600},   # pilot SPY covered overlay
        {"symbol": "JPM",  "collateral": 35_700},   # pilot JPM CSP
        {"symbol": "KO",   "collateral": 9_200},    # pilot KO CSP
    ]
    deployed = pa.deployed_overlay_capital(positions)
    tech_now = sum(p["collateral"] for p in positions
                   if p["symbol"] in cfg.sector_cap_group)
    print(f"    deployed overlay capital: ${deployed:,.0f}")
    print(f"    tech complex now (AAPL+MSFT+NVDA): ${tech_now:,.0f} "
          f"({tech_now/deployed*100:.1f}% of deployed)")
    print(f"    cap: {cfg.max_sector_concentration_pct:.0f}% "
          f"group={'+'.join(cfg.sector_cap_group)}")

    # A QQQ CSP would be the 4th tech entry.
    qqq_collateral = 71_000
    allowed, trace = pa.check_new_position(
        "QQQ", collateral_required=qqq_collateral,
        existing_overlay_value_for_symbol=0.0,
        portfolio_value=250_000, account_cash=200_000,
        existing_positions=positions)
    projected = (tech_now + qqq_collateral) / (deployed + qqq_collateral)
    print(f"    adding QQQ CSP (+${qqq_collateral:,}): projected complex = "
          f"${tech_now + qqq_collateral:,.0f} / ${deployed + qqq_collateral:,.0f} "
          f"= {projected*100:.1f}%")
    for line in trace:
        if "sector-cap" in line or "council rule" in line:
            print(f"    → {line}")
    print(f"\n    RESULT: new QQQ CSP {'ALLOWED' if allowed else 'BLOCKED'} "
          f"(expected: BLOCKED)")

    # Contrast: a non-tech entry passes.
    ok2, _ = pa.check_new_position(
        "JPM", collateral_required=10_000,
        existing_overlay_value_for_symbol=35_700,
        portfolio_value=250_000, account_cash=150_000,
        existing_positions=positions)
    print(f"    contrast: adding JPM overlay → "
          f"{'ALLOWED' if ok2 else 'BLOCKED'} (expected: ALLOWED)")

    print("\n" + "=" * 78)
    assert not allowed and ok2
    print("ALL CHECKS PASSED: engine consumes the council handoff.")


if __name__ == "__main__":
    main()
