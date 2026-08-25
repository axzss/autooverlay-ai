"""
Cash-Secured Put Screening Strategy.

Pure logic: takes a list of put-option dicts (option-chain snapshot) and an
account-cash figure and returns ranked recommendations. No I/O.

Criteria:
- Put |delta| between MIN_DELTA and MAX_DELTA (default 0.15-0.35).
- DTE within [min_dte, max_dte].
- Strike below cost basis where the underlying is held (prefer getting paid
  to buy more below what you already pay); otherwise strike below spot (OTM).
- Cash requirement: strike * 100 <= available cash per contract.
- Ranked by annualized cash-secured yield (premium / strike * 365 / DTE).

Each output row carries an explicit integer risk score 0-100 and a written
rationale for the recommendation label.
"""

from typing import Dict, List
from datetime import datetime


class CashSecuredPutStrategy:
    MIN_DELTA = 0.15
    MAX_DELTA = 0.35

    def __init__(
        self,
        min_dte: int = 7,
        max_dte: int = 45,
        min_delta: float = MIN_DELTA,
        max_delta: float = MAX_DELTA,
        min_annualized_yield: float = 0.12,
        good_annualized_yield: float = 0.25,
        max_risk_for_entry: int = 60,
    ):
        self.min_dte = min_dte
        self.max_dte = max_dte
        self.min_delta = min_delta
        self.max_delta = max_delta
        self.min_annualized_yield = min_annualized_yield
        self.good_annualized_yield = good_annualized_yield
        self.max_risk_for_entry = max_risk_for_entry

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #
    def screen(self, opportunities: List[Dict], account_cash: float,
               positions: List[Dict] | None = None,
               as_of: datetime | None = None) -> List[Dict]:
        """
        Screen candidate put contracts against cash availability and,
        optionally, existing holdings' cost basis.

        Returns recommendations sorted by annualized yield, desc.
        """
        as_of = as_of or datetime.utcnow()
        basis_by_symbol = {
            p["symbol"]: float(p.get("avg_entry_price") or 0)
            for p in (positions or []) if p.get("symbol")
        }

        results: List[Dict] = []
        for opp in opportunities:
            dte = self._dte(opp, as_of)
            if dte is None or not (self.min_dte <= dte <= self.max_dte):
                continue

            delta = abs(float(opp.get("delta") or 0))
            if not (self.min_delta <= delta <= self.MAX_DELTA):
                continue

            underlying = float(opp.get("underlying_price") or 0)
            strike = float(opp.get("strike_price") or 0)
            premium = self._premium(opp)
            if strike <= 0 or premium <= 0:
                continue

            cash_required = strike * 100.0
            contracts_affordable = int(account_cash // cash_required) if cash_required > 0 else 0
            if contracts_affordable < 1:
                continue

            symbol = opp.get("symbol")
            cost_basis = basis_by_symbol.get(symbol, 0.0)
            strike_below_basis = strike < cost_basis if cost_basis > 0 else None
            otm = strike < underlying if underlying > 0 else None

            ann_yield = (premium / strike) * (365.0 / dte)
            risk_score = self._risk_score(
                iv=float(opp.get("implied_volatility") or 0), delta=delta,
                dte=dte, underlying=underlying, strike=strike,
                strike_below_basis=strike_below_basis,
            )
            recommendation = self._recommendation(ann_yield, risk_score)
            rationale = self._rationale(
                symbol=symbol, strike=strike, dte=dte, delta=delta,
                premium=premium, ann_yield=ann_yield, risk_score=risk_score,
                strike_below_basis=strike_below_basis, otm=otm,
                contracts=contracts_affordable, recommendation=recommendation,
                iv=float(opp.get("implied_volatility") or 0),
            )

            results.append({
                "strategy": "CASH_SECURED_PUT",
                "symbol": symbol,
                "option_symbol": opp.get("option_symbol"),
                "contracts": contracts_affordable,
                "cash_required": round(cash_required, 2),
                "strike_price": strike,
                "expiration_date": opp.get("expiration_date"),
                "dte": dte,
                "delta": round(delta, 3),
                "implied_volatility": round(float(opp.get("implied_volatility") or 0), 4),
                "premium_per_share": round(premium, 2),
                "annualized_premium_yield": round(ann_yield, 4),
                "strike_below_cost_basis": strike_below_basis,
                "risk_score": risk_score,
                "recommendation": recommendation,
                "rationale": rationale,
            })

        return sorted(results, key=lambda r: r["annualized_premium_yield"], reverse=True)

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _dte(opp: Dict, as_of: datetime) -> int | None:
        dte = opp.get("days_to_expiry") or opp.get("dte")
        if dte is not None:
            return int(dte)
        exp = opp.get("expiration_date")
        if not exp:
            return None
        try:
            expiry = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            naive_expiry = expiry.replace(tzinfo=None)
            return (naive_expiry - as_of.replace(tzinfo=None)).days
        except ValueError:
            return None

    @staticmethod
    def _premium(opp: Dict) -> float:
        for key in ("premium_received_per_share", "last_price"):
            if opp.get(key):
                return float(opp[key])
        bid, ask = opp.get("bid"), opp.get("ask")
        if bid is not None and ask is not None:
            return (float(bid) + float(ask)) / 2.0
        return 0.0

    def _risk_score(self, *, iv: float, delta: float, dte: int,
                    underlying: float, strike: float,
                    strike_below_basis: bool | None) -> int:
        """Composite risk 0-100 (higher = riskier). Deterministic."""
        score = 0.0
        # IV: up to 30 pts (50% IV -> max). Elevated IV raises assignment odds.
        score += min(iv / 0.50, 1.0) * 30
        # Delta proximity to the money: up to 25 pts.
        score += min((delta - self.MIN_DELTA) / (self.MAX_DELTA - self.MIN_DELTA), 1.0) * 25
        # Short-dated gamma risk: up to 20 pts (<21 DTE ramps up).
        score += min(max(0.0, (21 - dte) / 21), 1.0) * 20
        # Strike above cost basis means buying more ABOVE what you already pay: up to 15 pts.
        if strike_below_basis is False:
            score += 15
        # Thin cushion (<3% OTM): up to 10 pts.
        if underlying > 0:
            cushion = (underlying - strike) / underlying
            score += min(max(0.0, (0.03 - cushion) / 0.03), 1.0) * 10
        return int(round(min(score, 100)))

    def _recommendation(self, ann_yield: float, risk_score: int) -> str:
        if ann_yield >= self.good_annualized_yield and risk_score <= self.max_risk_for_entry:
            return "INITIATE_POSITION"
        if ann_yield >= self.min_annualized_yield and risk_score <= 75:
            return "HOLD_POSITION"
        return "MONITOR_CLOSELY"

    @staticmethod
    def _rationale(**kw) -> str:
        basis_txt = (
            "below your cost basis (accumulating at a discount)"
            if kw["strike_below_basis"] else
            "ABOVE your cost basis (would add shares above current average)"
            if kw["strike_below_basis"] is False else
            "with no existing position to compare basis"
        )
        otm_txt = ("out-of-the-money" if kw["otm"] else "in-the-money"
                   if kw["otm"] is False else "moneyness unknown")
        return (
            f"{kw['symbol']}: sell {kw['contracts']} cash-secured put(s) at ${kw['strike']:.2f} "
            f"({basis_txt}, {otm_txt}), {kw['dte']} DTE, |delta| {kw['delta']:.2f}. "
            f"Premium ${kw['premium']:.2f}/share = {kw['ann_yield']*100:.1f}% annualized "
            f"cash-secured yield; ${kw['strike']*100:,.0f} collateral per contract. "
            f"Risk score {kw['risk_score']}/100 (IV {kw['iv']*100:.0f}%, gamma near expiry, cushion). "
            f"=> {kw['recommendation']}"
        )
