"""The pre-trade risk gate itself.

`evaluate_trade(intent, snapshot, config)` is a pure function: same inputs, same
decision, no I/O. Fetching portfolio state is the caller's job (see
`backend/app/risk/state.py`), which keeps every check trivially testable and
means the gate can be reused by a batch endpoint later without change.

Check order is deliberate: cheap local checks first, and the two that can halt
everything (kill-switch, state availability) before anything else.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from .models import (
    CONTRACT_MULTIPLIER,
    CheckResult,
    PortfolioSnapshot,
    RiskDecision,
    TradeIntent,
)


def evaluate_trade(
    intent: TradeIntent,
    snapshot: PortfolioSnapshot,
    config=None,
    *,
    today: date | None = None,
    quote_price: float | None = None,
) -> RiskDecision:
    """Evaluate one order against portfolio state and strategy config.

    ``quote_price`` is the current mid/last of the contract when the caller has
    it; when None the price-sanity check reports itself as not evaluated rather
    than passing silently.
    """
    ref_day = today or datetime.now(timezone.utc).date()
    checks: list[CheckResult] = []

    checks.append(_check_state_available(snapshot))
    checks.append(_check_kill_switch(snapshot))
    checks.append(_check_contract_sanity(intent, ref_day, config))
    checks.append(_check_coverage(intent, snapshot))
    checks.append(_check_collateral(intent, snapshot, config))
    checks.append(_check_concentration(intent, snapshot, config))
    checks.append(_check_duplicate(intent, snapshot))
    checks.append(_check_price_sanity(intent, quote_price))
    checks.append(_check_provenance(intent))

    blocking = [c for c in checks if not c.passed and c.severity == "BLOCK"]

    # An override can clear ordinary blocks but never these two. A trade placed
    # while the kill-switch is engaged, or against a portfolio nobody can read,
    # is exactly the trade the gate exists to stop.
    unoverridable = {"kill_switch", "state_available"}
    override_eligible = intent.manual_override and bool(intent.override_reason)
    hard_blocked = [c for c in blocking if c.name in unoverridable]

    if hard_blocked:
        allowed = False
        override_applied = False
    elif blocking and override_eligible:
        allowed = True
        override_applied = True
        checks.append(CheckResult(
            name="manual_override",
            passed=True,
            severity="WARN",
            detail=(
                f"manual override applied over {len(blocking)} blocking check(s): "
                f"{intent.override_reason}"
            ),
            values={
                "overridden": [c.name for c in blocking],
                "reason": intent.override_reason,
            },
        ))
    else:
        allowed = not blocking
        override_applied = False

    return RiskDecision(
        allowed=allowed,
        checks=checks,
        evaluated_at=RiskDecision.now(),
        snapshot_hash=snapshot.hash(),
        mode=snapshot.mode,
        override_applied=override_applied,
    )


# --- individual checks ----------------------------------------------------


def _check_state_available(snapshot: PortfolioSnapshot) -> CheckResult:
    """Fail closed when portfolio state could not be read."""
    if snapshot.available:
        return CheckResult(
            name="state_available",
            passed=True,
            severity="INFO",
            detail=f"portfolio state read ({snapshot.mode} mode)",
            values={"mode": snapshot.mode, "equity": snapshot.equity},
        )
    return CheckResult(
        name="state_available",
        passed=False,
        severity="BLOCK",
        detail=(
            "portfolio state unavailable — refusing the order rather than "
            f"assuming it is safe ({snapshot.fetch_error or 'no detail'})"
        ),
        values={"fetch_error": snapshot.fetch_error},
    )


def _check_kill_switch(snapshot: PortfolioSnapshot) -> CheckResult:
    if not snapshot.halted:
        return CheckResult(
            name="kill_switch",
            passed=True,
            severity="INFO",
            detail="kill-switch not engaged",
            values={},
        )
    return CheckResult(
        name="kill_switch",
        passed=False,
        severity="BLOCK",
        detail="kill-switch engaged: " + "; ".join(snapshot.halt_reasons or ["no reason given"]),
        values={"halt_reasons": list(snapshot.halt_reasons)},
    )


def _check_contract_sanity(
    intent: TradeIntent, today: date, config
) -> CheckResult:
    if not intent.is_option:
        return CheckResult(
            name="contract_sanity",
            passed=True,
            severity="INFO",
            detail=f"{intent.symbol} is an equity order — no contract checks apply",
            values={"is_option": False},
        )

    expiration = intent.expiration
    assert expiration is not None  # is_option implies a parsed OCC symbol
    dte = (expiration - today).days
    values = {
        "option_symbol": intent.symbol,
        "expiration": expiration.isoformat(),
        "dte": dte,
    }

    if dte < 0:
        return CheckResult(
            name="contract_sanity",
            passed=False,
            severity="BLOCK",
            detail=f"contract expired {abs(dte)} day(s) ago ({expiration.isoformat()})",
            values=values,
        )
    if dte == 0:
        return CheckResult(
            name="contract_sanity",
            passed=False,
            severity="BLOCK",
            detail=(
                f"contract expires today ({expiration.isoformat()}) — an overlay "
                "cannot be established on a contract with no time left"
            ),
            values=values,
        )

    # Config DTE band is an entry-screening preference, not a safety property:
    # closing or rolling an existing position legitimately falls outside it.
    dte_min = _cfg(config, "dte_min", None)
    dte_max = _cfg(config, "dte_max", None)
    values.update({"dte_min": dte_min, "dte_max": dte_max})
    if intent.opens_short_option and dte_min is not None and dte_max is not None:
        if not (dte_min <= dte <= dte_max):
            return CheckResult(
                name="contract_sanity",
                passed=False,
                severity="WARN",
                detail=(
                    f"DTE {dte} outside the configured entry band "
                    f"{int(dte_min)}-{int(dte_max)}"
                ),
                values=values,
            )

    return CheckResult(
        name="contract_sanity",
        passed=True,
        severity="INFO",
        detail=f"contract expires in {dte} day(s) ({expiration.isoformat()})",
        values=values,
    )


def _check_coverage(intent: TradeIntent, snapshot: PortfolioSnapshot) -> CheckResult:
    """Never naked: a short call must be backed by shares, per contract.

    Existing short calls on the same underlying consume the shares that back
    them — otherwise two orders could each claim the same 100 shares.
    """
    if not (intent.opens_short_option and intent.option_type == "call"):
        return CheckResult(
            name="coverage",
            passed=True,
            severity="INFO",
            detail="not a short call — share coverage does not apply",
            values={"applies": False},
        )

    underlying = intent.underlying
    shares = snapshot.shares_held(underlying)
    already_short = snapshot.short_calls_on(underlying)
    required_shares = (intent.contracts + already_short) * CONTRACT_MULTIPLIER
    values = {
        "underlying": underlying,
        "shares_held": shares,
        "contracts_requested": intent.contracts,
        "contracts_already_short": already_short,
        "shares_required": required_shares,
    }

    if shares >= required_shares:
        return CheckResult(
            name="coverage",
            passed=True,
            severity="INFO",
            detail=(
                f"{shares:g} shares of {underlying} cover {intent.contracts} new "
                f"+ {already_short} existing short call(s) (need {required_shares})"
            ),
            values=values,
        )

    return CheckResult(
        name="coverage",
        passed=False,
        severity="BLOCK",
        detail=(
            f"NAKED CALL: {intent.contracts} short call(s) on {underlying} need "
            f"{required_shares} shares ({already_short} contract(s) already short); "
            f"portfolio holds {shares:g}"
        ),
        values=values,
    )


def _check_collateral(
    intent: TradeIntent, snapshot: PortfolioSnapshot, config
) -> CheckResult:
    """A short put must be cash-secured, respecting the cash-reserve floor."""
    if not (intent.opens_short_option and intent.option_type == "put"):
        return CheckResult(
            name="collateral",
            passed=True,
            severity="INFO",
            detail="not a short put — cash collateral does not apply",
            values={"applies": False},
        )

    strike = intent.strike or 0.0
    required = strike * CONTRACT_MULTIPLIER * intent.contracts
    cash = snapshot.cash
    reserve_pct = _cfg(config, "min_cash_reserve_pct", 0.0) or 0.0
    equity = snapshot.equity or 0.0
    reserve = equity * (reserve_pct / 100.0)
    values = {
        "underlying": intent.underlying,
        "strike": strike,
        "contracts": intent.contracts,
        "collateral_required": round(required, 2),
        "cash": cash,
        "min_cash_reserve_pct": reserve_pct,
        "cash_reserve_floor": round(reserve, 2),
    }

    if cash is None:
        return CheckResult(
            name="collateral",
            passed=False,
            severity="BLOCK",
            detail="cash balance unknown — cannot verify the put is cash-secured",
            values=values,
        )

    usable = cash - reserve
    values["cash_available_after_reserve"] = round(usable, 2)
    if usable >= required:
        return CheckResult(
            name="collateral",
            passed=True,
            severity="INFO",
            detail=(
                f"${usable:,.2f} available after the {reserve_pct:g}% reserve covers "
                f"${required:,.2f} of put collateral"
            ),
            values=values,
        )

    return CheckResult(
        name="collateral",
        passed=False,
        severity="BLOCK",
        detail=(
            f"UNSECURED PUT: {intent.contracts} short put(s) at ${strike:,.2f} require "
            f"${required:,.2f} collateral; ${usable:,.2f} available after the "
            f"{reserve_pct:g}% cash reserve"
        ),
        values=values,
    )


def _check_concentration(
    intent: TradeIntent, snapshot: PortfolioSnapshot, config
) -> CheckResult:
    """Per-ticker concentration cap on the exposure this order would add.

    A covered call adds **no** new exposure: the shares backing it are already
    counted in the position's market value, and writing the call caps upside
    rather than committing more capital. Counting the strike notional again
    double-counts the same holding and would block every legitimate covered
    call on a normally-sized position.

    A cash-secured put does commit new capital — the collateral — so that is
    what gets added.
    """
    if not intent.opens_short_option:
        return CheckResult(
            name="concentration",
            passed=True,
            severity="INFO",
            detail="order does not open short option exposure",
            values={"applies": False},
        )

    limit_pct = _cfg(config, "max_concentration_pct", None)
    equity = snapshot.equity
    if limit_pct is None or not equity:
        return CheckResult(
            name="concentration",
            passed=True,
            severity="WARN",
            detail="concentration not evaluated — equity or limit unavailable",
            values={"max_concentration_pct": limit_pct, "equity": equity},
        )

    strike = intent.strike or 0.0
    if intent.option_type == "put":
        added = strike * CONTRACT_MULTIPLIER * intent.contracts
        basis = "cash collateral committed by the short put"
    else:
        added = 0.0
        basis = "covered call — shares already counted, no new capital committed"

    existing = snapshot.position_value(intent.underlying)
    projected = existing + added
    projected_pct = (projected / equity) * 100 if equity else 0.0
    values = {
        "underlying": intent.underlying,
        "existing_exposure": round(existing, 2),
        "added_exposure": round(added, 2),
        "added_exposure_basis": basis,
        "projected_exposure": round(projected, 2),
        "projected_pct": round(projected_pct, 2),
        "max_concentration_pct": limit_pct,
        "equity": equity,
    }

    if projected_pct <= limit_pct:
        return CheckResult(
            name="concentration",
            passed=True,
            severity="INFO",
            detail=(
                f"{intent.underlying} projected exposure ${projected:,.2f} = "
                f"{projected_pct:.1f}% of ${equity:,.2f} (limit {limit_pct:g}%)"
            ),
            values=values,
        )

    # An existing holding already over the cap is not something this order
    # created, and refusing to write a call against it would leave the
    # position *more* exposed, not less. Only a breach this order causes blocks.
    existing_pct = (existing / equity) * 100 if equity else 0.0
    values["existing_pct"] = round(existing_pct, 2)
    if added <= 0 and existing_pct > limit_pct:
        return CheckResult(
            name="concentration",
            passed=False,
            severity="WARN",
            detail=(
                f"{intent.underlying} is already {existing_pct:.1f}% of the portfolio, "
                f"over the {limit_pct:g}% cap — this overlay adds no exposure and "
                "reduces upside risk, so it is not blocked"
            ),
            values=values,
        )

    return CheckResult(
        name="concentration",
        passed=False,
        severity="BLOCK",
        detail=(
            f"{intent.underlying} projected exposure {projected_pct:.1f}% breaches the "
            f"{limit_pct:g}% concentration cap (${projected:,.2f} of ${equity:,.2f})"
        ),
        values=values,
    )


def _check_duplicate(intent: TradeIntent, snapshot: PortfolioSnapshot) -> CheckResult:
    """Warn when the account is already short this exact contract.

    A WARN, not a BLOCK: scaling into a position is legitimate. True
    double-submission protection is idempotency (B3), which is a different
    mechanism — this check catches the case where the position already exists.
    """
    if not intent.opens_short_option:
        return CheckResult(
            name="duplicate",
            passed=True,
            severity="INFO",
            detail="order does not open short option exposure",
            values={"applies": False},
        )

    existing = snapshot.short_contracts_on(intent.symbol)
    values = {"option_symbol": intent.symbol, "contracts_already_short": existing}
    if existing == 0:
        return CheckResult(
            name="duplicate",
            passed=True,
            severity="INFO",
            detail="no existing short position on this contract",
            values=values,
        )
    return CheckResult(
        name="duplicate",
        passed=False,
        severity="WARN",
        detail=(
            f"already short {existing} contract(s) of {intent.symbol} — confirm this "
            "is intentional scaling and not a resubmission"
        ),
        values=values,
    )


def _check_price_sanity(intent: TradeIntent, quote_price: float | None) -> CheckResult:
    """Reject market orders on options; sanity-check limit prices against quote."""
    if intent.is_option and intent.order_type == "market":
        return CheckResult(
            name="price_sanity",
            passed=False,
            severity="BLOCK",
            detail=(
                "market order on an option — option books are wide and illiquid; "
                "use a limit price"
            ),
            values={"order_type": "market", "is_option": True},
        )

    if intent.order_type != "limit" or intent.limit_price is None:
        return CheckResult(
            name="price_sanity",
            passed=True,
            severity="INFO",
            detail="no limit price to check",
            values={"order_type": intent.order_type},
        )

    values = {"limit_price": intent.limit_price, "quote_price": quote_price}
    if quote_price is None or quote_price <= 0:
        return CheckResult(
            name="price_sanity",
            passed=True,
            severity="WARN",
            detail=(
                "no current quote available — limit price not sanity-checked "
                "against the market"
            ),
            values=values,
        )

    deviation = (intent.limit_price / quote_price - 1) * 100
    values["deviation_pct"] = round(deviation, 2)

    # Selling far below the market gives away premium; buying far above
    # overpays. 50% is loose on purpose: option quotes move fast and a tight
    # band would reject legitimate orders during the demo.
    if abs(deviation) > 50.0:
        return CheckResult(
            name="price_sanity",
            passed=False,
            severity="BLOCK",
            detail=(
                f"limit ${intent.limit_price:,.2f} deviates {deviation:+.1f}% from the "
                f"${quote_price:,.2f} quote — outside the ±50% tolerance"
            ),
            values=values,
        )

    return CheckResult(
        name="price_sanity",
        passed=True,
        severity="INFO",
        detail=(
            f"limit ${intent.limit_price:,.2f} is {deviation:+.1f}% from the "
            f"${quote_price:,.2f} quote"
        ),
        values=values,
    )


def _check_provenance(intent: TradeIntent) -> CheckResult:
    """An order must trace to an agent run, or be explicitly flagged manual."""
    values = {
        "run_id": intent.run_id,
        "directive_ref": intent.directive_ref,
        "manual_override": intent.manual_override,
    }
    if intent.run_id:
        return CheckResult(
            name="provenance",
            passed=True,
            severity="INFO",
            detail=f"order traces to agent run {intent.run_id}",
            values=values,
        )
    if intent.manual_override and intent.override_reason:
        return CheckResult(
            name="provenance",
            passed=True,
            severity="WARN",
            detail=f"manual order, reason recorded: {intent.override_reason}",
            values=values,
        )
    if intent.manual_override:
        return CheckResult(
            name="provenance",
            passed=False,
            severity="BLOCK",
            detail=(
                "manual_override set without override_reason — an override nobody "
                "can audit later is indistinguishable from no gate at all"
            ),
            values=values,
        )
    return CheckResult(
        name="provenance",
        passed=False,
        severity="BLOCK",
        detail=(
            "no run_id: order cannot be traced to an agent recommendation. Set "
            "manual_override with an override_reason to place it deliberately"
        ),
        values=values,
    )


def _cfg(config, name: str, default):
    """Read a numeric config field, rejecting bools and non-finite values."""
    import math

    if config is None:
        return default
    value = getattr(config, name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return value if math.isfinite(value) else default
