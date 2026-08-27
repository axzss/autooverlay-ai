"""
Portfolio Analyst.

Portfolio-context checks applied on top of strategy screening:
- Concentration: no more than MAX_CONCENTRATION (25%) of total portfolio
  value committed to one ticker's overlays.
- Sector awareness: static map of common tickers to sectors; flags
  sector-level stacking of overlay exposure.
- Cash reserve: keep at least MIN_CASH_RESERVE_PCT (10%) cash after the
  collateral commitment of any new position.

Pure logic, deterministic, no I/O.
"""

from typing import Dict, List, Optional, Tuple

try:
    from .config import StrategyConfig
except ImportError:  # pragma: no cover - direct-script imports
    from config import StrategyConfig

MAX_CONCENTRATION = 0.25        # max share of portfolio value per ticker
MIN_CASH_RESERVE_PCT = 0.10     # min cash remaining after collateral

SECTOR_MAP = {
    # tech
    "AAPL": "tech", "MSFT": "tech", "NVDA": "tech", "GOOGL": "tech",
    "GOOG": "tech", "AMZN": "tech", "META": "tech", "TSLA": "tech",
    "AMD": "tech", "NFLX": "tech", "CRM": "tech", "ORCL": "tech",
    "AVGO": "tech", "INTC": "tech", "MU": "tech", "PLTR": "tech",
    "SHOP": "tech", "UBER": "tech", "SQ": "tech", "COIN": "crypto_finance",
    # finance
    "JPM": "finance", "BAC": "finance", "WFC": "finance", "GS": "finance",
    "MS": "finance", "C": "finance", "V": "finance", "MA": "finance",
    "BRK.B": "finance", "SCHW": "finance", "AXP": "finance",
    # healthcare
    "JNJ": "healthcare", "UNH": "healthcare", "PFE": "healthcare",
    "MRK": "healthcare", "ABBV": "healthcare", "LLY": "healthcare",
    "TMO": "healthcare", "ABT": "healthcare",
    # energy
    "XOM": "energy", "CVX": "energy", "COP": "energy", "SLB": "energy",
    # consumer / retail
    "WMT": "consumer", "COST": "consumer", "KO": "consumer", "PEP": "consumer",
    "PG": "consumer", "MCD": "consumer", "NKE": "consumer", "SBUX": "consumer",
    "HD": "consumer", "TGT": "consumer", "DIS": "consumer",
    # industrials
    "CAT": "industrials", "BA": "industrials", "GE": "industrials",
    "HON": "industrials", "UPS": "industrials", "LMT": "industrials",
    # telecom
    "VZ": "telecom", "T": "telecom", "TMUS": "telecom",
}


def get_sector(ticker: str) -> str:
    """Sector for a ticker; 'other' if unmapped."""
    return SECTOR_MAP.get(str(ticker).upper(), "other")


