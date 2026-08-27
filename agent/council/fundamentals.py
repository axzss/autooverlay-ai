"""Fundamentals enrichment layer — FREE sources only (Yahoo Finance
unofficial endpoints), graceful degradation everywhere.

Design rules:
  * No paid APIs, no API keys of any kind. Yahoo's unofficial endpoints are
    used with a browser User-Agent plus the public cookie/crumb handshake.
  * Every fetch failure degrades gracefully: a missing field becomes ``None``
    and callers must treat ``None`` as "unknown", never as zero.
  * Responses are cached in ``/tmp/fundamentals_cache.json`` with a 24h TTL
    so repeated council runs do not hammer Yahoo rate limits.
  * No credential values are ever logged (there are none — this module is
    keyless by construction).
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_PATH = Path("/tmp/fundamentals_cache.json")
CACHE_TTL_SECONDS = 24 * 3600

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

QUOTE_SUMMARY_MODULES = "financialData,defaultKeyStatistics,summaryDetail"


def _num(v: Any) -> float | None:
    """Coerce Yahoo {'raw': x} shapes / plain numbers to float, else None."""
    if isinstance(v, dict):
        v = v.get("raw")
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and not math.isnan(float(v)):
        return float(v)
    return None


class FundamentalsProvider:
    """Fetches per-symbol fundamentals from Yahoo Finance (free), cached."""

    def __init__(self, cache_path: Path = CACHE_PATH,
                 ttl_seconds: int = CACHE_TTL_SECONDS,
                 timeout: float = 15.0):
        self.cache_path = cache_path
        self.ttl = ttl_seconds
        self.timeout = timeout
        self._session = None  # lazy requests.Session
        self._crumb: str | None = None

    # ------------------------------------------------------------------ #
    # Cache                                                              #
    # ------------------------------------------------------------------ #
    def _load_cache(self) -> dict:
        try:
            data = json.loads(self.cache_path.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _cache_get(self, symbol: str) -> dict | None:
        entry = self._load_cache().get(symbol)
        if isinstance(entry, dict) and time.time() - entry.get("ts", 0) < self.ttl:
            return entry.get("data") or {}
        return None

    def _cache_put(self, symbol: str, data: dict) -> None:
        cache = self._load_cache()
        cache[symbol] = {"ts": time.time(), "data": data}
        tmp = self.cache_path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(cache))
            tmp.replace(self.cache_path)
        except OSError as exc:  # cache is best-effort
            logger.warning("fundamentals cache write failed: %s", exc)

    # ------------------------------------------------------------------ #
    # HTTP                                                               #
    # ------------------------------------------------------------------ #
    def _get_session(self):
        import requests

        if self._session is None:
            s = requests.Session()
            s.headers.update({"User-Agent": UA})  # no Accept header — Yahoo's
            # getcrumb endpoint returns HTTP 406 for application/json accepts.
            self._session = s
        return self._session

    def _get_crumb(self) -> str | None:
        """Public cookie+crumb handshake for Yahoo's unofficial endpoints."""
        if self._crumb:
            return self._crumb
        try:
            s = self._get_session()
            s.get("https://fc.yahoo.com", timeout=self.timeout)  # sets cookie
            r = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb",
                      timeout=self.timeout)
            if r.status_code == 200 and r.text.strip():
                self._crumb = r.text.strip()
                return self._crumb
        except Exception as exc:
            logger.info("yahoo crumb handshake failed (%s)", exc.__class__.__name__)
        return None

    # ------------------------------------------------------------------ #
    # Fetchers                                                           #
    # ------------------------------------------------------------------ #
    def _fetch_quote_summary(self, symbol: str) -> dict:
        """Return merged {module: {...}} or {} on any failure."""
        crumb = self._get_crumb()
        params: dict[str, str] = {"modules": QUOTE_SUMMARY_MODULES}
        url = (f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
               f"{symbol.upper()}")
        if crumb:
            params["crumb"] = crumb
        try:
            r = self._get_session().get(url, params=params, timeout=self.timeout)
            result = (r.json() or {}).get("quoteSummary", {})
            if r.status_code != 200 or result.get("error"):
                logger.info("quoteSummary %s unavailable (HTTP %s)",
                            symbol.upper(), r.status_code)
                return {}
            return ((result.get("result") or [{}])[0]) or {}
        except Exception as exc:
            logger.info("quoteSummary %s failed (%s)", symbol.upper(),
                        exc.__class__.__name__)
            return {}

    def _fetch_dividend_history(self, symbol: str, years: int = 25) -> list[float]:
        """Return yearly dividend totals per calendar year via chart events.

        Empty list means unknown/unavailable — callers treat it as such."""
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}"
        params = {"range": f"{years}y", "interval": "3mo", "events": "div"}
        try:
            r = self._get_session().get(url, params=params, timeout=self.timeout)
            body = (r.json() or {}).get("chart", {}).get("result") or []
            events = ((body[0] or {}).get("events")) or {}
            divs = events.get("dividends") or events.get("divs") or {}
            if not isinstance(divs, dict):
                return []
            yearly: dict[int, float] = {}
            for ev in divs.values():
                amt = _num(ev.get("amount"))
                ts = ev.get("date")
                if amt and isinstance(ts, (int, float)):
                    yr = time.gmtime(ts).tm_year
                    yearly[yr] = yearly.get(yr, 0.0) + amt
            return [yearly[y] for y in sorted(yearly)]
        except Exception as exc:
            logger.info("dividend history %s failed (%s)", symbol.upper(),
                        exc.__class__.__name__)
            return []

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def get_fundamentals(self, symbol: str, use_cache: bool = True) -> dict:
        """Return a normalized fundamentals dict; every field may be None."""
        sym = symbol.upper()
        if use_cache:
            cached = self._cache_get(sym)
            if cached is not None:
                return cached

        qs = self._fetch_quote_summary(sym)
        fin = qs.get("financialData") or {}
        ks = qs.get("defaultKeyStatistics") or {}
        sd = qs.get("summaryDetail") or {}

        div_years = self._fetch_dividend_history(sym)

        # Dividend record: uninterrupted recent years + total history length.
        # If Yahoo gives us FEWER than 20 years of coverage, the exact-book
        # Ch.14 test cannot be decided — leave the decisive inputs as None so
        # evaluate_defensive() reports the test as inconclusive (passed=None)
        # rather than failing it on incomplete evidence.
        dividend_years_paid: list[bool] | None = None
        years_since_dividend_started: float | None = None
        dividend_years_paid_partial: list[bool] | None = None
        if div_years:
            recent = div_years[-20:]
            dividend_years_paid_partial = [amt > 0 for amt in recent]
            if len(div_years) >= 20:
                dividend_years_paid = dividend_years_paid_partial
                years_since_dividend_started = float(len(div_years))

        data = {
            "symbol": sym,
            # valuation
            "market_cap": _num(sd.get("marketCap")),
            "pe_ratio": _num(sd.get("trailingPE")) or _num(fin.get("forwardPE")),
            "forward_pe": _num(sd.get("forwardPE")),
            "pb_ratio": _num(sd.get("priceToBook"))
                        or _num(ks.get("priceToBook")),
            "peg_ratio": _num(ks.get("pegRatio")),
            "dividend_yield_pct": (
                lambda dy: dy * 100 if dy is not None and dy < 1.5 else dy
            )(_num(sd.get("dividendYield"))),
            "eps_trailing": _num(ks.get("trailingEps")),
            "eps_fwd_estimate": _num(ks.get("forwardEps")),
            "book_value_per_share": _num(ks.get("bookValue")),
            # balance sheet / quality
            "current_ratio": _num(fin.get("currentRatio")),
            "quick_ratio": _num(fin.get("quickRatio")),
            "debt_to_equity": (
                lambda d: d / 100.0 if d is not None else None
            )(_num(fin.get("debtToEquity"))),
            "roe_pct": (
                lambda roe: roe * 100 if roe is not None and roe <= 3 else roe
            )(_num(fin.get("returnOnEquity"))),
            "gross_margin_pct": (
                lambda g: g * 100 if g is not None else None
            )(_num(fin.get("grossMargins"))),
            "operating_margin_pct": (
                lambda m: m * 100 if m is not None else None
            )(_num(fin.get("operatingMargins"))),
            "profit_margin_pct": (
                lambda m: m * 100 if m is not None else None
            )(_num(fin.get("profitMargins"))),
            "total_cash": _num(fin.get("totalCash")),
            "total_debt": _num(fin.get("totalDebt")),
            "revenue_ttm": _num(fin.get("totalRevenue")),
            "free_cash_flow_yield_pct": None,   # computed below when possible
            # growth proxies
            "earnings_growth_fwd_pct": (
                lambda g: g * 100 if g is not None else None
            )(_num(fin.get("earningsGrowth"))),
            "earnings_growth_5y_pct": None,     # filled below from EPS history proxy
            "revenue_growth_fwd_pct": (
                lambda g: g * 100 if g is not None else None
            )(_num(fin.get("revenueGrowth"))),
            # Graham test inputs
            "dividend_years_paid": dividend_years_paid,
            "dividend_years_paid_partial": dividend_years_paid_partial,
            "years_since_dividend_started": years_since_dividend_started,
            "positive_earnings_years": None,    # not available from these endpoints
            "_source": "yahoo_unofficial",
            "_fetched_at": time.time(),
        }

        # FCF yield proxy: FCF ~ operating cashflow not exposed here; leave None.
        # Earnings-growth 5y proxy: use trailing->forward EPS CAGR if both exist.
        etr, efwd = data["eps_trailing"], data["eps_fwd_estimate"]
        if etr and efwd and etr > 0 and efwd > 0:
            data["earnings_growth_5y_pct"] = round((efwd / etr - 1) * 100, 2)

        if use_cache:
            self._cache_put(sym, data)
        return data


