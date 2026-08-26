"""
Covered Call Screening Strategy.

Pure logic: takes a list of position dicts (Alpaca-style) and a list of
call-option dicts (option-chain snapshot) and returns ranked recommendations.
No I/O, no API calls -- fully deterministic and testable.

Criteria:
- Underlying must be held in whole 100-share lots (one contract per lot).
- Call delta between MIN_DELTA and MAX_DELTA (default 0.15-0.35).
- DTE within [min_dte, max_dte].
- Strike above cost basis preferred (assignment at or above basis avoids loss).
- Ranked by annualized premium yield (premium / underlying_price * 365 / DTE).

Each output row carries an explicit integer risk score 0-100 and a written
rationale for the recommendation label.
"""

from typing import Dict, List
from datetime import datetime

try:
    from ..config import StrategyConfig
except ImportError:  # pragma: no cover - direct-script imports
    from config import StrategyConfig


class CoveredCallStrategy:
    MIN_DELTA = 0.15
    MAX_DELTA = 0.35

    def __init__(
        self,
        min_dte: "int | None" = None,
        max_dte: "int | None" = None,
        min_delta: "float | None" = None,
        max_delta: "float | None" = None,
        min_annualized_yield: float = 0.12,
        good_annualized_yield: float = 0.25,
        config: "StrategyConfig | None" = None,
        tier_policy: "dict | object | None" = None,
    ):
        """
        ``tier_policy``: optional council volatility-tier policy (a
        ``agent.council.handoff.TierPolicy`` or an equivalent dict). When
        given, its delta band / DTE ceiling / size multiplier take effect
        unless explicitly overridden by the matching keyword args; explicit
        args and StrategyConfig defaults still win otherwise.
        """
        cfg = config or StrategyConfig()
        pol = self._normalize_policy(tier_policy)
        self.tier_policy = pol
        # Precedence: explicit arg > tier policy > StrategyConfig defaults.
        self.min_dte = min_dte if min_dte is not None else (
            pol["dte_min"] if pol and pol.get("dte_min") else cfg.dte_min)
        self.max_dte = max_dte if max_dte is not None else (
            pol["max_dte"] if pol else cfg.dte_max)
        self.min_delta = min_delta if min_delta is not None else (
            pol["delta_min"] if pol else cfg.delta_min)
        self.max_delta = max_delta if max_delta is not None else (
            pol["delta_max"] if pol else cfg.delta_max)
        self.size_multiplier = float(pol.get("size_multiplier", 1.0)) if pol else 1.0
        self.min_annualized_yield = min_annualized_yield
        self.good_annualized_yield = good_annualized_yield

    @staticmethod
    def _normalize_policy(tier_policy) -> "dict | None":
        """Accept a TierPolicy dataclass or a plain dict; return dict or None."""
        if tier_policy is None:
            return None
        if hasattr(tier_policy, "to_dict"):
            tier_policy = tier_policy.to_dict()
        try:
            allowed = tuple(s.upper() for s in
                            tier_policy.get("allowed_strategies", ()))
        except AttributeError:
            allowed = ()
        return {
            "delta_min": float(tier_policy.get("delta_min", 0.15)),
            "delta_max": float(tier_policy.get("delta_max", 0.35)),
            "max_dte": int(tier_policy.get("max_dte", 45)),
            "size_multiplier": float(tier_policy.get("size_multiplier", 1.0)),
            "allowed_strategies": allowed,
        }

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #
    def screen(self, opportunities: List[Dict], positions: List[Dict],
               as_of: datetime | None = None) -> List[Dict]:
        """
        Match candidate call contracts against holdings.

        Parameters
        ----------
        opportunities : list of option-chain dicts. Recognized keys:
            symbol, underlying_price, strike_price, expiration_date and/or
            days_to_expiry, bid/ask/last_price/premium_received_per_share,
            delta (call delta, sign agnostic via abs()), implied_volatility.
        positions : list of Alpaca-style position dicts
            (symbol, qty, avg_entry_price).
        as_of : optional reference time for DTE computation (testability).

        Returns recommendations sorted by annualized premium yield, desc.
        """
        as_of = as_of or datetime.utcnow()
        holdings = {
            p["symbol"]: p for p in positions if float(p.get("qty", 0)) > 0
        }

        results: List[Dict] = []
        for opp in opportunities:
            symbol = opp.get("symbol")
            pos = holdings.get(symbol)
            if not pos:
                continue

            qty = int(float(pos["qty"]))
            lots = qty // 100
            if lots < 1:
                continue  # cannot write a covered call without a full lot

            # Council tier size multiplier (restricted tiers write fewer lots).
            contracts = max(1, int(lots * self.size_multiplier))

            # Council tier gate: block if this tier disallows covered calls.
            if (self.tier_policy
                    and "COVERED_CALL" not in
                    self.tier_policy["allowed_strategies"]):
                results.append({
                    "strategy": "COVERED_CALL",
                    "symbol": symbol,
                    "option_symbol": opp.get("option_symbol"),
                    "contracts": 0,
                    "strike_price": float(opp.get("strike_price") or 0),
                    "expiration_date": opp.get("expiration_date"),
                    "recommendation": "BLOCKED_BY_COUNCIL_TIER",
                    "rationale": (
                        f"{symbol}: covered call blocked — council handoff "
                        f"restricts this volatility tier to "
                        f"{','.join(self.tier_policy['allowed_strategies'])} "
                        f"only."),
                    "reasoning_trace": [
                        f"council tier gate: allowed strategies = "
                        f"{','.join(self.tier_policy['allowed_strategies'])}; "
                        f"covered call not permitted → ✗ BLOCKED",
                        "council rule cited: Investment Council Report §8 "
                        "HANDOFF eligibility table",
                    ],
                })
                continue

            dte = self._dte(opp, as_of)
            if dte is None or not (self.min_dte <= dte <= self.max_dte):
                continue

            delta = abs(float(opp.get("delta") or 0))
            if not (self.min_delta <= delta <= self.max_delta):
                continue

            underlying = float(opp.get("underlying_price") or 0)
            strike = float(opp.get("strike_price") or 0)
            premium = self._premium(opp)
            if underlying <= 0 or strike <= 0 or premium <= 0:
                continue

            cost_basis = float(pos.get("avg_entry_price") or 0)
            strike_above_basis = strike >= cost_basis if cost_basis > 0 else None

            ann_yield = (premium / underlying) * (365.0 / dte)

            risk_score = self._risk_score(
                iv=float(opp.get("implied_volatility") or 0),
                delta=delta, dte=dte, underlying=underlying, strike=strike,
                strike_above_basis=strike_above_basis,
            )
            recommendation = self._recommendation(ann_yield, risk_score)

            reasoning_trace = [
                f"holding check: {qty} shares of {symbol} = {lots} full lot(s) ✓",
                f"DTE {dte} within {self.min_dte}-{self.max_dte} band ✓",
                f"delta {delta:.2f} within {self.min_delta:.2f}-"
                f"{self.max_delta:.2f} band ✓",
                *( [f"council tier sizing: size multiplier x{self.size_multiplier} "
                    f"applied → {contracts} contract(s) of {lots} available lot(s)"]
                   if self.size_multiplier < 1 else [] ),
                f"premium ${premium:.2f}/share → annualized yield "
                f"{ann_yield*100:.1f}% (floor {self.min_annualized_yield*100:.0f}%) "
                f"{'✓' if ann_yield >= self.min_annualized_yield else '✗'}",
                f"strike ${strike:.2f} vs cost basis ${cost_basis:.2f}: "
                + ("above basis — assignment is neutral-to-profitable ✓"
                   if strike_above_basis else
                   "BELOW basis — assignment would realize a loss ✗ (+15 risk)"
                   if strike_above_basis is False else
                   "cost basis unknown"),
                f"risk score {risk_score}/100 from IV, delta, DTE gamma, "
                f"basis and cushion components",
                f"verdict: {recommendation}",
            ]

            rationale = self._rationale(
                symbol=symbol, strike=strike, dte=dte, delta=delta,
                premium=premium, ann_yield=ann_yield,
                strike_above_basis=strike_above_basis, risk_score=risk_score,
                lots=lots, recommendation=recommendation,
                iv=float(opp.get("implied_volatility") or 0),
            )

            results.append({
                "strategy": "COVERED_CALL",
                "symbol": symbol,
                "option_symbol": opp.get("option_symbol"),
                "contracts": contracts,
                "tier_size_multiplier": self.size_multiplier,
                "shares_covered": contracts * 100,
                "strike_price": strike,
                "expiration_date": opp.get("expiration_date"),
                "dte": dte,
                "delta": round(delta, 3),
                "implied_volatility": round(float(opp.get("implied_volatility") or 0), 4),
                "premium_per_share": round(premium, 2),
                "total_premium": round(premium * 100 * contracts, 2),
                "annualized_premium_yield": round(ann_yield, 4),
                "strike_above_cost_basis": strike_above_basis,
                "risk_score": risk_score,
                "recommendation": recommendation,
                "rationale": rationale,
                "reasoning_trace": reasoning_trace,
            })

        return sorted(results, key=lambda r: r.get("annualized_premium_yield", 0), reverse=True)

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
                    strike_above_basis: bool | None) -> int:
        """Composite risk 0-100 (higher = riskier). Deterministic."""
        score = 0.0
        # IV: up to 30 pts (50% IV -> max)
        score += min(iv / 0.50, 1.0) * 30
        # Delta proximity to the money: up to 25 pts (delta 0.35 -> max)
        score += min((delta - self.MIN_DELTA) / (self.MAX_DELTA - self.MIN_DELTA), 1.0) * 25
        # Short-dated gamma risk: up to 20 pts (<21 DTE ramps up)
        score += min(max(0.0, (21 - dte) / 21), 1.0) * 20
        # Assignment below cost basis locks a loss on called shares: up to 15 pts
        if strike_above_basis is False:
            score += 15
        # Thin cushion to strike (<3% OTM): up to 10 pts
        otm_pct = (strike - underlying) / underlying
        score += min(max(0.0, (0.03 - otm_pct) / 0.03), 1.0) * 10
        return int(round(min(score, 100)))

    def _recommendation(self, ann_yield: float, risk_score: int) -> str:
        if ann_yield >= self.good_annualized_yield and risk_score <= 60:
            return "INITIATE_POSITION"
        if ann_yield >= self.min_annualized_yield and risk_score <= 75:
            return "HOLD_POSITION"
        return "MONITOR_CLOSELY"

    @staticmethod
    def _rationale(**kw) -> str:
        basis_txt = ("above your cost basis"
                     if kw["strike_above_basis"] else
                     "BELOW your cost basis (assignment would realize a loss)"
                     if kw["strike_above_basis"] is not None else
                     "with unknown cost-basis comparison")
        return (
            f"{kw['symbol']}: sell {kw['lots']} covered call(s) at ${kw['strike']:.2f} "
            f"({basis_txt}), {kw['dte']} DTE, delta {kw['delta']:.2f}. "
            f"Premium ${kw['premium']:.2f}/share = {kw['ann_yield']*100:.1f}% annualized "
            f"yield. Risk score {kw['risk_score']}/100 "
            f"(IV {kw.get('iv', 0)*100:.0f}%, short-dated gamma, cushion to strike). "
            f"=> {kw['recommendation']}"
        )
