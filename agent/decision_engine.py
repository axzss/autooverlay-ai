"""
Decision Engine.

Aggregates covered-call and cash-secured-put screening results into a unified
recommendation set. Every recommendation carries:
- an explicit action label: INITIATE_POSITION | HOLD_POSITION | MONITOR_CLOSELY
- an explicit integer risk score 0-100
- a written rationale string

Pure logic over the strategy outputs + positions; no I/O, deterministic.
"""

from typing import Dict, List, Optional
from .strategies.cash_secured_put import CashSecuredPutStrategy
from .strategies.covered_call import CoveredCallStrategy
from .exit_manager import ExitManager
from .portfolio_analyst import PortfolioAnalyst
from .config import StrategyConfig

VALID_ACTIONS = ("INITIATE_POSITION", "HOLD_POSITION", "MONITOR_CLOSELY")


class DecisionEngine:
    def __init__(self, account_cash: float = 100000.0,
                 portfolio_value: Optional[float] = None,
                 config: Optional[StrategyConfig] = None):
        self.config = config or StrategyConfig()
        self.csp = CashSecuredPutStrategy(config=self.config)
        self.cc = CoveredCallStrategy(config=self.config)
        self.account_cash = account_cash
        self.portfolio_value = (portfolio_value if portfolio_value is not None
                                else account_cash)
        self.exit_manager = ExitManager(config=self.config)
        self.portfolio_analyst = PortfolioAnalyst(config=self.config)

    def evaluate(
        self,
        csp_opportunities: List[Dict],
        cc_opportunities: List[Dict],
        positions: List[Dict],
        market_data: Optional[Dict] = None,
        open_option_positions: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Run both strategies and produce a unified decision dict with
        csp_results, cc_results, actions (INITIATE_POSITION only),
        exit_actions, and portfolio_health.

        open_option_positions: optional list of open short-option overlay
        positions (short calls / short puts) evaluated by the ExitManager.
        """
        csp_results = self.csp.screen(csp_opportunities, self.account_cash,
                                      positions=positions)
        cc_results = self.cc.screen(cc_opportunities, positions)

        actions = []
        for r in csp_results + cc_results:
            if r["recommendation"] == "INITIATE_POSITION":
                actions.append({
                    "type": r["strategy"],
                    "symbol": r["symbol"],
                    "option_symbol": r.get("option_symbol"),
                    "action": "SELL_TO_OPEN",
                    "contracts": r["contracts"],
                    "qty": r["contracts"],  # back-compat for orchestrator
                    "strike_price": r.get("strike_price"),
                    "expiration_date": r.get("expiration_date"),
                    "annualized_premium_yield": r["annualized_premium_yield"],
                    "risk_score": r["risk_score"],
                    "rationale": r["rationale"],
                    "reasoning": r["rationale"],  # back-compat key
                    "reasoning_trace": r.get("reasoning_trace", []),
                    "premium_per_share": r.get("premium_per_share"),
                })

        # Exit management for open short-option overlays.
        exit_actions = self.exit_manager.evaluate_positions(
            open_option_positions or [])

        # Portfolio context: concentration, sectors, cash reserve.
        portfolio_context = self.portfolio_analyst.assess(
            positions, self.portfolio_value, self.account_cash)

        # Global ranking of every screened candidate (both strategies merged),
        # by annualized yield desc — useful for the caller's prioritization.
        ranked = sorted(
            csp_results + cc_results,
            key=lambda r: r["annualized_premium_yield"],
            reverse=True,
        )

        return {
            "csp_results": csp_results,
            "cc_results": cc_results,
            "ranked_recommendations": ranked,
            "actions": actions,
            "exit_actions": exit_actions,
            "portfolio_context": portfolio_context,
            "portfolio_health": self._assess_portfolio_health(positions, ranked),
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        }

    def _assess_portfolio_health(self, positions: List[Dict],
                                 opportunities: List[Dict]) -> Dict:
        n = len(opportunities)
        avg_risk = (sum(o["risk_score"] for o in opportunities) / n) if n else 0.0
        actionable = sum(1 for o in opportunities if o["recommendation"] == "INITIATE_POSITION")

        # Concentration: fraction of holdings eligible for covered calls (>=1 lot).
        lots_ok = 0
        for p in positions:
            if int(float(p.get("qty", 0))) // 100 >= 1:
                lots_ok += 1
        lot_coverage = (lots_ok / len(positions)) if positions else 0.0

        health = "HEALTHY" if avg_risk <= 50 else (
            "ELEVATED_RISK" if avg_risk <= 70 else "HIGH_RISK")

        return {
            "total_positions": len(positions),
            "positions_with_full_lots": lots_ok,
            "lot_coverage_ratio": round(lot_coverage, 2),
            "screened_opportunities": n,
            "actionable_opportunities": actionable,
            "average_risk_score_0_100": round(avg_risk, 1),
            "health": health,
        }
