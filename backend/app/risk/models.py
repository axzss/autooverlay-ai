"""Value objects for the pre-trade risk gate.

Every check returns its computed numbers, not a bare boolean. A rejection a
human cannot diagnose in seconds is a rejection that will be overridden blind,
and the whole point of the gate is that the override is the exceptional path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal

Severity = Literal["BLOCK", "WARN", "INFO"]

# A short call is covered by shares; a short put by cash or a spread. Anything
# else that opens short option exposure is naked by definition.
CONTRACT_MULTIPLIER = 100


@dataclass(frozen=True)
class CheckResult:
    """One risk check, with the values it was decided on."""

    name: str
    passed: bool
    severity: Severity
    detail: str
    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "severity": self.severity,
            "detail": self.detail,
            "values": self.values,
        }


@dataclass(frozen=True)
class TradeIntent:
    """The order under evaluation, normalized away from the HTTP layer."""

    symbol: str
    qty: float
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    time_in_force: str
    limit_price: float | None = None
    client_order_id: str | None = None
    # Provenance: which agent run and directive produced this order.
    run_id: str | None = None
    directive_ref: str | None = None
    manual_override: bool = False
    override_reason: str | None = None

    # -- derived option properties ----------------------------------------

    @property
    def is_option(self) -> bool:
        return self._occ() is not None

    @property
    def underlying(self) -> str:
        occ = self._occ()
        return occ.underlying if occ else self.symbol

    @property
    def option_type(self) -> str | None:
        occ = self._occ()
        return occ.option_type if occ else None

    @property
    def strike(self) -> float | None:
        occ = self._occ()
        return occ.strike if occ else None

    @property
    def expiration(self) -> date | None:
        occ = self._occ()
        return occ.expiration if occ else None

    @property
    def opens_short_option(self) -> bool:
        """True when this order creates or increases short option exposure."""
        return self.is_option and self.side == "sell"

    @property
    def contracts(self) -> int:
        return int(abs(self.qty))

    def _occ(self):
        from ..adapters.options import parse_occ

        try:
            return parse_occ(self.symbol)
        except ValueError:
            return None


@dataclass(frozen=True)
class PortfolioSnapshot:
    """The state a decision is made against.

    ``available`` is False when broker state could not be read. The gate then
    fails closed: a gate that opens when it cannot see is worse than no gate,
    because it manufactures confidence it has not earned.
    """

    available: bool
    equity: float | None = None
    cash: float | None = None
    positions: list[dict] = field(default_factory=list)
    open_option_positions: list[dict] = field(default_factory=list)
    halted: bool = False
    halt_reasons: list[str] = field(default_factory=list)
    fetch_error: str | None = None
    mode: str = "unknown"

    def shares_held(self, underlying: str) -> float:
        total = 0.0
        for position in self.positions:
            if str(position.get("symbol", "")).upper() != underlying.upper():
                continue
            if position.get("asset_class") == "us_option":
                continue
            try:
                total += float(position.get("qty") or 0)
            except (TypeError, ValueError):
                continue
        return total

    def short_contracts_on(self, option_symbol: str) -> int:
        """Contracts already short on this exact contract."""
        total = 0
        for position in self.open_option_positions:
            if str(position.get("option_symbol", "")).upper() != option_symbol.upper():
                continue
            try:
                qty = float(position.get("qty") or 0)
            except (TypeError, ValueError):
                continue
            if qty < 0:
                total += int(abs(qty))
        return total

    def short_calls_on(self, underlying: str) -> int:
        """Contracts already short-called against this underlying.

        Existing covered calls consume the shares that back them, so a second
        order cannot count the same 100 shares twice.
        """
        total = 0
        for position in self.open_option_positions:
            if str(position.get("symbol", "")).upper() != underlying.upper():
                continue
            if str(position.get("option_type", "")).lower() != "call":
                continue
            try:
                qty = float(position.get("qty") or 0)
            except (TypeError, ValueError):
                continue
            if qty < 0:
                total += int(abs(qty))
        return total

    def position_value(self, underlying: str) -> float:
        total = 0.0
        for position in self.positions:
            if str(position.get("symbol", "")).upper() != underlying.upper():
                continue
            try:
                total += abs(float(position.get("market_value") or 0))
            except (TypeError, ValueError):
                continue
        return total

    def hash(self) -> str:
        """Stable digest of the state this decision was made against."""
        payload = json.dumps(
            {
                "available": self.available,
                "equity": self.equity,
                "cash": self.cash,
                "halted": self.halted,
                "positions": sorted(
                    (str(p.get("symbol")), str(p.get("qty"))) for p in self.positions
                ),
                "options": sorted(
                    (str(p.get("option_symbol")), str(p.get("qty")))
                    for p in self.open_option_positions
                ),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class RiskDecision:
    """The verdict, plus every check that produced it."""

    allowed: bool
    checks: list[CheckResult]
    evaluated_at: datetime
    snapshot_hash: str
    mode: str = "unknown"
    override_applied: bool = False

    @property
    def hard_failures(self) -> list[str]:
        return [c.detail for c in self.checks if not c.passed and c.severity == "BLOCK"]

    @property
    def warnings(self) -> list[str]:
        return [c.detail for c in self.checks if not c.passed and c.severity == "WARN"]

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "checks": [c.to_dict() for c in self.checks],
            "hard_failures": self.hard_failures,
            "warnings": self.warnings,
            "evaluated_at": self.evaluated_at.isoformat(),
            "snapshot_hash": self.snapshot_hash,
            "mode": self.mode,
            "override_applied": self.override_applied,
        }

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
