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
    """
    try:
        from agent.council.risk_mitigation import evaluate_kill_switch

        equity = _num(account.get("equity")) or 0.0
        state = {
            "equity": equity,
            "peak_equity": max(
                _num(account.get("equity")) or 0.0,
                _num(account.get("last_equity")) or 0.0,
            ) or None,
            "prev_equity": _num(account.get("last_equity")),
        }
        state = {k: v for k, v in state.items() if v is not None}
        verdict = evaluate_kill_switch(
            state, config=config, positions=list(positions) + list(open_options)
        )
        return bool(verdict.get("halted")), list(verdict.get("reasons") or [])
    except Exception as exc:  # noqa: BLE001
        return True, [f"kill-switch could not be evaluated: {type(exc).__name__}: {exc}"]


def _num(value) -> float | None:
    import math

    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None
