"""Alpaca options payload adapter — the single place broker JSON becomes typed.

Why this module exists (docs/BRIEF-BACKEND-V2.md, D1 + D2): route code used to
read broker field names inline and guessed them wrong in two independent places.
Both bugs produced "no candidates", which is indistinguishable from an empty
portfolio, so 236 green tests never caught either.

Rules enforced here:

* **Missing means ``None``, never ``0.0``.** A defaulted ``0.0`` delta passes a
  delta-band filter trivially — that was D2's mechanism. ``None`` is an
  admission of ignorance and callers must handle it explicitly.
* **Strike and expiration come from the OCC symbol**, not from a payload field.
  The symbol is always present; ``details`` is not.
* **One OCC parser.** ``alpaca_client.parse_occ_symbol`` now delegates here.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal

OCC_RE = re.compile(r"^([A-Z.]{1,6})(\d{6})([CP])(\d{8})$")

# Alpaca sends camelCase in the options snapshot/chain payloads; alpaca-py and
# some feeds hand back snake_case. Accept both rather than betting on one.
_QUOTE_KEYS = ("latestQuote", "latest_quote")
_TRADE_KEYS = ("latestTrade", "latest_trade")
_IV_KEYS = ("impliedVolatility", "implied_volatility")
_BID_KEYS = ("bp", "bid_price", "bidPrice")
_ASK_KEYS = ("ap", "ask_price", "askPrice")
_TRADE_PRICE_KEYS = ("p", "price", "last_price")
_OI_KEYS = ("open_interest", "openInterest", "oi")


@dataclass(frozen=True)
class OccSymbol:
    """Components of an OCC option symbol, e.g. ``AAPL240621C00175000``."""

    underlying: str
    expiration: date
    option_type: Literal["call", "put"]
    strike: float


@dataclass(frozen=True)
class OptionQuote:
    """A normalized option quote. Every optional field may legitimately be None."""

    option_symbol: str
    underlying: str
    expiration: date
    strike: float
    option_type: Literal["call", "put"]
    bid: float | None
    ask: float | None
    mid: float | None
    last: float | None
    implied_volatility: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    rho: float | None
    open_interest: int | None
    source: str
    as_of: datetime | None

    def days_to_expiry(self, today: date | None = None) -> int:
        ref = today or datetime.now(timezone.utc).date()
        return (self.expiration - ref).days

    @property
    def price(self) -> float | None:
        """Best available price: mid, else last. None when neither is known."""
        return self.mid if self.mid is not None else self.last

    def to_dict(self) -> dict:
        return {
            "option_symbol": self.option_symbol,
            "symbol": self.underlying,
            "expiration_date": self.expiration.isoformat(),
            "strike_price": self.strike,
            "option_type": self.option_type,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "last": self.last,
            "implied_volatility": self.implied_volatility,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "rho": self.rho,
            "open_interest": self.open_interest,
            "source": self.source,
            "as_of": self.as_of.isoformat() if self.as_of else None,
        }


def parse_occ(symbol: str) -> OccSymbol:
    """Parse an OCC option symbol. Raises ValueError on anything malformed."""
    cleaned = str(symbol or "").upper().replace(" ", "")
    match = OCC_RE.match(cleaned)
    if not match:
        raise ValueError(f"Invalid OCC option symbol: {symbol!r}")
    root, yymmdd, cp, strike_raw = match.groups()
    try:
        expiration = date(
            2000 + int(yymmdd[0:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
        )
    except ValueError as exc:
        # e.g. month 13 or day 32 — a well-formed-looking symbol with an
        # impossible date. Surface it as ValueError like every other bad symbol
        # so callers have exactly one exception type to handle.
        raise ValueError(f"Invalid OCC expiration in {symbol!r}: {exc}") from exc
    return OccSymbol(
        underlying=root,
        expiration=expiration,
        option_type="call" if cp == "C" else "put",
        strike=int(strike_raw) / 1000.0,
    )


def _first(mapping: Any, keys: tuple[str, ...]) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _num(value: Any) -> float | None:
    """Coerce to a finite float, or None. Never returns 0.0 for missing input."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _pos(value: Any) -> float | None:
    """A price that must be strictly positive to be meaningful."""
    result = _num(value)
    return result if result is not None and result > 0 else None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    raw = value.replace("Z", "+00:00")
    # Alpaca timestamps carry nanosecond precision; fromisoformat accepts at
    # most microseconds on 3.11, so trim the fraction rather than losing the
    # whole timestamp to a ValueError.
    match = re.match(r"^(.*\.\d{1,6})\d*(\+\d{2}:\d{2}|-\d{2}:\d{2})?$", raw)
    if match:
        raw = match.group(1) + (match.group(2) or "")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def normalize_snapshot(
    option_symbol: str, raw: Any, *, source: str = "indicative"
) -> OptionQuote | None:
    """Build an OptionQuote from one raw snapshot entry.

    Returns None — never raises — when the symbol is not parseable OCC or the
    payload is not a mapping. A malformed contract inside an otherwise good
    chain must not abort the whole screen.
    """
    if not isinstance(raw, dict):
        return None
    try:
        occ = parse_occ(option_symbol)
    except ValueError:
        return None

    quote = _first(raw, _QUOTE_KEYS) or {}
    trade = _first(raw, _TRADE_KEYS) or {}
    greeks = raw.get("greeks") or {}
    if not isinstance(greeks, dict):
        greeks = {}

    bid = _pos(_first(quote, _BID_KEYS))
    ask = _pos(_first(quote, _ASK_KEYS))
    if bid is not None and ask is not None:
        mid = round((bid + ask) / 2, 4)
    else:
        # A one-sided book is real and usable, but do not pretend the single
        # side is a mid — callers that need a two-sided market check `mid`.
        mid = None

    return OptionQuote(
        option_symbol=str(option_symbol).upper().replace(" ", ""),
        underlying=occ.underlying,
        expiration=occ.expiration,
        strike=occ.strike,
        option_type=occ.option_type,
        bid=bid,
        ask=ask,
        mid=mid,
        last=_pos(_first(trade, _TRADE_PRICE_KEYS)),
        implied_volatility=_num(_first(raw, _IV_KEYS)),
        delta=_num(greeks.get("delta")),
        gamma=_num(greeks.get("gamma")),
        theta=_num(greeks.get("theta")),
        vega=_num(greeks.get("vega")),
        rho=_num(greeks.get("rho")),
        open_interest=_int(_first(raw, _OI_KEYS)),
        source=source,
        as_of=_ts(quote.get("t")) or _ts(trade.get("t")),
    )