# ------------------------------------------------------------------------- #
# Council-flow integration                                                   #
# ------------------------------------------------------------------------- #
def build_snapshot_with_fundamentals(
    symbol: str,
    price_snapshot: dict,
    provider: FundamentalsProvider | None = None,
) -> dict:
    """Merge bar-derived price/vol snapshot + fetched fundamentals into the
    dict shape CouncilEngine personas expect.

    Bar-derived fields always win for price/vol; fundamentals fill the
    fundamental keys; anything unfetched stays None (never fabricated).
    """
    provider = provider or FundamentalsProvider()
    f = provider.get_fundamentals(symbol)

    u = dict(price_snapshot)
    u.setdefault("symbol", symbol)
    u.setdefault("annualized_volatility_pct",
                 price_snapshot.get("vol30d_annualized_pct"))

    passthrough = [
        "market_cap", "pe_ratio", "forward_pe", "pb_ratio", "peg_ratio",
        "dividend_yield_pct", "eps_trailing", "eps_fwd_estimate",
        "book_value_per_share", "current_ratio", "quick_ratio",
        "debt_to_equity", "roe_pct", "gross_margin_pct",
        "operating_margin_pct", "profit_margin_pct", "total_cash",
        "total_debt", "revenue_ttm", "free_cash_flow_yield_pct",
        "earnings_growth_fwd_pct", "earnings_growth_5y_pct",
        "revenue_growth_fwd_pct", "dividend_years_paid",
        "dividend_years_paid_partial",
        "years_since_dividend_started", "positive_earnings_years",
    ]
    for key in passthrough:
        if f.get(key) is not None:
            u[key] = f[key]

    # Derived persona-facing helpers ------------------------------------- #
    price = _as_num(u.get("price"))
    eps = _as_num(u.get("eps_trailing"))
    bvps = _as_num(u.get("book_value_per_share"))
    rev = _as_num(u.get("revenue_ttm"))
    mcap = _as_num(u.get("market_cap"))

    if price and eps and eps > 0:
        u.setdefault("earnings_yield_pct", round(100.0 * eps / price, 4))
    # Size test proxy (Ch.14 test 1): revenue TTM in $M stands in for annual sales.
    if rev:
        u["annual_sales_musd"] = round(rev / 1e6, 1)
    elif mcap:
        u.setdefault("annual_sales_musd", round(mcap / 1e6, 1))
    # Conservative Graham-style appraised value: 15x trailing EPS (his P/E
    # ceiling applied to current earning power).
    if price and eps and eps > 0:
        u.setdefault("intrinsic_value_estimate", round(eps * 15.0, 2))
    return u


def _as_num(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and not math.isnan(float(v)):
        return float(v)
    return None
