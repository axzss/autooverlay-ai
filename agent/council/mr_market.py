"""Mr. Market — market-fluctuation psychology regime signal (Ch. 8).

Graham's parable: Mr. Market is your obliging business partner who quotes
you a price every day, sometimes sensible, often driven by enthusiasm or
fear. The investor's job is to act as a businessman toward his quotations:
use them when advantageous, ignore them otherwise. Price fluctuations have
only one significant meaning for the true investor — an opportunity to buy
wisely when prices fall sharply and to be wary (sell/withhold) when they
advance a great deal.

This module turns recent price/vol inputs into a mood classification plus
guidance strings for the council's decision engine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Mood thresholds (tunable, expressed as fractions).
EUPHORIC_RUNUP_PCT = 20.0      # +20% over the lookback -> euphoric advance
PANICKY_DRAWDOWN_PCT = -15.0   # -15% over the lookback -> panicky decline
HIGH_VOL_THRESHOLD_PCT = 35.0  # annualized vol that signals emotional tape
LOW_VOL_THRESHOLD_PCT = 15.0   # complacent tape


@dataclass
class MarketMood:
    mood: str                     # "euphoric" | "indifferent" | "panicky" | "unknown"
    runup_pct: float | None       # change over lookback window
    realized_vol_pct: float | None
    guidance: list[str] = field(default_factory=list)

    @property
    def is_favorable_for_buying(self) -> bool:
        return self.mood == "panicky"

    @property
    def is_warning_against_buying(self) -> bool:
        return self.mood == "euphoric"


def _pct_change(prices: list[float]) -> float | None:
    clean = [p for p in prices if isinstance(p, (int, float)) and p > 0]
    if len(clean) < 2:
        return None
    return (clean[-1] / clean[0] - 1) * 100


def _realized_vol_pct(prices: list[float]) -> float | None:
    """Annualized vol of daily returns (%), if enough observations."""
    clean = [p for p in prices if isinstance(p, (int, float)) and p > 0]
    if len(clean) < 5:
        return None
    rets = [math.log(clean[i] / clean[i - 1]) for i in range(1, len(clean))
            if clean[i - 1] > 0]
    if len(rets) < 4:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252) * 100


def classify_market_mood(prices: list[float],
                         vol_override: float | None = None) -> MarketMood:
    """Classify Mr. Market's current mood from a recent price series.

    prices: chronological daily closes (any lookback; longer windows give
            steadier readings). vol_override: externally supplied annualized vol.
    """
    runup = _pct_change(prices)
    vol = vol_override if isinstance(vol_override, (int, float)) \
        else _realized_vol_pct(prices)

    if runup is None and vol is None:
        g = ["Mr. Market has said nothing yet — no usable price history. "
             "Form value judgments from operations and financial position, not quotations."]
        return MarketMood("unknown", None, None, g)

    euphoric = runup is not None and (
        runup >= EUPHORIC_RUNUP_PCT or
        (runup >= EUPHORIC_RUNUP_PCT / 2 and
         vol is not None and vol < LOW_VOL_THRESHOLD_PCT))
    panicky = (runup is not None and runup <= PANICKY_DRAWDOWN_PCT) or (
        vol is not None and vol >= HIGH_VOL_THRESHOLD_PCT and
        runup is not None and runup <= 0)

    if panicky:
        mood = "panicky"
        guidance = [
            "Mr. Market is in one of his frightened moods — quoting silly low prices. "
            "This is when the businessman buys from him, wisely.",
            "Buy wisely when prices fall sharply: fluctuations are opportunities, not warnings.",
            "Act as a businessman, not a speculator: appraise the enterprise, then take "
            "advantage of the depressed quotation.",
        ]
    elif euphoric:
        mood = "euphoric"
        guidance = [
            "Mr. Market is euphoric and offering ridiculous prices to buy you out — "
            "consider selling into him, certainly refrain from new buying.",
            "Never buy immediately after a substantial rise; high levels above established "
            "standards of value are where investors get hurt.",
            "Be wary when euphoric: the margin of safety shrinks as the price paid rises.",
        ]
    else:
        mood = "indifferent"
        guidance = [
            "Mr. Market is calm and unexciting. The rest of the time it is wiser to forget "
            "the market and pay attention to dividend returns and operating results.",
            "No edge either way from the quotation itself — let fundamentals decide.",
        ]

    detail = []
    if runup is not None:
        detail.append(f"{runup:+.1f}% over the window")
    if vol is not None:
        detail.append(f"{vol:.0f}% realized vol")
    guidance.insert(0, f"Market read ({mood}): {', '.join(detail)}.")
    return MarketMood(mood, runup, vol, guidance)


def mr_market_context(underlying: dict, portfolio: dict | None = None) -> dict:
    """Build the mr_market_context block wired into CouncilEngine output."""
    prices = underlying.get("recent_prices") or (portfolio or {}).get("market_prices_recent") or []
    vol = underlying.get("annualized_volatility_pct")
    mood = classify_market_mood(list(prices), vol)
    return {
        "mood": mood.mood,
        "runup_pct": round(mood.runup_pct, 2) if mood.runup_pct is not None else None,
        "realized_vol_pct": round(mood.realized_vol_pct, 2) if mood.realized_vol_pct is not None else None,
        "favorable_for_buying": mood.is_favorable_for_buying,
        "warning_against_buying": mood.is_warning_against_buying,
        "guidance": mood.guidance,
    }
