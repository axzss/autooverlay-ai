"""End-to-end council demo: AAPL / MSFT / TSLA / NVDA snapshot -> full report."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.council import CouncilEngine, generate_report

PORTFOLIO = {
    "cash": 42_000,
    "total_value": 250_000,
    "macro_rate_regime": "falling",
    "macro_inflation_pct": 2.8,
    "portfolio_sector_concentration_pct": 45,
    "positions": [
        {"symbol": "AAPL", "qty": 200, "annualized_volatility_pct": 24},
        {"symbol": "MSFT", "qty": 150, "annualized_volatility_pct": 22},
    ],
}

CANDIDATES = [
    {
        "symbol": "AAPL", "sector": "Technology", "moat": "wide",
        "price": 228, "intrinsic_value_estimate": 240,
        "pe_ratio": 31, "pb_ratio": 45, "peg_ratio": 2.4,
        "operating_margin_pct": 30, "gross_margin_pct": 46, "roe_pct": 150,
        "debt_to_equity": 1.5, "current_ratio": 0.9,
        "dividend_yield_pct": 0.5, "earnings_growth_5y_pct": 9,
        "earnings_growth_fwd_pct": 10, "revenue_growth_fwd_pct": 6,
        "free_cash_flow_yield_pct": 3.5, "institutional_ownership_pct": 60,
        "disruption_risk": "medium", "story": "The iPhone ecosystem keeps customers paying forever.",
        "innovation_tags": "consumer hardware, services",
        "rd_intensity_pct": 7,
    },
    {
        "symbol": "MSFT", "sector": "Technology", "moat": "wide",
        "price": 420, "intrinsic_value_estimate": 450,
        "pe_ratio": 34, "pb_ratio": 12, "peg_ratio": 2.0,
        "operating_margin_pct": 44, "gross_margin_pct": 70, "roe_pct": 38,
        "debt_to_equity": 0.4, "current_ratio": 1.6,
        "dividend_yield_pct": 0.7, "earnings_growth_5y_pct": 16,
        "earnings_growth_fwd_pct": 14, "revenue_growth_fwd_pct": 13,
        "free_cash_flow_yield_pct": 2.8, "insider_ownership_pct": 0.06,
        "disruption_risk": "low", "story": "Enterprise software plus AI cloud rent collection.",
        "innovation_tags": "ai, cloud",
        "rd_intensity_pct": 12,
    },
    {
        "symbol": "TSLA", "sector": "Consumer", "moat": "narrow",
        "price": 250, "intrinsic_value_estimate": 180,
        "pe_ratio": 70, "pb_ratio": 11,
        "operating_margin_pct": 8, "gross_margin_pct": 18, "roe_pct": 20,
        "debt_to_equity": 0.2, "current_ratio": 1.9,
        "earnings_growth_5y_pct": 30, "earnings_growth_fwd_pct": 12,
        "revenue_growth_fwd_pct": 15, "customer_concentration_pct": 5,
        "annualized_volatility_pct": 55, "disruption_risk": "high",
        "story": "EVs plus robotaxis plus Optimus.",
        "innovation_tags": "ev, autonomous, robotics, ai, battery",
        "rd_intensity_pct": 9,
    },
    {
        "symbol": "NVDA", "sector": "Technology", "moat": "wide",
        "price": 125, "intrinsic_value_estimate": 130,
        "pe_ratio": 48, "pb_ratio": 35,
        "operating_margin_pct": 62, "gross_margin_pct": 75, "roe_pct": 90,
        "debt_to_equity": 0.2, "current_ratio": 4.0,
        "earnings_growth_5y_pct": 60, "earnings_growth_fwd_pct": 35,
        "revenue_growth_fwd_pct": 50, "free_cash_flow_yield_pct": 2.5,
        "annualized_volatility_pct": 48, "disruption_risk": "medium",
        "story": "Sells the picks and shovels for the entire AI gold rush.",
        "innovation_tags": "ai, semiconductor, cloud",
        "rd_intensity_pct": 14,
    },
]


def main() -> None:
    engine = CouncilEngine()
    print(generate_report(PORTFOLIO, CANDIDATES, engine))


if __name__ == "__main__":
    main()
