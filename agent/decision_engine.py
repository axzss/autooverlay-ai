"""
Decision Engine - Temporary Implementation
Aggregates strategy outputs and produces unified trading recommendations.
"""

from typing import Dict, List, Optional
from .strategies.cash_secured_put import CashSecuredPutStrategy
from .strategies.covered_call import CoveredCallStrategy


class DecisionEngine:
    def __init__(self, account_cash: float = 100000.0):
        self.csp = CashSecuredPutStrategy()
        self.cc = CoveredCallStrategy()
        self.account_cash = account_cash

    def evaluate(
        self,
        csp_opportunities: List[Dict],
        cc_opportunities: List[Dict],
        positions: List[Dict],
        market_data: Optional[Dict] = None
    ) -> Dict:
        """
        Run all strategies and produce a unified decision.
        Returns a summary dict with:
        - csp_results
        - cc_results
        - actions: list of recommended actions
        - portfolio_health: risk summary
        """
        csp_results = self.csp.screen(csp_opportunities, self.account_cash)
        cc_results = self.cc.screen(cc_opportunities, positions)

        actions = []
        for r in csp_results:
            if r["recommendation"] == "INITIATE_POSITION":
                actions.append({
                    "type": "CASH_SECURED_PUT",
                    "symbol": r["symbol"],
                    "action": "SELL_TO_OPEN",
                    "qty": 1,
                    "reasoning": r.get("reasoning", ""),
                    "risk_score": r["risk_score"],
                    "premium": r.get("last_price", 0)
                })

        for r in cc_results:
            if r["recommendation"] == "INITIATE_POSITION":
                actions.append({
                    "type": "COVERED_CALL",
                    "symbol": r["symbol"],
                    "action": "SELL_TO_OPEN",
                    "qty": 1,
                    "reasoning": r.get("reasoning", ""),
                    "risk_score": r["risk_score"],
                    "premium": r.get("last_price", 0)
                })

        portfolio_health = self._assess_portfolio_health(positions, csp_results + cc_results)

        return {
            "csp_results": csp_results,
            "cc_results": cc_results,
            "actions": actions,
            "portfolio_health": portfolio_health,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z"
        }

    def _assess_portfolio_health(self, positions: List[Dict], opportunities: List[Dict]) -> Dict:
        total_positions = len(positions)
        actionable = len([o for o in opportunities if o["recommendation"] == "INITIATE_POSITION"])
        avg_risk = sum(o["risk_score"] for o in opportunities) / max(len(opportunities), 1)

        return {
            "total_positions": total_positions,
            "actionable_opportunities": actionable,
            "average_risk_score": round(avg_risk, 3),
            "health": "HEALTHY" if avg_risk < 0.5 else "ELEVATED_RISK"
        }
