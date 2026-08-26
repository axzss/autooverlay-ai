"""
CouncilEngine — runs all six personas over candidate underlyings and
aggregates weighted consensus, split detection, dissent reports, and a
final overlay-suitability recommendation per underlying.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .personas import PERSONAS, DEFAULT_WEIGHTS, PersonaVerdict
from .mr_market import mr_market_context


RECOMMENDATIONS = ("STRONG_BUY", "ACCUMULATE", "HOLD", "AVOID")


def _recommendation(consensus: float) -> str:
    if consensus >= 75:
        return "STRONG_BUY"
    if consensus >= 60:
        return "ACCUMULATE"
    if consensus >= 40:
        return "HOLD"
    return "AVOID"


@dataclass
class UnderlyingAssessment:
    symbol: str
    verdicts: dict[str, PersonaVerdict]          # persona key -> verdict
    consensus_score: float                        # weighted 0-100
    recommendation: str                           # STRONG_BUY..AVOID
    majority_stance: str                          # ACCUMULATE / HOLD / AVOID bucket label
    is_split: bool                                # no clear majority (>=2 stances tie-ish)
    dissent: list[dict] = field(default_factory=list)
    mr_market_context: dict | None = None         # Ch. 8 market-mood regime signal

    @property
    def bullish_count(self) -> int:
        return sum(1 for v in self.verdicts.values() if v.is_bullish)

    @property
    def bearish_count(self) -> int:
        return sum(1 for v in self.verdicts.values() if v.is_bearish)


class CouncilEngine:
    def __init__(self, weights: dict[str, float] | None = None,
                 contrarian_keys: tuple[str, ...] = ("wood",)):
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.contrarian_keys = contrarian_keys

    # ------------------------------------------------------------------ #
    def assess_underlying(self, underlying: dict) -> UnderlyingAssessment:
        symbol = underlying.get("symbol", "?")
        verdicts: dict[str, PersonaVerdict] = {}
        for key, persona in PERSONAS.items():
            try:
                verdicts[key] = persona.score(underlying)
            except Exception as exc:  # never let one persona kill the council
                verdicts[key] = PersonaVerdict(
                    persona.name, 50.0, "HOLD",
                    [f"persona scoring error ({exc.__class__.__name__}) — neutral abstention"])

        total_w = sum(self.weights.get(k, 1.0) for k in verdicts)
        consensus = sum(v.score * self.weights.get(k, 1.0)
                        for k, v in verdicts.items()) / max(total_w, 1e-9)

        rec = _recommendation(consensus)

        # Majority / minority stance buckets
        def bucket(v: PersonaVerdict) -> str:
            if v.is_bullish:
                return "ACCUMULATE+"
            if v.is_bearish:
                return "AVOID-"
            return "HOLD"

        buckets: dict[str, list[str]] = {}
        for k, v in verdicts.items():
            buckets.setdefault(bucket(v), []).append(k)
        majority_stance = max(buckets, key=lambda b: len(buckets[b]))
        sorted_sizes = sorted((len(v) for v in buckets.values()), reverse=True)
        is_split = len(buckets) > 1 and (
            len(sorted_sizes) < 2 or sorted_sizes[0] == sorted_sizes[1]
            or len(buckets[majority_stance]) * 2 <= len(verdicts))

        # Dissent report: contrarian personas vs consensus
        dissent: list[dict] = []
        for ck in self.contrarian_keys:
            v = verdicts.get(ck)
            if v is None:
                continue
            if v.is_bullish and consensus < 55:
                dissent.append({
                    "persona": v.persona, "direction": "bullish-dissent",
                    "score": v.score, "consensus": consensus,
                    "why": v.bullets})
            elif v.score - consensus >= 15:
                dissent.append({
                    "persona": v.persona, "direction": "bullish-dissent",
                    "score": v.score, "consensus": consensus,
                    "why": v.bullets})
            elif not v.is_bullish and consensus >= 65:
                dissent.append({
                    "persona": v.persona, "direction": "bearish-dissent",
                    "score": v.score, "consensus": consensus,
                    "why": v.bullets})
            elif consensus - v.score >= 15:
                dissent.append({
                    "persona": v.persona, "direction": "bearish-dissent",
                    "score": v.score, "consensus": consensus,
                    "why": v.bullets})

        # Also flag any persona >20 points away from consensus as minority voice
        for k, v in verdicts.items():
            if k in self.contrarian_keys:
                continue
            if abs(v.score - consensus) >= 20:
                direction = "bearish-minority" if v.score < consensus else "bullish-minority"
                if v.is_bullish != (consensus >= 60):
                    dissent.append({
                        "persona": v.persona, "direction": direction,
                        "score": v.score, "consensus": consensus,
                        "why": v.bullets})

        return UnderlyingAssessment(symbol, verdicts, round(consensus, 1),
                                    rec, majority_stance.rstrip("+-") or "HOLD",
                                    is_split, dissent,
                                    mr_market_context=mr_market_context(underlying))

    # ------------------------------------------------------------------ #
    def run(self, portfolio: dict, candidates: list[dict]) -> list[UnderlyingAssessment]:
        """portfolio: snapshot dict (positions, cash, sector weights, macro inputs).
        candidates: list of underlying dicts (symbol + fundamentals + macro fields)."""
        macro_ctx = {k: v for k, v in portfolio.items()
                     if k.startswith("macro_") or k == "annualized_volatility_pct"}
        enriched = []
        for c in candidates:
            u = dict(c)
            for k, v in macro_ctx.items():
                u.setdefault(k, v)
            # per-symbol realized vol from positions if present
            pos = {p.get("symbol"): p for p in portfolio.get("positions", [])}
            ps = pos.get(u.get("symbol"), {})
            u.setdefault("annualized_volatility_pct", ps.get("annualized_volatility_pct"))
            u.setdefault("moat", ps.get("moat"))
            enriched.append(u)
        return [self.assess_underlying(u) for u in enriched]
