"""Pre-trade risk gate.

`POST /api/trade` previously validated syntax only — NaN, magnitude, OCC format,
TIF — and would happily accept 500 naked short calls on a symbol the portfolio
did not hold (docs/BRIEF-BACKEND-V2.md D4).

The agent layer enforces "never naked" in its own reasoning. That is decoration
if the execution surface bypasses the agent entirely, which this endpoint does.
This package is where the rule is actually enforced.
"""

from .models import CheckResult, PortfolioSnapshot, RiskDecision, TradeIntent
from .gate import evaluate_trade
from .state import fetch_snapshot

__all__ = [
    "CheckResult",
    "PortfolioSnapshot",
    "RiskDecision",
    "TradeIntent",
    "evaluate_trade",
    "fetch_snapshot",
]