def iter_snapshot_entries(payload: Any) -> list[tuple[str, dict]]:
    """Yield ``(option_symbol, raw)`` pairs from a snapshots/chain payload.

    Alpaca returns ``snapshots`` as a **dict keyed by OCC option symbol**. Some
    feeds and SDK paths hand back a list of objects that each carry their own
    ``symbol``. Accept both; reject neither silently.
    """
    if isinstance(payload, dict):
        container = payload.get("snapshots")
        if container is None:
            container = payload
    else:
        container = payload

    entries: list[tuple[str, dict]] = []
    if isinstance(container, dict):
        for symbol, raw in container.items():
            if isinstance(raw, dict):
                entries.append((str(symbol), raw))
    elif isinstance(container, list):
        for raw in container:
            if not isinstance(raw, dict):
                continue
            symbol = raw.get("symbol") or raw.get("option_symbol")
            if symbol:
                entries.append((str(symbol), raw))
    return entries


def normalize_snapshots(payload: Any, *, source: str = "indicative") -> list[OptionQuote]:
    """Normalize a whole snapshots payload, skipping entries that cannot parse."""
    quotes: list[OptionQuote] = []
    for symbol, raw in iter_snapshot_entries(payload):
        quote = normalize_snapshot(symbol, raw, source=source)
        if quote is not None:
            quotes.append(quote)
    return quotes
