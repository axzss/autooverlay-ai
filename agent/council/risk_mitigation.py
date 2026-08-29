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

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import for typing only
    from ..config import StrategyConfig

DEFAULT_MAX_DRAWDOWN_PCT = 5.0
DEFAULT_SINGLE_DAY_LOSS_PCT = 2.0
DEFAULT_CONSEC_STOP_LOSSES = 3

# OCC option symbol: root (1-6 alnum) + YYMMDD + C/P + 8-digit strike.
_OCC_RE = re.compile(r"^[A-Z0-9]{1,6}\d{6}[CP]\d{8}$")



def _cfg_get(config: "StrategyConfig | None", name: str, default: float) -> float:
    """Read a NUMERIC config threshold.

    Bools are rejected deliberately: ``True`` is not a meaningful threshold and
    letting it through would silently compare equity against 1. Use
    :func:`_cfg_flag` for boolean config — reusing this helper for a flag makes
    that flag permanently unsettable (finding A2).
    """
    if config is None:
        return default
    val = getattr(config, name, default)
    return val if isinstance(val, (int, float)) and not isinstance(val, bool) else default


def _cfg_flag(config: "StrategyConfig | None", name: str, default: bool) -> bool:
    """Read a BOOLEAN config flag.

    Separate from :func:`_cfg_get` because that helper rejects bools and returns
    its default, which made ``overlay_only_drawdown=False`` impossible to set.
    """
    if config is None:
        return default
    val = getattr(config, name, default)
    return bool(val) if isinstance(val, bool) else default


def _is_short_option(position: dict) -> bool:
    """True when a position is a SHORT OPTION — i.e. actual overlay exposure.

    Long stock is not overlay collateral. The previous implementation summed
    whatever list it was handed, and ``daily_cycle`` hands it the equity book,
    so every live account reported non-zero "overlay equity" (finding A1).

    Detection: OCC-shaped symbol (root + YYMMDD + C/P + 8-digit strike) AND a
    negative quantity. Both are required — a long call is an option but not
    overlay exposure.
    """
    symbol = str(position.get("symbol") or "")
    if not _OCC_RE.match(symbol):
        return False
    qty = position.get("qty")
    if qty is None:
        qty = position.get("quantity")
    try:
        qty_f = float(qty)
    except (TypeError, ValueError):
        # Shape says option but quantity is unreadable. Do not assume short.
        return False
    return qty_f < 0


def _overlay_collateral(positions: list[dict]) -> float:
    """Sum collateral (fallback: |market_value|) across short-option positions."""
    total = 0.0
    for p in positions:
        if not _is_short_option(p):
            continue
        raw = p.get("collateral")
        if raw in (None, 0, 0.0):
            raw = p.get("market_value") or 0
        try:
            total += abs(float(raw))
        except (TypeError, ValueError):
            continue
    return total



def evaluate_kill_switch(portfolio_state: dict,
                         config: "StrategyConfig | None" = None,
                         positions: list[dict] | None = None) -> dict:
    """Return ``{"halted": bool, "reasons": list[str]}`` for a portfolio snapshot.

    Recognized keys in ``portfolio_state``:
        equity: float                     current account equity ($)
        initial_equity / peak_equity: float
        prev_equity: float                equity at previous day's close
        consecutive_stop_losses: int

    When ``config.overlay_only_drawdown`` is True (default) the drawdown is
    measured against overlay exposure only — short-option positions — using
    ``portfolio_state["overlay_peak_equity"]`` as the high-water mark.

    If that peak is absent, drawdown falls back to full NAV and a note is
    recorded in the returned ``notes`` list. An unknown peak must never read as
    "no drawdown": that was finding A, where overlay equity was compared against
    itself and the ratio was always exactly 0.0.
    """
    max_dd = _cfg_get(config, "kill_max_drawdown_pct", DEFAULT_MAX_DRAWDOWN_PCT)
    max_1d = _cfg_get(config, "kill_max_single_day_loss_pct", DEFAULT_SINGLE_DAY_LOSS_PCT)
    max_stops = int(_cfg_get(config, "kill_consecutive_stop_losses", DEFAULT_CONSEC_STOP_LOSSES))
    overlay_only = _cfg_flag(config, "overlay_only_drawdown", True)

    reasons: list[str] = []
    notes: list[str] = []

    equity = portfolio_state.get("equity")
    peak = portfolio_state.get("peak_equity") or portfolio_state.get("initial_equity")

    dd_equity = equity
    dd_peak = peak
    dd_basis = "nav"

    if overlay_only and positions:
        overlay_equity = _overlay_collateral(positions)
        overlay_peak = portfolio_state.get("overlay_peak_equity")
        if overlay_equity > 0 and isinstance(overlay_peak, (int, float)) \
                and not isinstance(overlay_peak, bool) and overlay_peak > 0:
            dd_equity = overlay_equity
            dd_peak = float(overlay_peak)
            dd_basis = "overlay"
        elif overlay_equity > 0:
            # Overlay exposure exists but no high-water mark is available.
            # Fall back to NAV rather than reporting zero drawdown.
            notes.append(
                "overlay exposure present but overlay_peak_equity missing — "
                "drawdown measured against full NAV instead")
        else:
            notes.append(
                "no short-option positions detected — drawdown measured "
                "against full NAV")

    if isinstance(dd_equity, (int, float)) and isinstance(dd_peak, (int, float)) and dd_peak > 0:
        dd = (dd_equity / dd_peak - 1) * 100
        if dd <= -max_dd:
            reasons.append(
                f"{dd_basis} drawdown {dd:.2f}% breaches kill threshold "
                f"-{max_dd:.2f}%")
    else:
        notes.append("drawdown not evaluated — equity or peak unavailable")


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

    return {"halted": bool(reasons), "reasons": reasons, "notes": notes,
            "drawdown_basis": dd_basis}

