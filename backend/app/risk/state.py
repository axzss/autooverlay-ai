"""Portfolio state fetching for the risk gate.

Kept separate from `gate.py` so the gate stays a pure function. Every failure
here produces ``PortfolioSnapshot(available=False, ...)`` rather than raising:
the gate's fail-closed rule then refuses the order, which is the intended
behaviour when broker state cannot be read.
"""

from __future__ import annotations

from .models import PortfolioSnapshot


def fetch_snapshot(config=None) -> PortfolioSnapshot:
    """Read account, positions and kill-switch state.

    In mock mode the bundled fixtures are used and ``mode`` says ``mock`` — the
    gate still runs every check, because a demo that skips the gate proves
    nothing about the gate.
    """
    from ..alpaca_client import (
        AlpacaClient,
        is_configured,
        normalize_option_position,
    )
    from ..mock_data import mock_account, mock_positions

    if is_configured():
        try:
            client = AlpacaClient()
            raw_positions = client.get_positions()
            account = client.get_account() or {}
            mode = "live"
        except Exception as exc:  # noqa: BLE001 - any failure must fail closed
            return PortfolioSnapshot(
                available=False,
                fetch_error=f"{type(exc).__name__}: {exc}",
                mode="live",
            )
    else:
        account = mock_account()
        raw_positions = mock_positions()
        mode = "mock"

    equity_positions = [
        p for p in raw_positions
        if isinstance(p, dict) and p.get("asset_class") != "us_option"
    ]
    open_options = [
        normalized for normalized in (
            normalize_option_position(p)
            for p in raw_positions if isinstance(p, dict)
        )
        if normalized is not None and normalized["qty"] < 0
    ]

    equity = _num(account.get("equity")) or _num(account.get("portfolio_value"))
    cash = _num(account.get("cash"))
    if cash is None:
        cash = _num(account.get("buying_power"))

    halted, halt_reasons = _kill_switch_state(
        equity_positions, open_options, cash, account, config
    )

    return PortfolioSnapshot(
        available=True,
        equity=equity,
        cash=cash,
        positions=equity_positions,
        open_option_positions=open_options,
        halted=halted,
        halt_reasons=halt_reasons,
        mode=mode,
    )


def _kill_switch_state(
    positions: list[dict],
    open_options: list[dict],
    cash: float | None,
    account: dict,
    config,
) -> tuple[bool, list[str]]:
    """Ask the agent layer's kill-switch, not a reimplementation of it.

    Two copies of a halt rule drift, and the copy in the execution path is the
    one that matters. A failure to evaluate is reported as halted: the gate must
    not treat "the kill-switch is unreadable" as "the kill-switch is clear".

    The high-water mark comes from ``agent/state/peak.py``, not from the account
    snapshot. Alpaca exposes ``equity`` and ``last_equity`` — today and
    yesterday — and neither is a peak. The previous ``max(equity, last_equity)``
    was a two-day window that a slow decline walked straight through: a book
    down 72% from a peak set weeks ago reported ``halted=False`` because
    yesterday's close was also 55k. Measured, before this change:

        equity 55000, last_equity 55100  -> halted=False, reasons=[]
        equity 55000, last_equity 200000 -> halted=True

    Same book, opposite verdict, decided by which day the peak happened to fall
    on. The store remembers maxima across cycles, so the first case now halts.
    """
    try:
        from agent.council.risk_mitigation import evaluate_kill_switch

        equity = _num(account.get("equity")) or 0.0
        prev_equity = _num(account.get("last_equity"))
        overlay_collateral = _overlay_collateral_for(list(positions) + list(open_options))

        peak, overlay_peak, peak_source = _peak_marks(
            equity, prev_equity, overlay_collateral,
            account_id=str(account.get("account_id") or "default"),
        )


        state = {
            "equity": equity,
            "peak_equity": peak,
            "prev_equity": prev_equity,
            "overlay_peak_equity": overlay_peak,
        }
        state = {k: v for k, v in state.items() if v is not None}
        verdict = evaluate_kill_switch(
            state, config=config, positions=list(positions) + list(open_options)
        )
        reasons = list(verdict.get("reasons") or [])
        # Surface provenance. "no drawdown" and "no high-water mark" are
        # different states, and a gate that reports them identically is the
        # defect this whole module exists to prevent. Notes are appended as
        # `note: ...` entries so they reach halt_reasons without being mistaken
        # for breaches — a reader can filter on the prefix.
        notes = list(verdict.get("notes") or [])
        if peak_source in ("seeded", "absent"):
            notes.append(
                f"high-water mark {peak_source} — drawdown measured against the "
                "first observation, not a tracked peak"
            )
        if reasons:
            reasons.extend(f"note: {note}" for note in notes)
        return bool(verdict.get("halted")), reasons

    except Exception as exc:  # noqa: BLE001
        return True, [f"kill-switch could not be evaluated: {type(exc).__name__}: {exc}"]


def _peak_marks(
    equity: float,
    prev_equity: float | None,
    overlay_collateral: float,
    account_id: str = "default",
) -> tuple[float | None, float | None, str]:
    """Return ``(nav_peak, overlay_peak, source)`` from the persistent store.

    Marks are keyed by account so two accounts never share a high-water mark.
    Degrades to ``max(equity, prev_equity)`` when the store cannot be imported
    or written, reporting ``source="absent"`` so the caller knows the mark is a
    two-day window rather than a tracked high.
    """
    try:
        from agent.state import PeakStore

        store = PeakStore()
        # Fold yesterday's close in first: it is a real observation, and a peak
        # the store has never seen must not be discarded just because it arrived
        # in `last_equity` rather than `equity`.
        if prev_equity is not None:
            store.observe(prev_equity, None, account_id=account_id)
        record = store.observe(equity, overlay_collateral or None, account_id=account_id)
        return record.nav_peak, record.overlay_peak, record.source
    except Exception:  # noqa: BLE001
        fallback = max(equity, prev_equity or 0.0) or None
        return fallback, None, "absent"



def _overlay_collateral_for(positions: list[dict]) -> float:
    """Overlay collateral via the agent layer's shared short-option rule."""
    try:
        from agent.council.risk_mitigation import _overlay_collateral

        return _overlay_collateral(positions)
    except Exception:  # noqa: BLE001
        return 0.0



def _num(value) -> float | None:
    import math

    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None
