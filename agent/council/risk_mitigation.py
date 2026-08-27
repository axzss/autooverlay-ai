"""Kill-switch evaluator for the overlay agent.

``evaluate_kill_switch(portfolio_state)`` inspects a live portfolio snapshot
and decides whether trading must halt. Thresholds are configurable via
``StrategyConfig`` fields (with safe defaults if the config lacks them):

- kill_max_drawdown_pct      portfolio peak-to-current drawdown that halts (5%)
- kill_max_single_day_loss_pct  worst one-day portfolio loss (2%)
- kill_consecutive_stop_losses  consecutive stop-loss exits before halt (3)

Pure logic, deterministic, no I/O. Missing inputs are ignored, not guessed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from ..config import StrategyConfig

DEFAULT_MAX_DRAWDOWN_PCT = 5.0
DEFAULT_SINGLE_DAY_LOSS_PCT = 2.0
DEFAULT_CONSEC_STOP_LOSSES = 3


def _cfg_get(config: "StrategyConfig | None", name: str, default: float) -> float:
    if config is None:
        return default
    val = getattr(config, name, default)
    return val if isinstance(val, (int, float)) and not isinstance(val, bool) else default


def evaluate_kill_switch(portfolio_state: dict,
                         config: "StrategyConfig | None" = None,
                         positions: list[dict] | None = None) -> dict:
    """Return ``{"halted": bool, "reasons": list[str]}`` for a portfolio snapshot.

    Recognized keys in ``portfolio_state``:
        equity: float                     current account equity ($)
        initial_equity / peak_equity: float
        prev_equity: float                equity at previous day's close
        consecutive_stop_losses: int

    When ``config.overlay_only_drawdown`` is True, the drawdown calculation
    uses only overlay positions (short-option positions with a collateral or
    market_value field) rather than full NAV.
    """
    max_dd = _cfg_get(config, "kill_max_drawdown_pct", DEFAULT_MAX_DRAWDOWN_PCT)
    max_1d = _cfg_get(config, "kill_max_single_day_loss_pct", DEFAULT_SINGLE_DAY_LOSS_PCT)
    max_stops = int(_cfg_get(config, "kill_consecutive_stop_losses", DEFAULT_CONSEC_STOP_LOSSES))
    overlay_only = bool(_cfg_get(config, "overlay_only_drawdown", True))

    reasons: list[str] = []

    equity = portfolio_state.get("equity")
    peak = portfolio_state.get("peak_equity") or portfolio_state.get("initial_equity")

    # When overlay_only_drawdown is True, compute drawdown from overlay positions only.
    if overlay_only and positions:
        overlay_equity = float(sum(
            float(p.get("collateral", 0) or p.get("market_value", 0) or 0)
            for p in positions
        ))
        if overlay_equity > 0:
            # Use overlay equity as both current and peak (no separate peak yet)
            dd_equity = overlay_equity
            dd_peak = overlay_equity
        else:
            # No overlay collateral detected — fall back to full NAV
            dd_equity = equity
            dd_peak = peak
    else:
        dd_equity = equity
        dd_peak = peak

    if isinstance(dd_equity, (int, float)) and isinstance(dd_peak, (int, float)) and dd_peak > 0:
        dd = (dd_equity / dd_peak - 1) * 100
        if dd <= -max_dd:
            reasons.append(
                f"portfolio drawdown {dd:.2f}% breaches kill threshold -{max_dd:.2f}%")

    prev = portfolio_state.get("prev_equity")
    if (isinstance(equity, (int, float)) and isinstance(prev, (int, float))
            and prev > 0):
        day_loss = (equity / prev - 1) * 100
        if day_loss <= -max_1d:
            reasons.append(
                f"single-day loss {day_loss:.2f}% breaches kill threshold -{max_1d:.2f}%")

    stops = portfolio_state.get("consecutive_stop_losses")
    if isinstance(stops, (int, float)) and not isinstance(stops, bool):
        if stops >= max_stops:
            reasons.append(
                f"{int(stops)} consecutive stop-losses reached (threshold {max_stops})")

    return {"halted": bool(reasons), "reasons": reasons}
