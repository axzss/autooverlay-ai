import json, sys
sys.path.insert(0, "/root/autooverlay-ai")
from datetime import datetime, timedelta
from agent.decision_engine import DecisionEngine

exp = (datetime.utcnow() + timedelta(days=24)).strftime("%Y-%m-%d")

positions = [
    {"symbol": "AAPL", "qty": "200", "avg_entry_price": "172.45"},
    {"symbol": "MSFT", "qty": "25",  "avg_entry_price": "335.80"},   # <1 lot
    {"symbol": "NVDA", "qty": "100", "avg_entry_price": "820.50"},
]

calls = [  # covered-call candidates
    {"symbol": "AAPL", "option_symbol": "AAPL-C175", "underlying_price": 172.90,
     "strike_price": 180.0, "expiration_date": exp, "bid": 2.10, "ask": 2.30,
     "implied_volatility": 0.28, "delta": 0.22},
    {"symbol": "AAPL", "option_symbol": "AAPL-C174", "underlying_price": 172.90,
     "strike_price": 160.0, "expiration_date": exp, "last_price": 14.5,
     "implied_volatility": 0.35, "delta": 0.33},                      # below basis
    {"symbol": "MSFT", "option_symbol": "MSFT-C360", "underlying_price": 351.90,
     "strike_price": 360.0, "expiration_date": exp, "bid": 3.0, "ask": 3.2,
     "implied_volatility": 0.25, "delta": 0.20},                      # no lot
    {"symbol": "NVDA", "option_symbol": "NVDA-C900", "underlying_price": 1152.0,
     "strike_price": 900.0, "expiration_date": exp, "bid": 260.0, "ask": 262.0,
     "implied_volatility": 0.55, "delta": 0.34},                      # deep ITM, hi IV
]

puts = [  # cash-secured put candidates
    {"symbol": "AAPL", "option_symbol": "AAPL-P165", "underlying_price": 172.90,
     "strike_price": 165.0, "expiration_date": exp, "bid": 2.6, "ask": 2.8,
     "implied_volatility": 0.27, "delta": -0.18},                     # below basis
    {"symbol": "SPY",  "option_symbol": "SPY-P600",  "underlying_price": 612.4,
     "strike_price": 600.0, "expiration_date": exp, "last_price": 7.9,
     "implied_volatility": 0.16, "delta": -0.20},                     # new position
    {"symbol": "TSLA", "option_symbol": "TSLA-P300", "underlying_price": 310.0,
     "strike_price": 300.0, "expiration_date": exp, "bid": 11.0, "ask": 11.6,
     "implied_volatility": 0.48, "delta": -0.32},                     # rich IV
]

de = DecisionEngine(account_cash=50000.0)
result = de.evaluate(puts, calls, positions)
print(json.dumps(result["ranked_recommendations"], indent=2)[:400])
print("\n=== ACTIONS ===")
for a in result["actions"]:
    print(f"{a['type']:17s} {a['symbol']:5s} x{a['contracts']} "
          f"annYield={a['annualized_premium_yield']*100:5.1f}% risk={a['risk_score']}/100")
    print("  ", a["rationale"])
print("\n=== ALL SCREENED ===")
for r in result["ranked_recommendations"]:
    print(f"{r['strategy']:17s} {r['symbol']:5s} K={r['strike_price']:<7.1f} dte={r['dte']} "
          f"|delta|={r['delta']:<5} annYield={r['annualized_premium_yield']*100:5.1f}% "
          f"risk={r['risk_score']:>3}/100 -> {r['recommendation']}")
print("\n=== HEALTH ===", json.dumps(result["portfolio_health"]))
