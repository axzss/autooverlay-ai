"""
Council Handoff Consumption Layer.

Parses the HANDOFF section of docs/council_report.md into a structured
volatility-tier policy the strategy engine can consume:

    {tier -> {delta_min, delta_max, max_dte, allowed_strategies,
              size_multiplier}}

If the markdown cannot be parsed (section missing, malformed tables, etc.)
we fall back to sane defaults that mirror the council's published
recommendations:

    low  (<20% vol):  delta 0.15-0.30, DTE <=45, both strategies, 1.0x size
    mid  (20-35%):    delta 0.10-0.25, DTE <=45, both strategies, 0.5x size
    high (>35%):      delta 0.05-0.15, DTE <=30, covered-call only, 0.5x size

TSLA override (council §8): delta <= 0.10 and HALF size until realized vol
< 45%.

Tier boundaries (council §2): <20% annualized vol -> low, 20-35% -> mid,
>35% -> high.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional


# --------------------------------------------------------------------------- #
# Tier mapping                                                                #
# --------------------------------------------------------------------------- #

TIER_LOW_VOL_PCT = 20.0     # < 20%  -> low
TIER_HIGH_VOL_PCT = 35.0    # > 35%  -> high (20-35% -> mid)

TIER_ORDER = ("low", "mid", "high")


def get_tier_for_symbol(symbol: str, vol_annualized_pct: float) -> str:
    """Map a symbol + annualized realized vol (%) to its council volatility tier.

    Boundaries per council report §2:
        vol < 20%        -> 'low'
        20% <= vol <=35% -> 'mid'
        vol > 35%        -> 'high'
    """
    try:
        v = float(vol_annualized_pct)
    except (TypeError, ValueError):
        # Unknowable volatility is treated conservatively as high-vol.
        return "high"
    if v < TIER_LOW_VOL_PCT:
        return "low"
    if v <= TIER_HIGH_VOL_PCT:
        return "mid"
    return "high"


# --------------------------------------------------------------------------- #
# Policy model                                                                #
# --------------------------------------------------------------------------- #

# Council-restricted symbols (§8): TSLA gets delta<=0.10 + half-size until vol<45%
SYMBOL_OVERRIDES = {
    "TSLA": {
        "delta_max": 0.10,
        "size_multiplier": 0.5,
        "until_vol_below": 45.0,
        "reason": "council §8: 59.1% vol + -27.2% drawdown — delta ≤0.10, "
                  "half-size until vol <45%",
    },
}

# Tech-complex correlated group (council §6 correlation rule)
TECH_COMPLEX = ("AAPL", "MSFT", "NVDA", "QQQ")


@dataclass
class TierPolicy:
    """Screening parameters for one volatility tier."""
    name: str
    vol_band: str
    delta_min: float
    delta_max: float
    max_dte: int
    allowed_strategies: tuple          # subset of ("CSP", "COVERED_CALL")
    size_multiplier: float
    source: str = "default"            # 'parsed' | 'default'

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["allowed_strategies"] = list(self.allowed_strategies)
        return d

    def allows(self, strategy_name: str) -> bool:
        """strategy_name: 'CSP' / 'COVERED_CALL' (case-insensitive)."""
        s = strategy_name.upper().replace("CASH_SECURED_PUT", "CSP")
        return any(s == a or s.replace("_", "") == a.replace("_", "")
                   for a in self.allowed_strategies)


DEFAULT_TIER_POLICY: Dict[str, TierPolicy] = {
    "low": TierPolicy(
        name="low", vol_band="<20%", delta_min=0.15, delta_max=0.30,
        max_dte=45, allowed_strategies=("CSP", "COVERED_CALL"),
        size_multiplier=1.0),
    "mid": TierPolicy(
        name="mid", vol_band="20-35%", delta_min=0.10, delta_max=0.25,
        max_dte=45, allowed_strategies=("CSP", "COVERED_CALL"),
        size_multiplier=0.5),
    "high": TierPolicy(
        name="high", vol_band=">35%", delta_min=0.05, delta_max=0.15,
        max_dte=30, allowed_strategies=("COVERED_CALL",),
        size_multiplier=0.5),
}


def effective_policy_for_symbol(
    symbol: str, vol_annualized_pct: float,
    policies: Optional[Dict[str, TierPolicy]] = None,
) -> tuple[TierPolicy, list[str]]:
    """Resolve tier + symbol overrides into the effective screening policy.

    Returns (policy, notes) where notes explain any council overrides applied.
    """
    policies = policies or DEFAULT_TIER_POLICY
    tier = get_tier_for_symbol(symbol, vol_annualized_pct)
    base = policies[tier]
    notes = [f"{symbol}: {vol_annualized_pct:.1f}% vol → '{tier}' tier "
             f"(delta {base.delta_min:.2f}-{base.delta_max:.2f}, "
             f"DTE≤{base.max_dte}, strategies={','.join(base.allowed_strategies)}, "
             f"size x{base.size_multiplier})"]
    ov = SYMBOL_OVERRIDES.get(str(symbol).upper())
    if ov and float(vol_annualized_pct) >= ov["until_vol_below"]:
        eff = TierPolicy(
            name=tier, vol_band=base.vol_band,
            delta_min=min(base.delta_min, ov["delta_max"] - 0.05)
            if base.delta_min >= ov["delta_max"] else base.delta_min,
            delta_max=ov["delta_max"],
            max_dte=base.max_dte,
            allowed_strategies=base.allowed_strategies,
            size_multiplier=ov["size_multiplier"],
            source="parsed+override")
        notes.append(f"{symbol} OVERRIDE ACTIVE ({ov['reason']})")
        return eff, notes
    return base, notes


# --------------------------------------------------------------------------- #
# Markdown parsing                                                            #
# --------------------------------------------------------------------------- #

_EN_DASH = "[–\\-—]"


def _num(tok: str) -> float:
    return float(tok.strip().replace("%", ""))


def _parse_delta_pair(text: str):
    m = re.search(rf"(\d\.\d+)\s*{_EN_DASH}\s*(\d\.\d+)", text)
    if not m:
        return None
    lo, hi = float(m.group(1)), float(m.group(2))
    # Security clamp: injected markdown must not be able to widen the delta
    # band past sane option-selling bounds.
    lo = min(max(lo, 0.01), 0.90)
    hi = min(max(hi, 0.02), 0.95)
    if not (lo < hi):
        return None
    return lo, hi


def _clamp_int(value, low: int, high: int) -> int:
    return min(max(int(value), low), high)


def _clamp_float(value, low: float, high: float) -> float:
    import math

    if not math.isfinite(float(value)):
        return high
    return min(max(float(value), low), high)


def parse_handoff(markdown: str) -> Dict[str, TierPolicy]:
    """Parse the HANDOFF section of the council report into tier policies.

    Falls back to DEFAULT_TIER_POLICY values per-tier whenever a specific
    attribute cannot be extracted.
    """
    result: Dict[str, TierPolicy] = {
        k: TierPolicy(**v.to_dict(), ) for k, v in DEFAULT_TIER_POLICY.items()
    }
    for p in result.values():
        p.source = "parsed"

    # Isolate the HANDOFF section (fall back to whole document).
    m = re.search(r"^#+\s*.*HANDOFF.*$", markdown, flags=re.MULTILINE)
    section = markdown[m.start():] if m else ""
    if not section:
        for p in result.values():
            p.source = "default"
        return result

    parsed_any = False

    # --- Low tier: default band applies unchanged -------------------------- #
    m = re.search(r"[Dd]efault band[^\n]*?(?:assumed\s*)?[~≈]?\s*0\.(\d)\s*[–\-]\s*0\.(\d)",
                  section)
    if not m:
        # e.g. "Default band (assumed ~0.15–0.30 short delta)"
        m = re.search(r"[Dd]efault band\s*\((?:assumed\s*)?[~≈]?\s*"
                      rf"(\d\.\d+)\s*{_EN_DASH}\s*(\d\.\d+)", section)
    if m:
        pair = _parse_delta_pair(m.group(0))
        if pair:
            result["low"].delta_min, result["low"].delta_max = pair
            parsed_any = True

    # --- Mid tier ----------------------------------------------------------- #
    m = re.search(r"[Mm]id tier:[^\n]*", section)
    if m:
        pair = _parse_delta_pair(m.group(0))
        if pair:
            result["mid"].delta_min, result["mid"].delta_max = pair
            parsed_any = True

    # --- High tier ---------------------------------------------------------- #
    m = re.search(r"[Hh]igh tier[^\n]*", section)
    if m:
        line = m.group(0)
        pair = _parse_delta_pair(line)
        if pair:
            result["high"].delta_min, result["high"].delta_max = pair
            parsed_any = True
        dm = re.search(r"DTE\s*<?=?\s*(\d+)", line)
        if dm:
            result["high"].max_dte = _clamp_int(dm.group(1), 1, 365)

    # High tier covered-call-only comes from the eligibility table row.
    m = re.search(r"\|\s*High[^|]*\|\s*[^|]*\|\s*([^|]*)\|\s*([^|]*)\|",
                  section)
    if m:
        cc_cell = (m.group(1) + m.group(2)).lower()
        csp_cell = m.group(1).lower()
        if "blocked" in csp_cell and "❌" in csp_cell:
            result["high"].allowed_strategies = ("COVERED_CALL",)
            parsed_any = True

    # Mid tier reduced size from the eligibility table.
    m = re.search(r"\|\s*Mid[^|]*\|\s*([^|]*)\|", section)
    if m and ("reduced size" in m.group(1).lower() or "⚠️" in m.group(1)):
        result["mid"].size_multiplier = 0.5
        parsed_any = True

    # --- TSLA override ------------------------------------------------------ #
    m = re.search(r"For TSLA specifically[^\n]*", section)
    if m:
        line = m.group(0)
        dm = re.search(r"delta\s*<?=?\s*(0\.\d+)", line)
        if dm:
            # Security clamp: a hostile/injected council_report.md must not be
            # able to raise the TSLA delta cap or size multiplier.
            SYMBOL_OVERRIDES.setdefault("TSLA", {})["delta_max"] = \
                _clamp_float(dm.group(1), 0.01, 0.50)
            SYMBOL_OVERRIDES["TSLA"]["reason"] = (
                f"council handoff: TSLA restricted to delta ≤{dm.group(1)}")
            hm = re.search(r"half[- ]?size", line.lower())
            if hm:
                SYMBOL_OVERRIDES["TSLA"]["size_multiplier"] = 0.5
            vm = re.search(r"(?:until|below)\s*vol\s*<?\s*(\d+(?:\.\d+)?)\s*%",
                           line)
            if vm:
                # Must stay strictly positive so the override cannot become
                # permanently-active (until_vol_below=0) via injection.
                SYMBOL_OVERRIDES["TSLA"]["until_vol_below"] = \
                    _clamp_float(vm.group(1), 1.0, 500.0)
            parsed_any = True

    if not parsed_any:
        for p in result.values():
            p.source = "default"
    return result


def load_council_handoff(
    path: Optional[str] = None,
) -> Dict[str, TierPolicy]:
    """Load + parse the council report's HANDOFF section from disk.

    Never raises: unreadable/unparseable reports yield the sane defaults.
    """
    candidates = []
    if path:
        candidates.append(Path(path))
    here = Path(__file__).resolve()
    candidates += [
        here.parents[2] / "docs" / "council_report.md",
        Path("docs") / "council_report.md",
    ]
    for cand in candidates:
        try:
            text = cand.read_text(encoding="utf-8")
            return parse_handoff(text)
        except (OSError, ValueError):
            continue
    return {k: TierPolicy(**v.to_dict()) for k, v in DEFAULT_TIER_POLICY.items()}


def handoff_as_dicts(policies: Dict[str, TierPolicy]) -> Dict[str, Dict]:
    """Plain-dict view matching the task spec shape."""
    return {t: p.to_dict() for t, p in policies.items()}
