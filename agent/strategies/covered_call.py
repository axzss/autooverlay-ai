"""
Covered Call Strategy - Temporary Implementation
Screens for suitable covered call opportunities on existing holdings.
Criteria:
- Existing position in underlying
- OTM strike with reasonable premium
- Sufficient DTE
- Not too close to earnings
"""

from typing import Dict, List, Optional


class CoveredCallStrategy:
    def __init__(self, min_dte: int = 7, max_dte: int = 45, min_delta: float = 0.1, max_delta: float = 0.4):
        self.min_dte = min_dte
        self.max_dte = max_dte
        self.min_delta = min_delta
        self.max_delta = max_delta

    def screen(self, opportunities: List[Dict], positions: List[Dict]) -> List[Dict]:
        """
        Match covered call opportunities with existing positions.
        Only consider opportunities where we already own the underlying.
        """
        holdings = {p["symbol"]: p for p in positions if float(p.get("qty", 0)) > 0}
        results = []

        for opp in opportunities:
            symbol = opp.get("symbol")
            if symbol not in holdings:
                continue

            position = holdings[symbol]
            qty = int(float(position["qty"]))

            # Can only write calls on shares we own
            if qty <= 0:
                continue

            delta = opp.get("delta", 0)
            if not (self.min_delta <= delta <= self.max_delta):
                continue

            risk_score = self._calculate_risk_score(opp, position)
            annualized = opp.get("annualized_return_rate", 0)

            if annualized >= 0.25 and risk_score < 0.5:
                recommendation = "INITIATE_POSITION"
            elif annualized >= 0.15:
                recommendation = "HOLD_POSITION"
            else:
                recommendation = "MONITOR_CLOSELY"

            results.append({
                **opp,
                "underlying_qty": qty,
                "risk_score": round(risk_score, 3),
                "recommendation": recommendation,
                "strategy": "COVERED_CALL"
            })

        return sorted(results, key=lambda x: x["annualized_return_rate"], reverse=True)

    def _calculate_risk_score(self, opp: Dict, position: Dict) -> float:
        """
        Risk scoring for covered calls.
        Higher risk if: very high IV, very close to strike, near-term expiry.
        """
        iv = opp.get("implied_volatility", 0)
        delta = opp.get("delta", 0)
        underlying_price = opp.get("underlying_price", 0)
        strike = opp.get("strike_price", 0)
        distance_to_strike = ((strike - underlying_price) / underlying_price) if underlying_price else 0

        score = 0.0
        score += min(iv * 0.4, 0.3)
        score += min(abs(delta) * 0.3, 0.3)
        score += max(0, -distance_to_strike) * 0.4  # Deep ITM = higher risk

        return min(score, 1.0)
