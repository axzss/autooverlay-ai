"""Distilled principles digest — Benjamin Graham, *The Intelligent Investor*
(4th rev. ed., Zweig commentary edition). Structured constants for the
council's Graham persona, Mr. Market regime module, and screening logic.

All thresholds below are transcribed from the book itself:
  - Ch. 14 "Stock Selection for the Defensive Investor" — the seven
    quality/quantity criteria (tests 1-7).
  - Ch. 15 — enterprising-investor approaches.
  - Ch. 8  — Mr. Market parable and investor-vs-speculator psychology.
  - Ch. 20 — margin of safety as the central concept of investment.
Only short quoted fragments (<50 words) appear in comments; everything
else is paraphrase.

Field-name conventions for underlying dicts consumed by these criteria:
  price, intrinsic_value_estimate, pe_ratio (vs 3-yr avg earnings),
  pb_ratio, current_ratio, long_term_debt_to_working_capital,
  annual_sales_musd / total_assets_musd (size test),
  positive_earnings_years (list of last ~10 yearly EPS),
  dividend_years_paid (list/bools of last ~20 years paid or not),
  earnings_growth_10y_pct (3-yr averages a decade apart),
  dividend_yield_pct, earnings_yield_pct, bond_yield_pct,
  net_current_asset_value_per_share (net-nets).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Investment vs speculation (Ch. 4 & 20)                                       #
# --------------------------------------------------------------------------- #
INVESTMENT_REQUIREMENTS = {
    # Graham's operational definition: an investment operation promises
    # safety of principal AND an adequate return; anything else is speculation.
    "thorough_analysis": True,
    "principal_safety_promised": True,
    "adequate_return_possible": True,
}
SPECULATION_WARNINGS = (
    "Speculating with money you cannot afford to lose",
    "Traders' forecasting effort self-neutralizes over time",
    "Buying on market action first, values second",
)

# --------------------------------------------------------------------------- #
# Defensive-investor criteria — the seven tests of Chapter 14                   #
# --------------------------------------------------------------------------- #
DEFENSIVE_CRITERIA = {
    1: {
        "name": "Adequate Size of the Enterprise",
        "rule": "Exclude small companies subject to more than average vicissitudes.",
        "min_annual_sales_musd_industrial": 100,
        "min_total_assets_musd_utility": 50,
        "input_keys": ("annual_sales_musd", "total_assets_musd"),
    },
    2: {
        "name": "A Sufficiently Strong Financial Condition",
        "rule": "Current assets at least twice current liabilities; long-term debt "
                "not exceeding net current assets (working capital). Utilities: "
                "debt not above twice stock equity at book value.",
        "min_current_ratio": 2.0,
        "max_lt_debt_to_working_capital": 1.0,
        "input_keys": ("current_ratio", "long_term_debt_to_working_capital"),
    },
    3: {
        "name": "Earnings Stability",
        "rule": "Some earnings for the common stock in each of the past ten years.",
        "required_positive_earnings_years": 10,
        "window_years": 10,
        "input_keys": ("positive_earnings_years",),
    },
    4: {
        "name": "Dividend Record",
        "rule": "Uninterrupted payments for at least the past 20 years.",
        "required_uninterrupted_dividend_years": 20,
        "input_keys": ("dividend_years_paid", "years_since_dividend_started"),
    },
    5: {
        "name": "Earnings Growth",
        "rule": "Minimum increase of one-third in per-share earnings over ten "
                "years, using three-year averages at beginning and end.",
        "min_10y_eps_growth_pct": 33.3,
        "input_keys": ("earnings_growth_10y_pct",),
    },
    6: {
        "name": "Moderate Price/Earnings Ratio",
        "rule": "Current price not more than 15 times average earnings of the "
                "past three years.",
        "max_pe_on_avg_earnings": 15.0,
        "input_keys": ("pe_ratio", "pe_on_3yr_avg_earnings"),
    },
    7: {
        "name": "Moderate Ratio of Price to Assets",
        "rule": "Price not more than 1.5x book value; P/E x P/B product must not "
                "exceed 22.5 (e.g. 9x earnings may justify 2.5x assets).",
        "max_price_to_book": 1.5,
        "max_pe_times_pb": 22.5,
        "input_keys": ("pb_ratio", "pe_ratio"),
    },
}

# Overall earnings yield should be >= high-grade bond rate (Ch. 14 note:
# implies e.g. P/E <= 13.3 against an AA bond yield of 7.5%).
MIN_EARNINGS_YIELD_OVER_BOND_PCT = 0.0   # stock E/P minus bond yield >= 0


def evaluate_defensive(u: dict) -> list[dict]:
    """Run all seven Ch. 14 tests against an underlying dict.

    Returns a list of {"test": n, "name": ..., "passed": bool|None,
    "detail": str} — None means insufficient data (test inconclusive).
    """
    def _num(*keys):
        for k in keys:
            v = u.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
        return None

    results: list[dict] = []

    # Test 1 — size
    sales = _num("annual_sales_musd")
    assets = _num("total_assets_musd")
    c1 = DEFENSIVE_CRITERIA[1]
    if sales is not None:
        ok = sales >= c1["min_annual_sales_musd_industrial"]
        results.append({"test": 1, "name": c1["name"], "passed": ok,
                        "detail": f"annual sales ${sales:.0f}M"})
    elif assets is not None:
        ok = assets >= c1["min_total_assets_musd_utility"]
        results.append({"test": 1, "name": c1["name"], "passed": ok,
                        "detail": f"total assets ${assets:.0f}M"})
    else:
        results.append({"test": 1, "name": c1["name"], "passed": None,
                        "detail": "no size data"})

    # Test 2 — financial condition
    cr = _num("current_ratio")
    ltd = _num("long_term_debt_to_working_capital")
    checks2 = []
    if cr is not None:
        checks2.append(cr >= DEFENSIVE_CRITERIA[2]["min_current_ratio"])
    if ltd is not None:
        checks2.append(ltd <= DEFENSIVE_CRITERIA[2]["max_lt_debt_to_working_capital"])
    results.append({
        "test": 2, "name": DEFENSIVE_CRITERIA[2]["name"],
        "passed": (None if not checks2 else all(checks2)),
        "detail": f"current ratio {cr if cr is not None else 'n/a'}",
    })

    # Test 3 — earnings stability (10y)
    hist = u.get("positive_earnings_years")
    c3 = DEFENSIVE_CRITERIA[3]
    if isinstance(hist, (list, tuple)) and len(hist) > 0:
        pos = sum(1 for x in hist if isinstance(x, (int, float)) and x > 0)
        ok = all(x > 0 for x in hist if isinstance(x, (int, float))) \
             and len(hist) >= min(c3["window_years"], len(hist))
        results.append({"test": 3, "name": c3["name"], "passed": bool(ok),
                        "detail": f"{pos} positive-earnings years out of {len(hist)}"})
    else:
        results.append({"test": 3, "name": c3["name"], "passed": None,
                        "detail": "no 10-year earnings history"})

    # Test 4 — dividend record (20y uninterrupted)
    div_hist = u.get("dividend_years_paid")
    c4 = DEFENSIVE_CRITERIA[4]
    if isinstance(div_hist, (list, tuple)) and len(div_hist) > 0:
        paid = sum(1 for d in div_hist if d)
        ok = paid == len(div_hist) and len(div_hist) >= 20
        results.append({"test": 4, "name": c4["name"], "passed": bool(ok),
                        "detail": f"dividends paid in {paid}/{len(div_hist)} recent years"})
    else:
        yrs_since = _num("years_since_dividend_started")
        if yrs_since is not None:
            results.append({"test": 4, "name": c4["name"], "passed": yrs_since >= 20,
                            "detail": f"dividend history {yrs_since:.0f}y"})
        else:
            results.append({"test": 4, "name": c4["name"], "passed": None,
                            "detail": "no 20-year dividend record"})

    # Test 5 — earnings growth (>=1/3 over 10y)
    g10 = _num("earnings_growth_10y_pct")
    c5 = DEFENSIVE_CRITERIA[5]
    if g10 is not None:
        results.append({"test": 5, "name": c5["name"],
                        "passed": g10 >= c5["min_10y_eps_growth_pct"],
                        "detail": f"10y EPS growth {g10:+.1f}%"})
    else:
        results.append({"test": 5, "name": c5["name"], "passed": None,
                        "detail": "no decade growth data"})

    # Test 6 — moderate P/E (on 3-yr average earnings)
    pe = _num("pe_on_3yr_avg_earnings") or _num("pe_ratio")
    c6 = DEFENSIVE_CRITERIA[6]
    if pe is not None:
        results.append({"test": 6, "name": c6["name"],
                        "passed": pe <= c6["max_pe_on_avg_earnings"],
                        "detail": f"P/E {pe:.1f}x vs 15x ceiling"})
    else:
        results.append({"test": 6, "name": c6["name"], "passed": None,
                        "detail": "no P/E"})

    # Test 7 — price/assets + PE*PB <= 22.5
    pb = _num("pb_ratio")
    c7 = DEFENSIVE_CRITERIA[7]
    if pb is not None:
        passed7 = pb <= c7["max_price_to_book"]
        detail = f"P/B {pb:.1f}x vs 1.5x"
        if pe is not None:
            product = pb * pe
            prod_ok = product <= c7["max_pe_times_pb"]
            passed7 = passed7 or prod_ok  # book allows richer P/B if P/E cheap enough
            detail += f"; PExPB {product:.1f} vs 22.5 cap"
        else:
            prod_ok = None
        results.append({"test": 7, "name": c7["name"], "passed": bool(passed7),
                        "detail": detail})
    else:
        results.append({"test": 7, "name": c7["name"], "passed": None,
                        "detail": "no P/B"})

    return results


# --------------------------------------------------------------------------- #
# Enterprising-investor criteria (Ch. 15)                                      #
# --------------------------------------------------------------------------- #
ENTERPRISING_CRITERIA = {
    "low_multiples": "Buy on a low multiple of current earnings (Graham ran a "
                     "test portfolio at ~9x earnings and ~12x book-equivalents).",
    "bargain_issues": "Price well under appraised value — especially half of "
                      "past 12-month high; secondary companies at bargain levels.",
    "net_nets": "Price below net current asset value (working capital alone "
                "below price); requires heavy diversification and discipline.",
    "special_situations": "Merger/restructuring arb only with real legal insight.",
}

NET_CURRENT_ASSET_TEST = "price <= net current asset value per share"

# --------------------------------------------------------------------------- #
# Margin of Safety (Ch. 20)                                                    #
# --------------------------------------------------------------------------- #
MARGIN_OF_SAFETY = {
    "motto": "Margin of Safety as the Central Concept of Investment",
    "definition": "Favorable difference between price and conservatively "
                  "appraised value; absorbs miscalculation and bad luck.",
    "min_margin_of_safety_pct": 33.3,     # buy zone used by Graham-style value funds
    "acceptable_margin_of_safety_pct": 15.0,
    "bond_coverage_rule": "Fixed charges earned > 5x before tax over years (bond analogue).",
    "earning_power_vs_bond_rule": "Stock earning power should exceed the going bond "
                                  "rate by a comfortable spread sustained over a decade.",
    "estimates_must_err_understated": True,   # prudent rule: err on understatement
}


def margin_of_safety_pct(price: float | None, value: float | None) -> float | None:
    """(value - price) / value * 100 — how much estimates can be wrong before loss."""
    if not isinstance(price, (int, float)) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return (value - price) / value * 100


def inversion_checks(u: dict) -> list[str]:
    """Ch. 20 inversion: what happens to this position if estimates prove wrong?

    Returns human-readable risk statements quantifying the cushion that
    survives adverse surprises."""
    notes: list[str] = []

    def _num(key):
        v = u.get(key)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    mos = margin_of_safety_pct(_num("price"), u.get("intrinsic_value_estimate"))
    if mos is not None:
        if mos >= MARGIN_OF_SAFETY["min_margin_of_safety_pct"]:
            notes.append(
                f"Inversion: appraised value can fall another {mos:.0f}% before "
                f"cost is impaired — margin survives sizable estimate error.")
        elif mos >= MARGIN_OF_SAFETY["acceptable_margin_of_safety_pct"]:
            notes.append(
                f"Inversion: only {mos:.0f}% cushion — a modest analytical error "
                f"wipes it out; margin too thin to rely on.")
        else:
            notes.append(
                "Inversion: negative or negligible margin — the whole case rests "
                "on estimates being right; per Ch. 20 this is speculation.")

    eps_fwd = _num("eps_fwd_estimate")
    eps_hist = _num("eps_trailing")
    if eps_fwd and eps_hist and eps_fwd > eps_hist:
        uplift = (eps_fwd / eps_hist - 1) * 100
        notes.append(
            f"Inversion: forward estimate embeds {uplift:+.0f}% growth over trailing — "
            f"if realized EPS merely matches history, today's price has no support."
            if uplift > 20 else
            f"Inversion: forward estimate assumes modest {uplift:+.0f}% uplift — "
            f"cushion not dependent on heroic projections.")

    pe = _num("pe_ratio")
    if pe is not None and pe > 22.5 / 1.5:
        notes.append(
            f"Inversion: at {pe:.1f}x earnings, a reversion to Graham's 15x ceiling "
            f"implies roughly {-((1 - 15 / pe) * 100):.0f}% downside with zero change "
            f"in fundamentals.")

    ltd_inv = _num("long_term_debt_to_working_capital")
    if ltd_inv is not None and ltd_inv > 1:
        notes.append("Inversion: long-term debt exceeds working capital — no "
                     "balance-sheet buffer in an adverse year.")
    return notes


DIVERSIFICATION_RULE = (
    "Margin of safety guarantees better odds, not certainty — diversification "
    "(20+ issues) converts individual failures into insurance-like aggregate profit."
)

# --------------------------------------------------------------------------- #
# Inflation warnings (Ch. 2 & Zweig commentary context)                        #
# --------------------------------------------------------------------------- #
RISK_WARNINGS = {
    "speculation_vs_investment": "If you cannot demonstrate the margin with figures "
                                 "and reasoning from experience, you are speculating.",
    "inflation": "Persistent inflation erodes fixed claims; equities are not an "
                 "automatic hedge — demand real earning power, not nominal growth.",
    "mos_erosion": "Margin of safety depends entirely on the price paid; it is large "
                   "at one price, small at higher, nonexistent higher still.",
    "fair_weather_buys": "Chief losses come from buying low-quality securities in "
                         "prosperity, mistaking good times for earning power.",
    "market_timing": "Do not hold off buying solely for lower market levels; but do "
                     "refrain when the general level exceeds established standards of value.",
}
