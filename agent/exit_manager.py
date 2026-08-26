"""
Exit Manager.

Evaluates open overlay positions (short calls / short puts) against
mechanical exit rules and returns structured exit actions with rationale
strings and step-by-step reasoning traces.

Rules (checked in priority order — first trigger wins):
- TAKE_PROFIT : >= 60% of the initial premium has been captured
                (current premium <= 40% of initial).
- STOP_LOSS   : loss >= 2x the initial premium received (200% rule),
                i.e. current premium >= 3x initial.
- ROLL        : |delta| breaches 0.40 OR DTE < 7 days (and no profit/stop
                triggered first).
- HOLD        : no exit condition met.

Pure logic, deterministic, no I/O.
"""

from typing import Dict, List, Optional
from datetime import datetime

try:
    from .config import StrategyConfig
except ImportError:  # pragma: no cover - direct-script imports
    from config import StrategyConfig

TAKE_PROFIT_CAPTURE_PCT = 0.60   # close when >=60% of premium is captured
STOP_LOSS_MULTIPLE = 2.0         # stop at a loss of 2x initial premium
ROLL_DELTA_THRESHOLD = 0.40      # roll when |delta| > 0.40
ROLL_DTE_THRESHOLD = 7           # roll when DTE < 7

VALID_EXIT_ACTIONS = ("TAKE_PROFIT", "STOP_LOSS", "ROLL", "HOLD")


def _dte_of(position: Dict) -> Optional[int]:
    dte = position.get("days_to_expiry") or position.get("dte")
    if dte is not None:
        try:
            return int(dte)
        except (TypeError, ValueError):
            return None
    exp = position.get("expiration_date")
    if not exp:
        return None
    try:
        expiry = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        return (expiry.replace(tzinfo=None)
                - datetime.utcnow()).days
    except ValueError:
        return None


