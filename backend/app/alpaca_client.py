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


class AlpacaClient:
    """Thin synchronous wrapper over the Alpaca Trading / Data REST APIs."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    # -- trading api -------------------------------------------------------

    def _trading_request(self, method: str, path: str, json_body: dict | None = None) -> Any:
        url = f"{get_base_url().rstrip('/')}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(method, url, headers=_headers(), json=json_body)
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

    # -- data api (option chains) -----------------------------------------

    # -- data api (equity bars) ---------------------------------------------

    def _data_request(self, method: str, url: str, params: dict) -> dict:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(method, url, headers=_headers(), params=params)
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

    def get_daily_bars(self, symbol: str, days: int = 365) -> list[dict]:
        """Return daily equity bars (list of {c, t, ...}) for the trailing window."""
        from datetime import datetime, timedelta, timezone

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
        return bars

    def get_option_snapshots(self, underlying: str) -> list[dict]:
        """Return option snapshots for an underlying (indicative feed)."""
        url = f"{get_data_url().rstrip('/')}/v1beta1/options/snapshots/{underlying.upper()}"
        params = {"feed": "indicative", "limit": 500}
        payload = self._data_request("GET", url, params)
        snapshots = payload.get("snapshots", [])
        if not isinstance(snapshots, list) or not all(isinstance(snapshot, dict) for snapshot in snapshots):
            raise AlpacaAPIError("Alpaca snapshots response must contain a list")
        return snapshots


def parse_occ_symbol(symbol: str) -> dict:
    """Parse an OCC option symbol like AAPL240621C00175000 into components."""
    import re

    m = re.match(
        r"^([A-Z.]{1,6})(\d{6})([CP])(\d{8})$", symbol.upper().replace(" ", "")
    )
    if not m:
        raise ValueError(f"Invalid OCC option symbol: {symbol}")
    root, date, cp, strike = m.groups()
    return {
        "underlying": root,
        "expiration": f"20{date[0:2]}-{date[2:4]}-{date[4:6]}",
        "type": "call" if cp == "C" else "put",
        "strike": int(strike) / 1000.0,
    }
