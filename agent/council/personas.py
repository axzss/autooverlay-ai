"""
Investment Council — six analyst personas with documented philosophies.

Each persona exposes a ``score(underlying) -> PersonaVerdict`` function that
takes a plain dict of fundamental/market data and returns a 0-100 score plus
bullet rationales. All inputs are optional; personas degrade gracefully when
data is missing (missing input -> neutral contribution, noted in rationale).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field


@dataclass
class PersonaVerdict:
    persona: str
    score: float          # 0-100
    stance: str           # STRONG_BUY / ACCUMULATE / HOLD / AVOID
    bullets: list[str] = field(default_factory=list)

    @property
    def is_bullish(self) -> bool:
        return self.score >= 60

    @property
    def is_bearish(self) -> bool:
        return self.score < 40


def _stance(score: float) -> str:
    if score >= 75:
        return "STRONG_BUY"
    if score >= 60:
        return "ACCUMULATE"
    if score >= 40:
        return "HOLD"
    return "AVOID"


def _get(u: dict, key: str):
    v = u.get(key)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _blend(parts: list[tuple[float | None, float]]) -> tuple[float, list[str]]:
    """Weighted mean over (value, weight) pairs, skipping None values.
    Returns (score, notes about skipped components)."""
    total_w = sum(w for v, w in parts if v is not None)
    if total_w == 0:
        return 50.0, ["insufficient data — neutral default"]
    score = sum(v * w for v, w in parts if v is not None) / total_w
    skipped = [n for (v, w), n in [] ]  # placeholder, unused
    return _clip(score), skipped


# --------------------------------------------------------------------------- #
# Personas                                                                    #
# --------------------------------------------------------------------------- #

class WarrenBuffett:
    """Warren Buffett — buy wonderful businesses at fair prices.

    Philosophy: durable economic moat, consistent owner-earnings, low debt,
    honest management, and only businesses an intelligent layperson can
    understand. Time horizon: forever. Would rather own a great company at a
    good price than a fair company at a great price.
    """
    name = "Warren Buffett"
    philosophy = (
        "Durable moat + consistent earnings + low leverage + circle of "
        "competence. Buy and hold forever; the business does the work."
    )
    known_sectors = {"technology", "consumer", "financials", "industrials", "energy"}

    def score(self, u: dict) -> PersonaVerdict:
        bullets: list[str] = []
        parts: list[tuple[float | None, float]] = []

        moat = u.get("moat")  # "wide" | "narrow" | "none"
        if moat == "wide":
            parts.append((90, 3)); bullets.append("Wide durable moat — pricing power for decades.")
        elif moat == "narrow":
            parts.append((65, 2)); bullets.append("Narrow moat — some protection but erodible.")
        else:
            parts.append((35, 2)); bullets.append("No identifiable moat — commodity dynamics.")

        margin = _get(u, "operating_margin_pct")
        if margin is not None:
            s = _clip(margin * 4)  # 25% margin -> ~100
            parts.append((s, 2))
            bullets.append(f"Operating margin {margin:.1f}% — {'owner-earnings machine' if margin >= 20 else 'adequate' if margin >= 12 else 'thin'}.")
        else:
            bullets.append("Margins unavailable.")

        de = _get(u, "debt_to_equity")
        if de is not None:
            s = _clip(100 - de * 100)
            parts.append((s, 1))
            bullets.append(f"Debt/equity {de:.2f} — {'fortress balance sheet' if de < 0.5 else 'acceptable' if de < 1.5 else 'too much leverage'}.")
        else:
            bullets.append("Leverage data missing.")

        growth = _get(u, "earnings_growth_5y_pct")
        if growth is not None:
            s = _clip(50 + growth * 2)
            parts.append((s, 1))
            bullets.append(f"5y earnings growth {growth:+.1f}%/yr — consistency check {'passes' if growth > 5 else 'marginal'}.")
        else:
            bullets.append("Long-run earnings history missing.")

        sector = str(u.get("sector", "")).lower()
        if sector and sector not in self.known_sectors:
            parts.append((30, 3))
            bullets.append(f"Sector '{sector}' outside my circle of competence — hard pass regardless of numbers.")
        else:
            parts.append((80, 1)); bullets.append(f"{u.get('symbol','?')}: understandable business I could hold for decades.")

        score, _ = _blend(parts)
        return PersonaVerdict(self.name, score, _stance(score), bullets)


class CharlieMunger:
    """Charlie Munger — quality over price; invert, always invert.

    Philosophy: pay up for proven quality rather than hunt statistical
    bargains. Use inversion ("what kills this position?"), multidisciplinary
    mental models (incentives, feedback loops, second-order effects), and a
    small concentrated book. A great business at a fair price beats a fair
    business at a great price.
    """
    name = "Charlie Munger"
    philosophy = (
        "Quality-over-price, inversion ('what kills this position?'), "
        "mental-model checks on incentives, competition, and fragility."
    )

    def score(self, u: dict) -> PersonaVerdict:
        bullets: list[str] = []
        parts: list[tuple[float | None, float]] = []

        roe = _get(u, "roe_pct")
        if roe is not None:
            s = _clip(roe * 2.5)
            parts.append((s, 3))
            bullets.append(f"ROE {roe:.0f}% — {'compounding quality' if roe >= 18 else 'middling capital efficiency'}.")
        else:
            bullets.append("ROE missing — can't verify quality.")

        gross_m = _get(u, "gross_margin_pct")
        if gross_m is not None:
            parts.append((_clip(gross_m * 1.6), 2))
            bullets.append(f"Gross margin {gross_m:.0f}% signals brand/product strength." if gross_m >= 40 else f"Gross margin {gross_m:.0f}% — thin evidence of franchise.")
        else:
            bullets.append("Gross margin missing.")

        # Inversion: what kills this position?
        kill_risks: list[str] = []
        pe = _get(u, "pe_ratio")
        if pe is not None and pe > 45:
            parts.append((35, 2))
            kill_risks.append(f"P/E {pe:.0f}x leaves no room for disappointment")
        disruption = u.get("disruption_risk")  # "high"|"medium"|"low"
        if disruption == "high":
            parts.append((40, 2))
            kill_risks.append("explicit disruption risk — incumbency is fragile")
        concentration = _get(u, "customer_concentration_pct")
        if concentration is not None and concentration > 40:
            parts.append((45, 1))
            kill_risks.append(f"{concentration:.0f}% customer concentration — incentive trap waiting to fire")
        if kill_risks:
            bullets.append("Inversion — what kills this position: " + "; ".join(kill_risks) + ".")
        else:
            bullets.append("Inversion found no obvious position-killer in available data.")
            parts.append((75, 1))

        # Mental model: incentives / management
        insider_own = _get(u, "insider_ownership_pct")
        if insider_own is not None:
            aligned = insider_own >= 5
            parts.append((80 if aligned else 55, 1))
            bullets.append(f"Incentives: insider ownership {insider_own:.0f}% — skin {'in the game' if aligned else 'is modest'}.")

        score, _ = _blend(parts)
        return PersonaVerdict(self.name, score, _stance(score), bullets)


class RayDalio:
    """Ray Dalio — macro regime first; risk parity; diversify.

    Philosophy: returns are mostly explained by the macro environment
    (growth/inflation/rates regimes). Size positions by risk, not dollars,
    and never let one sector dominate. Cash-flow generation and balance-sheet
    resilience matter more than narrative across regimes.
    """
    name = "Ray Dalio"
    philosophy = (
        "Macro-regime awareness (rate & inflation proxy inputs), risk-parity "
        "sizing logic, diversification across sectors as the first defense."
    )

    def score(self, u: dict) -> PersonaVerdict:
        bullets: list[str] = []
        parts: list[tuple[float | None, float]] = []

        rate_env = u.get("macro_rate_regime", "neutral")   # rising|falling|neutral
        infl = _get(u, "macro_inflation_pct")

        dur = _get(u, "duration_sensitivity") or _get(u, "beta")
        if dur is not None:
            if rate_env == "rising":
                s = _clip(70 - dur * 15)
                bullets.append(f"Rising-rate regime with duration/beta {dur:.1f} — penalize long-duration exposure.")
            elif rate_env == "falling":
                s = _clip(55 + dur * 10)
                bullets.append(f"Falling rates favor duration/growth assets (duration proxy {dur:.1f}).")
            else:
                s = 60.0
                bullets.append("Neutral rate regime — duration less decisive.")
            parts.append((s, 2))

        if infl is not None:
            if infl > 5:
                s = 45 if u.get("pricing_power") != "wide" else 65
                bullets.append(f"Inflation {infl:.1f}% — {'real-asset/pricing-power names hold up better' if s==65 else 'cash-flow-heavy, low-pricing-power names get squeezed'}.")
            elif infl < 2:
                s = 70
                bullets.append(f"Inflation {infl:.1f}% — benign; nominal equities fine.")
            else:
                s = 62
                bullets.append(f"Inflation {infl:.1f}% — moderate, manageable.")
            parts.append((s, 2))

        fcf = _get(u, "free_cash_flow_yield_pct")
        if fcf is not None:
            parts.append((_clip(50 + fcf * 5), 2))
            bullets.append(f"FCF yield {fcf:.1f}% provides all-weather cash flow.")

        div = u.get("portfolio_sector_concentration_pct")  # largest sector weight
        if isinstance(div, (int, float)) and not isinstance(div, bool):
            if div > 40:
                parts.append((35, 2))
                bullets.append(f"Largest sector at {div:.0f}% of portfolio — violates diversification; trim bias.")
            else:
                parts.append((72, 1))
                bullets.append(f"Sector spread acceptable (largest {div:.0f}%).")

        vol = _get(u, "annualized_volatility_pct")
        if vol is not None:
            rp_ok = vol <= 30
            parts.append((70 if rp_ok else 48, 1))
            bullets.append(f"Realized vol {vol:.0f}% — {'risk-parity friendly' if rp_ok else 'risk budget hog; size down'}.")

        score, _ = _blend(parts)
        if not bullets:
            bullets = ["No macro inputs supplied — assuming neutral regime."]
        return PersonaVerdict(self.name, score, _stance(score), bullets)


class BenjaminGraham:
    """Benjamin Graham — margin of safety as the central concept (Ch. 20),
    scored against the seven defensive-investor tests of Ch. 14.

    Scoring runs each of the book's real criteria (size, financial
    condition, earnings stability, 20-year uninterrupted dividend record,
    one-third decade growth, P/E <= 15 on 3-yr average earnings, price <=
    1.5x book with PExPB <= 22.5), then applies Ch. 20 inversion checks:
    what margin remains if estimates prove wrong?
    """
    name = "Benjamin Graham"
    philosophy = (
        "Margin of safety vs conservative appraised value; the seven "
        "defensive-investor tests of Chapter 14; inversion per Chapter 20."
    )

    # Weight of each Ch. 14 test in the blended score (financial strength
    # and price discipline weigh most, per Graham's own emphasis).
    TEST_WEIGHTS = {1: 1.0, 2: 2.0, 3: 1.5, 4: 1.5, 5: 1.0, 6: 2.0, 7: 1.5}

    def score(self, u: dict) -> PersonaVerdict:
        from .graham_principles import (
            DEFENSIVE_CRITERIA, evaluate_defensive, inversion_checks,
            margin_of_safety_pct, MARGIN_OF_SAFETY, MIN_EARNINGS_YIELD_OVER_BOND_PCT,
        )

        bullets: list[str] = []
        parts: list[tuple[float | None, float]] = []
        results = evaluate_defensive(u)
        failed_tests: list[int] = []

        for res in results:
            n = res["test"]
            label = f"test {n} ({DEFENSIVE_CRITERIA[n]['name']})"
            if res["passed"] is True:
                parts.append((85.0, self.TEST_WEIGHTS[n]))
                bullets.append(f"Passes {label}: {res['detail']} — Ch. 14 criterion met.")
            elif res["passed"] is False:
                failed_tests.append(n)
                sev = self.TEST_WEIGHTS[n] * 3.0
                parts.append((30.0, sev))
                bullets.append(f"Fails {label}: {res['detail']} — excluded from my defensive list.")
            else:
                bullets.append(f"{label}: insufficient data to judge ({res['detail']}).")

        # Margin-of-safety core (Ch. 20) — the central concept.
        mos = margin_of_safety_pct(_get(u, "price"), u.get("intrinsic_value_estimate"))
        if mos is not None:
            if mos >= MARGIN_OF_SAFETY["min_margin_of_safety_pct"]:
                parts.append((95, 4))
                bullets.append(f"Margin of safety {mos:.0f}% vs appraised value — the Ch. 20 buy zone.")
            elif mos >= MARGIN_OF_SAFETY["acceptable_margin_of_safety_pct"]:
                parts.append((68, 3))
                bullets.append(f"Margin of safety {mos:.0f}% — present but not demonstrably adequate.")
            else:
                parts.append((28, 4))
                bullets.append(f"Margin of safety only {mos:.0f}% — without it this is speculation, not investment.")

        # Earnings yield vs bond rate (Ch. 14 note / Ch. 20 earning-power rule).
        ey = _get(u, "earnings_yield_pct")
        by = _get(u, "bond_yield_pct")
        if ey is not None and by is not None:
            spread = ey - by
            ok = spread >= MIN_EARNINGS_YIELD_OVER_BOND_PCT + 2
            parts.append(((82 if ok else 50), 1.5))
            bullets.append(
                f"Earnings yield {ey:.1f}% vs bond yield {by:.1f}% — spread {spread:+.1f}pp; "
                f"{'earning power comfortably clears fixed-income competition' if ok else 'bonds pay nearly as much for no equity risk'}."
            )

        # Net-net check (Ch. 15 enterprising approach).
        ncav = _get(u, "net_current_asset_value_per_share")
        px = _get(u, "price")
        if ncav is not None and px is not None:
            ok = px <= ncav
            parts.append(((98 if ok else 60), 1.5))
            bullets.append("Price below net current asset value — a true bargain issue." if ok
                           else f"Price ${px:.0f} above net-current-asset value ${ncav:.0f}/sh — no net-net bargain here.")

        # Ch. 20 inversion checks.
        for note in inversion_checks(u):
            bullets.append(note)

        score, _ = _blend(parts)
        if failed_tests:
            bullets.insert(0,
                "Defensive verdict: fails " +
                ", ".join(f"test {n}" for n in sorted(failed_tests)) +
                f" of {len(DEFENSIVE_CRITERIA)} — Graham's tests eliminate most stocks; that is their purpose.")
        elif not any(r["passed"] is None for r in results) and results:
            bullets.insert(0, "Defensive verdict: passes all seven Ch. 14 quality/quantity tests.")
        if mos is None and px is None:
            bullets.insert(0, "No price provided — cannot compute margin of safety.")
        return PersonaVerdict(self.name, score, _stance(score), bullets)


class PeterLynch:
    """Peter Lynch — growth at a reasonable price; know the story.

    Philosophy: ten-baggers come from understandable businesses with steady,
    compounding earnings bought at a sensible multiple of growth (PEG < 1).
    The story must fit in one sentence you'd tell a neighbor. Watch debt,
    insider buying, and whether institutions have already piled in.
    """
    name = "Peter Lynch"
    philosophy = (
        "Growth-at-a-reasonable-price (PEG<1), consistent earnings growth, "
        "and a simple story you can explain in one sentence."
    )

    def score(self, u: dict) -> PersonaVerdict:
        bullets: list[str] = []
        parts: list[tuple[float | None, float]] = []

        peg = _get(u, "peg_ratio")
        g = _get(u, "earnings_growth_fwd_pct")
        if peg is None and g not in (None, 0):
            pe = _get(u, "pe_ratio")
            if pe is not None:
                peg = pe / g
                bullets.append(f"Derived PEG {peg:.2f} from P/E {pe:.0f} ÷ growth {g:.0f}%.")
        if peg is not None:
            if peg < 1:
                parts.append((92, 4)); bullets.append(f"PEG {peg:.2f} < 1 — growth on sale. This is my favorite kind of stock.")
            elif peg < 1.5:
                parts.append((70, 3)); bullets.append(f"PEG {peg:.2f} — fair-ish price for the growth.")
            else:
                parts.append((38, 4)); bullets.append(f"PEG {peg:.2f} — paying too much for growth here.")
        else:
            bullets.append("No PEG computable (need P/E and forward growth).")
            parts.append((50, 2))

        hist_g = _get(u, "earnings_growth_5y_pct")
        if hist_g is not None:
            ok = hist_g >= 8
            parts.append(((82 if ok else 52), 2))
            bullets.append(f"Historical EPS growth {hist_g:+.0f}%/yr — {'the pattern I look for' if ok else 'slower than I like'}.")

        story = u.get("story")
        if isinstance(story, str) and story.strip():
            simple = len(story.split()) <= 25
            parts.append((80 if simple else 60, 2))
            bullets.append("Story check: " + story.strip() + (" — short enough to explain to a neighbor." if simple else " — getting complicated; complexity is a cost."))
        else:
            bullets.append("No story provided — if I can't explain it, I won't own it.")
            parts.append((45, 2))

        de = _get(u, "debt_to_equity")
        if de is not None:
            ok = de < 0.8
            parts.append(((75 if ok else 50), 1))
            msg = "balance sheet won't sink the story" if ok else "leverage could wreck the narrative"
            bullets.append(f"D/E {de:.2f} — {msg}.")

        inst = _get(u, "institutional_ownership_pct")
        if inst is not None and inst > 80:
            parts.append((55, 1)); bullets.append(f"{inst:.0f}% institutional ownership — the easy money already arrived.")

        score, _ = _blend(parts)
        return PersonaVerdict(self.name, score, _stance(score), bullets)


class CathieWood:
    """Cathie Wood — innovation and exponential disruption.

    Philosophy: the market systematically underprices technological
    convergence (AI, genomics, robotics, energy storage). Volatility is the
    price of asymmetric upside; five-year horizons forgive near-term
    multiples. Deliberately positioned as the council's contrarian voice —
    she is expected to disagree with value-oriented consensus.
    """
    name = "Cathie Wood"
    philosophy = (
        "Disruption-first: innovation exposure and high growth outweigh "
        "today's multiples. The council's intentional dissenting vote."
    )
    disruptive_keywords = {"ai", "artificial intelligence", "robotics", "genomic",
                           "biotech", "battery", "autonomous", "cloud", "semiconductor",
                           "ev", "fintech", "quantum"}

    def score(self, u: dict) -> PersonaVerdict:
        bullets: list[str] = []
        parts: list[tuple[float | None, float]] = []

        sector = str(u.get("sector", "")).lower()
        tags = str(u.get("innovation_tags", "")).lower() + " " + sector
        hits = sorted({k for k in self.disruptive_keywords if k in tags})
        if hits:
            s = _clip(70 + 8 * len(hits))
            parts.append((s, 4))
            bullets.append(f"Direct exposure to disruptive themes ({', '.join(hits)}) — innovation convergence play.")
        else:
            parts.append((42, 3))
            bullets.append(f"'{sector or 'unknown'}' lacks visible innovation catalysts — not my hunting ground.")

        g = _get(u, "revenue_growth_fwd_pct") or _get(u, "earnings_growth_fwd_pct")
        if g is not None:
            if g >= 20:
                parts.append((90, 3)); bullets.append(f"{g:.0f}% forward growth — exponential trajectory intact.")
            elif g >= 10:
                parts.append((70, 2)); bullets.append(f"{g:.0f}% forward growth — solid, though I want more.")
            else:
                parts.append((45, 2)); bullets.append(f"{g:.0f}% forward growth — mature profile, limited optionality.")
        else:
            bullets.append("Forward growth missing — cannot assess trajectory.")
            parts.append((50, 1))

        pe = _get(u, "pe_ratio")
        if pe is not None:
            if pe > 45:
                parts.append((72, 2)); bullets.append(f"P/E {pe:.0f}x looks rich today but is cheap if 5-year disruption plays out.")
            else:
                parts.append((65, 1)); bullets.append(f"P/E {pe:.0f}x — undemanding for any growth at all.")

        r_and_d = _get(u, "rd_intensity_pct")
        if r_and_d is not None:
            ok = r_and_d >= 8
            parts.append(((85 if ok else 55), 2))
            bullets.append(f"R&D intensity {r_and_d:.0f}% — {'investing through the cycle' if ok else 'under-investing in the future'}.")

        vol = _get(u, "annualized_volatility_pct")
        if vol is not None and vol >= 35:
            parts.append((70, 1)); bullets.append(f"Volatility {vol:.0f}% — that's the toll for convex upside; I'll pay it.")

        score, _ = _blend(parts)
        if not bullets:
            bullets = ["Too little data to see disruption potential — abstaining toward neutral."]
        return PersonaVerdict(self.name, score, _stance(score), bullets)


PERSONAS = {
    "buffett": WarrenBuffett(),
    "munger": CharlieMunger(),
    "dalio": RayDalio(),
    "graham": BenjaminGraham(),
    "lynch": PeterLynch(),
    "wood": CathieWood(),
}

DEFAULT_WEIGHTS = {
    "buffett": 1.0,
    "munger": 1.0,
    "dalio": 0.8,
    "graham": 1.0,
    "lynch": 0.9,
    "wood": 0.6,
}
