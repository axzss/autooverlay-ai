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
        "APCA-API-SECRET": get_secret() or "",
        "Content-Type": "application/json",
    }


class AlpacaClient:
    """Thin synchronous wrapper over the Alpaca Trading / Data REST APIs."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    # -- trading api -------------------------------------------------------

    def _trading_request(self, method: str, path: str, json_body: dict | None = None) -> Any:
        url = f"{get_base_url().rstrip('/')}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.request(method, url, headers=_headers(), json=json_body)
        if resp.status_code >= 400:
            raise RuntimeError(f"Alpaca API error {resp.status_code}: {resp.text[:500]}")
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def get_account(self) -> dict:
        return self._trading_request("GET", "/v2/account")

    def get_positions(self) -> list[dict]:
        return self._trading_request("GET", "/v2/positions") or []

    def submit_order(self, order: dict) -> dict:
        return self._trading_request("POST", "/v2/orders", json_body=order)

    def list_orders(self, status: str = "open", limit: int = 50) -> list[dict]:
        return (
            self._trading_request(
                "GET", f"/v2/orders?status={status}&limit={limit}"
            )
            or []
        )

    # -- data api (option chains) -----------------------------------------

    def get_option_snapshots(self, underlying: str) -> list[dict]:
        """Return option snapshots for an underlying (indicative feed)."""
        url = f"{get_data_url().rstrip('/')}/v1beta1/options/snapshots/{underlying.upper()}"
        params = {"feed": "indicative", "limit": 500}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, headers=_headers(), params=params)
        if resp.status_code >= 400:
            raise RuntimeError(f"Alpaca data API error {resp.status_code}: {resp.text[:300]}")
        return (resp.json() or {}).get("snapshots", [])


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