class ExitManager:
    """Evaluate short-option overlay positions for exit conditions."""

    def __init__(
        self,
        take_profit_capture_pct: Optional[float] = None,
        stop_loss_multiple: Optional[float] = None,
        roll_delta_threshold: Optional[float] = None,
        roll_dte_threshold: Optional[int] = None,
        config: Optional[StrategyConfig] = None,
    ):
        cfg = config or StrategyConfig()
        tp = take_profit_capture_pct if take_profit_capture_pct is not None \
            else cfg.take_profit_pct
        sl = stop_loss_multiple if stop_loss_multiple is not None \
            else cfg.stop_loss_mult
        rd = roll_delta_threshold if roll_delta_threshold is not None \
            else cfg.roll_delta
        rdt = roll_dte_threshold if roll_dte_threshold is not None \
            else cfg.roll_min_dte
        self.take_profit_capture_pct = float(tp)
        self.stop_loss_multiple = float(sl)
        self.roll_delta_threshold = float(rd)
        self.roll_dte_threshold = int(rdt)

    def evaluate_position(self, position: Dict,
                          as_of: Optional[datetime] = None) -> Dict:
        """
        Evaluate one open short option position.

        Recognized position keys:
            symbol, strategy ("COVERED_CALL"|"CASH_SECURED_PUT" or
            "SHORT_CALL"|"SHORT_PUT"), contracts, strike_price,
            expiration_date / days_to_expiry / dte,
            initial_premium (per share, $ received when sold),
            current_premium (per share, $ to buy back now), delta.
        """
        symbol = position.get("symbol", "?")
        initial = float(position.get("initial_premium") or 0)
        current = float(position.get("current_premium") or 0)
        delta = abs(float(position.get("delta") or 0))
        dte = _dte_of(position)

        trace: List[str] = []
        action = "HOLD"
        reason_parts: List[str] = []
        rule = None

        if initial <= 0:
            trace.append(f"initial premium ${initial:.2f} invalid — cannot "
                         "evaluate P&L rules ✗")
            pnl_capture_pct = None
            loss_multiple = None
        else:
            pnl_per_share = initial - current          # captured profit
            pnl_capture_pct = max(0.0, pnl_per_share / initial)
            loss_multiple = (current - initial) / initial if current > initial else 0.0
            trace.append(
                f"P&L check: sold @ ${initial:.2f}, buyback now ${current:.2f} → "
                f"{pnl_capture_pct*100:.0f}% of premium captured ✓"
            )

            if pnl_capture_pct >= self.take_profit_capture_pct:
                action = "TAKE_PROFIT"
                rule = f"profit-taking ≥{int(self.take_profit_capture_pct*100)}% captured"
                reason_parts.append(
                    f"{pnl_capture_pct*100:.0f}% of premium captured "
                    f"(≥ {int(self.take_profit_capture_pct*100)}% target)")
                trace.append(
                    f"profit target hit: {pnl_capture_pct*100:.0f}% ≥ "
                    f"{self.take_profit_capture_pct*100:.0f}% → TAKE_PROFIT ✓")
            elif loss_multiple >= self.stop_loss_multiple:
                action = "STOP_LOSS"
                rule = f"200% rule: loss ≥ {int(self.stop_loss_multiple)}x premium"
                reason_parts.append(
                    f"loss is {loss_multiple:.1f}x initial premium "
                    f"(≥ {int(self.stop_loss_multiple)}x limit)")
                trace.append(
                    f"stop-loss hit: adverse move {loss_multiple:.2f}x ≥ "
                    f"{self.stop_loss_multiple:.2f}x initial premium → STOP_LOSS ✓")

        if action == "HOLD":
            # Delta rule
            if delta > self.roll_delta_threshold:
                action = "ROLL"
                rule = f"|delta| {delta:.2f} breached {self.roll_delta_threshold:.2f}"
                reason_parts.append(rule)
                trace.append(
                    f"delta check: |delta| {delta:.2f} > "
                    f"{self.roll_delta_threshold:.2f} → ROLL ✓")
            elif delta > 0:
                trace.append(
                    f"delta check: |delta| {delta:.2f} within ≤ "
                    f"{self.roll_delta_threshold:.2f} band ✓")
            # DTE rule
            if dte is not None:
                if dte < self.roll_dte_threshold:
                    if action == "HOLD":
                        action = "ROLL"
                        rule = (f"DTE {dte} < {self.roll_dte_threshold} "
                                "(gamma/assignment risk window)")
                    else:
                        reason_parts.append(f"DTE {dte} also < {self.roll_dte_threshold}")
                    trace.append(
                        f"DTE check: {dte} days < {self.roll_dte_threshold} → "
                        "roll window ✓")
                else:
                    trace.append(
                        f"DTE check: {dte} days ≥ {self.roll_dte_threshold} ✓")
            else:
                trace.append("DTE check: no expiry data available ✗")

        if action == "HOLD":
            reason_parts.append(
                "no exit condition met; continue collecting premium")
            trace.append("no rule triggered → HOLD ✓")

        strategy = position.get("strategy") or (
            "SHORT_CALL" if "C" in str(position.get("option_symbol", ""))[-9:-8]
            else "SHORT_OPTION")
        rationale = (
            f"{symbol} short {strategy}: {action} — "
            + "; ".join(reason_parts)
            + ".")
        if action == "ROLL":
            rationale += (" Roll to next expiration / further-OTM strike to "
                          "reset deltas and harvest more time decay.")

        exit_action = {
            "type": "EXIT_MANAGEMENT",
            "strategy": strategy,
            "symbol": symbol,
            "option_symbol": position.get("option_symbol"),
            "contracts": int(float(position.get("contracts") or 0)),
            "strike_price": position.get("strike_price"),
            "expiration_date": position.get("expiration_date"),
            "action": action,
            "order_side": ("BUY_TO_CLOSE" if action in
                           ("TAKE_PROFIT", "STOP_LOSS") else
                           None),
            "rule_triggered": rule,
            "premium_captured_pct": (round(pnl_capture_pct, 4)
                                     if pnl_capture_pct is not None else None),
            "current_loss_multiple": (round(loss_multiple, 4)
                                      if loss_multiple is not None else None),
            "delta": round(delta, 3) if position.get("delta") is not None else None,
            "dte": dte,
            "rationale": rationale,
            "reasoning_trace": trace,
        }
        return exit_action

    def evaluate_positions(self, positions: List[Dict],
                           as_of: Optional[datetime] = None) -> List[Dict]:
        """Evaluate every open overlay position; returns one dict each."""
        return [self.evaluate_position(p, as_of=as_of) for p in positions]
