"""
Order Executor - Temporary Implementation
Wraps Alpaca API for order submission/cancellation.
Falls back to mock execution when API unavailable.
"""

from typing import Dict, Optional
import os


class OrderExecutor:
    def __init__(self, api_client=None):
        self.api_client = api_client
        self.paper = True

    def submit_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None
    ) -> Dict:
        """
        Submit order to Alpaca or mock if no client.
        Returns standard Alpaca-like order response.
        """
        if self.api_client:
            return self._submit_real(symbol, qty, side, order_type, time_in_force, limit_price, stop_price)
        return self._submit_mock(symbol, qty, side, order_type, time_in_force, limit_price, stop_price)

    def cancel_order(self, order_id: str) -> Dict:
        if self.api_client:
            try:
                return self.api_client.cancel_order(order_id)
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "cancelled", "order_id": order_id}

    def _submit_real(self, symbol, qty, side, order_type, time_in_force, limit_price, stop_price) -> Dict:
        # Real Alpaca submission
        try:
            order = self.api_client.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type=order_type,
                time_in_force=time_in_force,
                limit_price=limit_price,
                stop_price=stop_price
            )
            return {
                "id": order.id,
                "client_order_id": order.client_order_id,
                "status": order.status,
                "symbol": order.symbol,
                "qty": str(order.qty),
                "side": order.side,
                "type": order.type,
                "filled_at": getattr(order, "filled_at", None)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _submit_mock(self, symbol, qty, side, order_type, time_in_force, limit_price, stop_price) -> Dict:
        import uuid
        from datetime import datetime
        return {
            "id": str(uuid.uuid4()),
            "client_order_id": f"mock_order_{symbol.lower()}_{side}",
            "status": "filled",
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
            "filled_at": datetime.utcnow().isoformat() + "Z",
            "filled_avg_price": limit_price or 0.0
        }
