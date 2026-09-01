"""Alpaca paper-trading REST client.

Credentials are read ONLY from environment variables:
  ALPACA_KEY       - Alpaca API key ID
  ALPACA_SECRET    - Alpaca secret key
  ALPACA_BASE_URL  - e.g. https://paper-api.alpaca.markets
  APCA_API_DATA_URL - optional, e.g. https://data.alpaca.markets

If any trading credential is missing, `is_configured()` returns False and
routes fall back to bundled mock data so the app runs without credentials.
Keys are never hardcoded in this repository.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx


class AlpacaConfigError(RuntimeError):
    """Raised when a call is attempted without credentials configured."""


class AlpacaAPIError(RuntimeError):
    """Raised when Alpaca cannot return a valid API response."""


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value else default


def get_key() -> str | None:
    return _env("ALPACA_KEY")


def get_secret() -> str | None:
    return _env("ALPACA_SECRET")


def get_base_url() -> str:
    return _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets") or ""


def get_data_url() -> str:
    return _env("APCA_API_DATA_URL", "https://data.alpaca.markets") or ""


def is_configured() -> bool:
    """True only when all three required trading credentials are present."""
    return bool(get_key() and get_secret() and get_base_url())


def _headers() -> dict[str, str]:
    if not is_configured():
        raise AlpacaConfigError(
            "Alpaca credentials missing: set ALPACA_KEY, ALPACA_SECRET, ALPACA_BASE_URL"
        )
    return {
        "APCA-API-KEY-ID": get_key() or "",
        "APCA-API-SECRET-KEY": get_secret() or "",
        "Content-Type": "application/json",
    }


# Reuse one HTTP client across calls. httpx.Client is thread-safe, and Alpaca
# data endpoints do not require per-call setup.
_shared_client = None


def _get_shared_client() -> httpx.Client:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0))
    return _shared_client


class AlpacaClient:
    """Thin synchronous wrapper over the Alpaca Trading / Data REST APIs."""

    # Hard cap on snapshot pagination: bounded so a broken or hostile
    # next_page_token cannot spin this loop forever inside one HTTP request.
    MAX_SNAPSHOT_PAGES = 10

    # In-memory caches keep repeated dashboard/strategy reads from hitting the
    # network on every keystroke/route change. TTLs are intentionally short so
    # the UI reflects live state without manual refresh.
    _BARS_TTL_SECONDS = 60
    _SNAPSHOTS_TTL_SECONDS = 30

    def __init__(self) -> None:
        # Instance creation is cheap; real work is funneled through the shared
        # client above so TCP/TLS is reused across threads/calls.
        self._bars_cache: dict[str, tuple[float, list[dict]]] = {}
        self._snapshots_cache: dict[str, tuple[float, list[dict]]] = {}

    # -- trading api -------------------------------------------------------

    def _trading_request(self, method: str, path: str, json_body: dict | None = None) -> Any:
        url = f"{get_base_url().rstrip('/')}{path}"
        try:
            resp = _get_shared_client().request(method, url, headers=_headers(), json=json_body)
        except httpx.TimeoutException as exc:
            raise AlpacaAPIError(f"Alpaca request timed out: {method} {path}") from exc
        except httpx.RequestError as exc:
            raise AlpacaAPIError(f"Alpaca API unreachable: {method} {path}") from exc
        if resp.status_code >= 400:
            raise AlpacaAPIError(f"Alpaca API error {resp.status_code}: {resp.text[:500]}")
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            return resp.json()
        except (TypeError, ValueError) as exc:
            raise AlpacaAPIError("Alpaca API returned invalid JSON") from exc

    def get_account(self) -> dict:
        result = self._trading_request("GET", "/v2/account")
        if not isinstance(result, dict):
            raise AlpacaAPIError("Alpaca account response must be an object")
        return result

    def get_positions(self) -> list[dict]:
        result = self._trading_request("GET", "/v2/positions") or []
        if not isinstance(result, list) or not all(isinstance(p, dict) for p in result):
            raise AlpacaAPIError("Alpaca positions response must be a list")
        return result

    def submit_order(self, order: dict) -> dict:
        result = self._trading_request("POST", "/v2/orders", json_body=order)
        if not isinstance(result, dict):
            raise AlpacaAPIError("Alpaca order response must be an object")
        return result

    def list_orders(self, status: str = "open", limit: int = 50) -> list[dict]:
        result = (
            self._trading_request(
                "GET", f"/v2/orders?status={status}&limit={limit}"
            )
            or []
        )
        if not isinstance(result, list) or not all(isinstance(o, dict) for o in result):
            raise AlpacaAPIError("Alpaca orders response must be a list")
        return result

    def get_clock(self) -> dict:
        result = self._trading_request("GET", "/v2/clock")
        if not isinstance(result, dict):
            raise AlpacaAPIError("Alpaca clock response must be an object")
        return result

    # -- data api (equity bars) -------------------------------------------

    def _data_request(self, method: str, url: str, params: dict) -> dict:
        try:
            resp = _get_shared_client().request(
                method, url, headers=_headers(), params=params
            )
        except httpx.TimeoutException as exc:
            raise AlpacaAPIError(f"Alpaca data request timed out: {method} {url}") from exc
        except httpx.RequestError as exc:
            raise AlpacaAPIError(f"Alpaca data API unreachable: {method} {url}") from exc
        if resp.status_code >= 400:
            raise AlpacaAPIError(
                f"Alpaca data API error {resp.status_code}: {resp.text[:300]}"
            )
        try:
            payload = resp.json()
        except (TypeError, ValueError) as exc:
            raise AlpacaAPIError("Alpaca data API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AlpacaAPIError("Alpaca data API response must be an object")
        return payload

    def _bars_cache_key(self, symbol: str, days: int) -> str:
        return f"bars:{symbol.upper()}:{days}"

    def get_daily_bars(self, symbol: str, days: int = 365) -> list[dict]:
        """Return daily equity bars for the trailing window, with short TTL."""
        from datetime import datetime, timedelta, timezone

        cache_key = self._bars_cache_key(symbol, days)
        now = time.time()
        cached = self._bars_cache.get(cache_key)
        if cached and now - cached[0] < self._BARS_TTL_SECONDS:
            return cached[1]

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        url = f"{get_data_url().rstrip('/')}/v2/stocks/bars"
        params = {
            "symbols": symbol.upper(),
            "timeframe": "1Day",
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "limit": 10000,
            "feed": "iex",
        }
        payload = self._data_request("GET", url, params)
        bars_by_symbol = payload.get("bars")
        if not isinstance(bars_by_symbol, dict):
            raise AlpacaAPIError("Alpaca bars response must contain a mapping")
        bars = bars_by_symbol.get(symbol.upper(), [])
        if not isinstance(bars, list) or not all(isinstance(bar, dict) for bar in bars):
            raise AlpacaAPIError("Alpaca bars response must contain a list")
        self._bars_cache[cache_key] = (now, bars)
        return bars

    # -- data api (option snapshots) --------------------------------------

    def _snapshots_cache_key(self, underlying: str) -> str:
        return f"snapshots:{underlying.upper()}"

    def get_option_snapshots(self, underlying: str) -> list[dict]:
        """Return option snapshots for an underlying, with short TTL."""
        from .adapters.options import iter_snapshot_entries

        cache_key = self._snapshots_cache_key(underlying)
        now = time.time()
        cached = self._snapshots_cache.get(cache_key)
        if cached and now - cached[0] < self._SNAPSHOTS_TTL_SECONDS:
            return cached[1]

        url = f"{get_data_url().rstrip('/')}/v1beta1/options/snapshots/{underlying.upper()}"
        out: list[dict] = []
        page_token: str | None = None
        for _ in range(self.MAX_SNAPSHOT_PAGES):
            params: dict[str, Any] = {"feed": "indicative", "limit": 500}
            if page_token:
                params["page_token"] = page_token
            payload = self._data_request("GET", url, params)
            raw_container = payload.get("snapshots")
            if raw_container is not None and not isinstance(raw_container, (dict, list)):
                raise AlpacaAPIError(
                    "Alpaca snapshots response must be an object or a list"
                )
            for symbol, raw in iter_snapshot_entries(payload):
                out.append({**raw, "symbol": symbol})
            page_token = payload.get("next_page_token") or None
            if not page_token:
                break
        self._snapshots_cache[cache_key] = (now, out)
        return out


def normalize_option_position(position: dict) -> dict | None:
    """Normalize an Alpaca option position for ExitManager consumption.

    Invalid or incomplete broker records are ignored instead of entering the
    risk pipeline with guessed values.
    """
    if not isinstance(position, dict) or position.get("asset_class") != "us_option":
        return None
    option_symbol = str(position.get("symbol") or "").upper().strip()
    try:
        parsed = parse_occ_symbol(option_symbol)
        qty = float(position.get("qty"))
        initial = float(position.get("avg_entry_price"))
        current = float(position.get("current_price"))
    except (TypeError, ValueError):
        return None
    if qty == 0 or initial < 0 or current < 0:
        return None
    contracts = int(abs(qty))
    if contracts < 1:
        return None
    try:
        market_value = float(position.get("market_value"))
    except (TypeError, ValueError):
        market_value = 0.0
    return {
        "symbol": parsed["underlying"],
        "option_symbol": option_symbol,
        "strategy": "SHORT_CALL" if parsed["type"] == "call" else "SHORT_PUT",
        "contracts": contracts,
        "qty": qty,
        "side": "short" if qty < 0 else "long",
        "expiration_date": parsed["expiration"],
        "strike_price": parsed["strike"],
        "option_type": parsed["type"],
        "initial_premium": initial,
        "current_premium": current,
        "premium_received": round(initial * 100 * contracts, 2),
        "market_value": market_value,
    }


def parse_occ_symbol(symbol: str) -> dict:
    """Parse an OCC option symbol like AAPL240621C00175000 into components.

    Kept as the historical entry point; the single implementation now lives in
    ``adapters.options.parse_occ`` so there is exactly one OCC parser in the
    backend (there were three, and one of them raised TypeError — D3).
    """
    from .adapters.options import parse_occ

    occ = parse_occ(symbol)
    return {
        "underlying": occ.underlying,
        "expiration": occ.expiration.isoformat(),
        "type": occ.option_type,
        "strike": occ.strike,
    }
