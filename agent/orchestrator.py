"""
Agent Runtime / Orchestrator - Temporary Implementation
Main loop that:
- Fetches portfolio state
- Pulls option chain / opportunities
- Runs decision engine
- Produces actionable recommendations
"""

from typing import Dict, List, Optional
from datetime import datetime

from agent.strategies.cash_secured_put import CashSecuredPutStrategy
from agent.strategies.covered_call import CoveredCallStrategy
from agent.decision_engine import DecisionEngine
from agent.order_executor import OrderExecutor


class AgentRuntime:
    def __init__(self, account_cash: float = 100000.0):
        self.csp = CashSecuredPutStrategy()
        self.cc = CoveredCallStrategy()
        self.decision_engine = DecisionEngine(account_cash=account_cash)
        self.order_executor = OrderExecutor()
        self.last_run_at: Optional[str] = None
        self.run_history: List[Dict] = []

    def run_once(self, context: Dict) -> Dict:
        """
        Execute one decision cycle.
        Expected context keys:
        - account_info
        - positions
        - csp_opportunities
        - cc_opportunities
        - market_data (optional)
        """
        account_info = context.get("account_info", {})
        positions = context.get("positions", [])
        csp_opps = context.get("csp_opportunities", [])
        cc_opps = context.get("cc_opportunities", [])
        market_data = context.get("market_data", {})

        # Update executor with real client if available
        if context.get("alpaca_client"):
            self.order_executor = OrderExecutor(api_client=context["alpaca_client"])

        decision = self.decision_engine.evaluate(
            csp_opportunities=csp_opps,
            cc_opportunities=cc_opps,
            positions=positions,
            market_data=market_data
        )

        # Optionally auto-execute safe actions
        executed_orders = []
        if context.get("auto_execute", False):
            for action in decision["actions"]:
                result = self.order_executor.submit_order(
                    symbol=action["symbol"],
                    qty=action["qty"],
                    side=action["action"],
                    order_type="market",
                    time_in_force="day"
                )
                executed_orders.append(result)

        run_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "decision": decision,
            "executed_orders": executed_orders
        }
        self.run_history.append(run_record)
        self.last_run_at = run_record["timestamp"]

        return run_record

    def get_status(self) -> Dict:
        return {
            "last_run_at": self.last_run_at,
            "runs": len(self.run_history),
            "recent_actions": [
                r["decision"]["actions"] for r in self.run_history[-5:]
            ]
        }
