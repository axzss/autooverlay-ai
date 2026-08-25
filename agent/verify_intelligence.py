"""End-to-end verification of the agentic intelligence layer:
exit management + portfolio context + reasoning traces, all through
DecisionEngine.evaluate() with sample data. Run: python agent/verify_intelligence.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.decision_engine import DecisionEngine  # noqa: E402

AS_OF_STYLE_EXPIRY = "2026-09-15T12:00:00Z"

csp_opps = [{
    "symbol": "AAPL", "option_symbol": "AAPL260915P00145000",
    "underlying_price": 180.0, "strike_price": 145.0,
    "last_price": 4.50, "delta": -0.20, "implied_volatility": 0.35,
    "expiration_date": AS_OF_STYLE_EXPIRY, "days_to_expiry": 21,
}]
cc_opps = [{
    "symbol": "MSFT", "option_symbol": "MSFT260915C00460000",
    "underlying_price": 420.0, "strike_price": 460.0,
    "last_price": 8.00, "delta": 0.18, "implied_volatility": 0.25,
    "expiration_date": AS_OF_STYLE_EXPIRY, "days_to_expiry": 21,
}]
positions = [
    {"symbol": "MSFT", "qty": 100, "avg_entry_price": 400.00},
    {"symbol": "AAPL", "qty": 100, "avg_entry_price": 170.00},
]
open_options = [
    {   # profit-taking candidate: sold @ 2.50, now 0.90 -> 64% captured
        "symbol": "AAPL", "strategy": "SHORT_CALL", "contracts": 1,
        "strike_price": 190.0, "expiration_date": AS_OF_STYLE_EXPIRY,
        "days_to_expiry": 12, "initial_premium": 2.50,
        "current_premium": 0.90, "delta": 0.22,
    },
    {   # roll candidate: delta breached 0.40 and DTE < 7
        "symbol": "TSLA", "strategy": "SHORT_PUT", "contracts": 1,
        "strike_price": 220.0, "expiration_date": "2026-08-28T12:00:00Z",
        "days_to_expiry": 3, "initial_premium": 3.00,
        "current_premium": 3.20, "delta": -0.44,
    },
]

engine = DecisionEngine(account_cash=50_000.0, portfolio_value=200_000.0)
out = engine.evaluate(csp_opportunities=csp_opps, cc_opportunities=cc_opps,
                      positions=positions, open_option_positions=open_options)

print("=" * 72)
print("ENTRY RECOMMENDATIONS (with reasoning traces)")
for row in out["ranked_recommendations"]:
    print(f"\n{row['strategy']} {row['symbol']} -> "
          f"{row['recommendation']} (risk {row['risk_score']}/100)")
    for step in row["reasoning_trace"]:
        print(f"   • {step}")

print("\n" + "=" * 72)
print("EXIT ACTIONS")
for ex in out["exit_actions"]:
    print(f"\n{ex['symbol']} short {ex['strategy']} -> {ex['action']} "
          f"(rule: {ex['rule_triggered']}, order_side: {ex['order_side']})")
    print(f"   rationale: {ex['rationale']}")
    for step in ex["reasoning_trace"]:
        print(f"   • {step}")

print("\n" + "=" * 72)
print("PORTFOLIO CONTEXT")
ctx = out["portfolio_context"]
for step in ctx["reasoning_trace"]:
    print(f"   • {step}")
print(f"   concentration table: "
      f"{json.dumps(ctx['concentration'], indent=None)}")

# Assertions: the layer behaves as specified.
assert out["exit_actions"][0]["action"] == "TAKE_PROFIT"
assert out["exit_actions"][1]["action"] == "ROLL"
assert ctx["concentration_breaches"] == []
assert all(r["reasoning_trace"] for r in out["ranked_recommendations"])
assert all(a["reasoning_trace"] for a in out["actions"])
assert out["portfolio_context"]["sector_exposure"]["tech"]["value"] == 57_000
print("\nALL END-TO-END ASSERTIONS PASSED ✓")