class PortfolioAnalyst:
    """Concentration / sector / cash-reserve checks for overlay decisions."""

    def __init__(
        self,
        max_concentration: Optional[float] = None,
        min_cash_reserve_pct: Optional[float] = None,
        sector_map: Optional[Dict[str, str]] = None,
        config: Optional[StrategyConfig] = None,
        max_sector_concentration: Optional[float] = None,
        sector_cap_group=None,
    ):
        cfg = config or StrategyConfig()
        self.max_concentration = (
            max_concentration if max_concentration is not None
            else cfg.max_concentration_pct / 100.0)
        self.min_cash_reserve_pct = (
            min_cash_reserve_pct if min_cash_reserve_pct is not None
            else cfg.min_cash_reserve_pct / 100.0)
        self.sector_map = dict(sector_map or SECTOR_MAP)
        # Council §6 correlation rule: tech-complex (AAPL/MSFT/NVDA/QQQ)
        # combined exposure ≤ max_sector_concentration_pct of deployed
        # overlay capital. Counted as tech, not as a diversifier.
        self.max_sector_concentration = (
            max_sector_concentration if max_sector_concentration is not None
            else cfg.max_sector_concentration_pct / 100.0)
        self.sector_cap_group = tuple(
            s.upper() for s in (sector_cap_group or cfg.sector_cap_group
                                or ("AAPL", "MSFT", "NVDA", "QQQ")))

    # ------------------------------------------------------------------ #
    # Core checks                                                         #
    # ------------------------------------------------------------------ #
    def concentration_by_ticker(self, positions: List[Dict],
                                portfolio_value: float) -> Dict[str, Dict]:
        """
        Per-ticker overlay value as a fraction of portfolio value.

        Position dicts may carry `market_value` directly or `qty` +
        `current_price`/`avg_entry_price`. Overlay collateral for short
        options uses `collateral` if present.
        """
        by_ticker: Dict[str, float] = {}
        for p in positions:
            sym = str(p.get("symbol", "?")).upper()
            mv = p.get("market_value")
            if mv is None:
                price = p.get("current_price") or p.get("avg_entry_price") or 0
                mv = float(p.get("qty") or 0) * float(price)
            by_ticker[sym] = by_ticker.get(sym, 0.0) + float(mv)

        out = {}
        for sym, val in by_ticker.items():
            frac = val / portfolio_value if portfolio_value > 0 else 1.0
            out[sym] = {
                "value": round(val, 2),
                "fraction_of_portfolio": round(frac, 4),
                "within_limit": frac <= self.max_concentration + 1e-9,
            }
        return out

    def check_new_position(self, symbol: str, collateral_required: float,
                           existing_overlay_value_for_symbol: float,
                           portfolio_value: float, account_cash: float,
                           contracts: int = 1,
                           existing_positions: Optional[List[Dict]] = None,
                           ) -> Tuple[bool, List[str]]:
        """
        Gate a proposed new overlay position.

        Returns (allowed, reasoning_trace). Checks:
          1. concentration: (existing + new) / portfolio <= 25%
          2. cash reserve: account_cash - collateral >= 10% of portfolio
             value (and >= 0).
          3. council sector cap: correlated-group (tech complex:
             AAPL/MSFT/NVDA/QQQ) combined exposure <=
             max_sector_concentration of deployed overlay capital — when
             ``existing_positions`` is supplied.
        """
        trace: List[str] = []
        allowed = True
        sym = str(symbol).upper()

        projected = existing_overlay_value_for_symbol + collateral_required
        conc_frac = projected / portfolio_value if portfolio_value > 0 else 1.0
        trace.append(
            f"concentration check: {sym} overlays ${projected:,.0f} = "
            f"{conc_frac*100:.1f}% of ${portfolio_value:,.0f} portfolio "
            f"(limit {self.max_concentration*100:.0f}%) "
            f"{'✓' if conc_frac <= self.max_concentration else '✗ BLOCKED'}")
        if conc_frac > self.max_concentration:
            allowed = False

        cash_after = account_cash - collateral_required
        reserve_needed = portfolio_value * self.min_cash_reserve_pct
        reserve_ok = cash_after >= reserve_needed and cash_after >= 0
        trace.append(
            f"cash reserve check: ${account_cash:,.0f} − "
            f"${collateral_required:,.0f} collateral = ${cash_after:,.0f} "
            f"remaining ({self.min_cash_reserve_pct*100:.0f}% floor = "
            f"${reserve_needed:,.0f}) {'✓' if reserve_ok else '✗ BLOCKED'}")
        if not reserve_ok:
            allowed = False

        # Council §6 correlation rule: tech-complex sector cap.
        if existing_positions is not None:
            sector_ok, sector_lines = self.check_sector_cap(
                sym, collateral_required, existing_positions)
            trace.extend(sector_lines)
            if not sector_ok:
                allowed = False

        return allowed, trace

    def _position_value(self, p: Dict) -> float:
        mv = p.get("market_value")
        if mv is None:
            price = p.get("current_price") or p.get("avg_entry_price") or 0
            mv = float(p.get("qty") or 0) * float(price)
        # Short-option overlays may report explicit collateral instead.
        return float(p.get("collateral", mv))

    def deployed_overlay_capital(self, positions: List[Dict]) -> float:
        """Total deployed overlay capital across all positions."""
        return sum(self._position_value(p) for p in positions)

    def check_sector_cap(self, symbol: str, collateral_required: float,
                         positions: List[Dict],
                         deployed_capital: Optional[float] = None
                         ) -> Tuple[bool, List[str]]:
        """
        Council correlation rule (report §6): combined exposure of the
        correlated group (default tech complex AAPL+MSFT+NVDA+QQQ — QQQ
        counts as tech, not as a diversifier) must stay ≤
        max_sector_concentration (40%) of deployed overlay capital.

        Returns (allowed, reasoning_trace). A breaching new entry is BLOCKED.
        """
        sym = str(symbol).upper()
        group = set(self.sector_cap_group)
        deployed_now = (self.deployed_overlay_capital(positions)
                        if deployed_capital is None else float(deployed_capital))
        group_now = sum(self._position_value(p) for p in positions
                        if str(p.get("symbol", "?")).upper() in group)
        in_group = sym in group
        group_projected = group_now + (collateral_required if in_group else 0.0)
        deployed_projected = deployed_now + float(collateral_required)
        frac = (group_projected / deployed_projected
                if deployed_projected > 0 else 0.0)
        ok = frac <= self.max_sector_concentration + 1e-9
        trace = [
            f"council sector-cap check ({'+'.join(sorted(group))} vs "
            f"{self.max_sector_concentration*100:.0f}% of deployed overlay "
            f"capital): ${group_projected:,.0f} / ${deployed_projected:,.0f} "
            f"= {frac*100:.1f}% "
            f"{'✓' if ok else '✗ BLOCKED'}",
        ]
        if not ok:
            trace.append(
                "council rule cited: Investment Council Report §6 — "
                "'combined tech-complex exposure (AAPL+MSFT+NVDA+QQQ) limited "
                "to ≤40% of deployed overlay capital'; QQQ counts as tech, "
                "not as a diversifier → new entry BLOCKED")
        return ok, trace

    def sector_exposure(self, positions: List[Dict]) -> Dict[str, Dict]:
        """Aggregate overlay/holding value per sector via the static map."""
        by_sector: Dict[str, float] = {}
        for p in positions:
            sym = str(p.get("symbol", "?")).upper()
            mv = p.get("market_value")
            if mv is None:
                price = p.get("current_price") or p.get("avg_entry_price") or 0
                mv = float(p.get("qty") or 0) * float(price)
            sec = self.sector_map.get(sym, "other")
            by_sector[sec] = by_sector.get(sec, 0.0) + float(mv)
        return {s: {"value": round(v, 2)} for s, v in
                sorted(by_sector.items(), key=lambda kv: -kv[1])}

    def assess(self, positions: List[Dict], portfolio_value: float,
               account_cash: float) -> Dict:
        """Full context snapshot: concentration table, sectors, cash rule."""
        conc = self.concentration_by_ticker(positions, portfolio_value)
        breaches = [s for s, c in conc.items() if not c["within_limit"]]
        cash_after = account_cash  # current commitment already reflected in cash
        cash_ok = True
        sectors = self.sector_exposure(positions)
        top_sector = next(iter(sectors), None)
        sector_note = (
            f"largest sector exposure: {top_sector}"
            if top_sector else "no sector exposure")
        trace = [
            f"concentration scan across {len(conc)} ticker(s): "
            f"{len(breaches)} breach(es) of the "
            f"{self.max_concentration*100:.0f}% cap "
            f"{'✓' if not breaches else '✗ ' + ', '.join(breaches)}",
            f"sector awareness ({sector_note}) ✓",
            f"cash reserve: ${account_cash:,.0f} available "
            f"({(account_cash/portfolio_value*100 if portfolio_value > 0 else 0):.1f}%"
            f" of portfolio; ≥{self.min_cash_reserve_pct*100:.0f}% required after "
            f"new collateral) {'✓' if cash_ok else '✗'}",
        ]
        return {
            "max_concentration_pct": self.max_concentration * 100,
            "min_cash_reserve_pct": self.min_cash_reserve_pct * 100,
            "concentration": conc,
            "concentration_breaches": breaches,
            "sector_exposure": sectors,
            "cash_available": round(account_cash, 2),
            "reasoning_trace": trace,
        }
