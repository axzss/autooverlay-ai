# HEDGE-FUND-COUNCIL — The Investment Committee

`agent/council/` implements a six-person investment committee. Each persona
evaluates a stock independently against its own philosophy, and the engine
combines those verdicts into a consensus while keeping disagreement visible.

The design bet: a single scoring function is a black box, but six named
philosophies that can openly disagree is auditable. When the committee is split,
that is information — not an error to smooth over.

---

## The six personas

Defined in `personas.py`. Each returns a `PersonaVerdict`:

```python
@dataclass
class PersonaVerdict:
    persona: str        # "Warren Buffett"
    score:   float      # 0-100
    stance:  str        # STRONG_BUY / ACCUMULATE / HOLD / REDUCE / AVOID
    bullets: list[str]  # rationale, one line per check
```

| Persona | Weights most heavily | Signature check |
|---|---|---|
| **Warren Buffett** | Moat, ROE, predictable earnings, price vs intrinsic value | Would I own the whole business at this price? |
| **Charlie Munger** | Quality at a fair price, inversion | What would make this position fail? |
| **Ray Dalio** | Diversification, correlation, macro regime | Sector concentration via `portfolio_sector_concentration_pct` |
| **Benjamin Graham** | The seven Ch.14 defensive tests, margin of safety | See below — book-accurate |
| **Peter Lynch** | Growth at reasonable price, comprehensible story | PEG, "can I explain this in a sentence?" |
| **Cathie Wood** | Innovation exposure, disruption | Deliberately contrarian on deep-value names |

Scores are combined with `_weighted_mean()` over `(value, weight)` pairs,
**skipping `None`** — a persona that lacks the data for a check does not get to
guess.

### Why Cathie Wood is here

Five value-leaning personas would agree with each other most of the time, and a
committee that never disagrees provides no signal. Wood scores innovation
exposure, so she rejects exactly the cheap industrial names Graham loves. Her
dissent on a deep-value stock is the value-trap argument stated explicitly. This
is verified in `test_council.py::test_contrarian_bearish_dissent_detected_on_value_trap`.

---

## `engine.py` — consensus and dissent

`CouncilEngine().assess_underlying(snapshot)` returns:

| Field | Meaning |
|---|---|
| `consensus_score` | Combined score, **0–100** |
| `recommendation` | `ACCUMULATE` / `HOLD` / `REDUCE` / `AVOID` |
| `majority_stance` | Modal stance across the six |
| `is_split` | `True` when the committee does not agree |
| `verdicts` | All six `PersonaVerdict`s |
| `dissent` | Personas materially against consensus |

A dissent entry:

```json
{
  "persona": "Charlie Munger",
  "direction": "bullish-minority",
  "score": 75.0,
  "consensus": 53.61,
  "why": ["ROE missing — can't verify quality.", "Gross margin missing."]
}
```

Note `why` is a **list of strings**, not a string. Note also that the score scale
is 0–100, not 0–10 — `specials/BACKEND_FRONTEND_API.md` currently documents 0–10,
which is wrong (see `KNOWN-ISSUES.md`).

---

## `graham_principles.py` — from the actual book

The Graham persona does not use generic value heuristics. The full text of *The
Intelligent Investor* (Zweig commentary edition, 708 pages) was obtained and read,
and the criteria were distilled directly from it.

> The book text and PDF are **gitignored** — copyrighted material is not
> committed. Only short paraphrases appear in code comments.

### The seven defensive tests (Ch.14)

| # | Test | Book threshold |
|---|---|---|
| 1 | Adequate size | ≥ $100M annual sales (≥ $50M assets for utilities) |
| 2 | Strong financial condition | Current ratio ≥ 2 **and** long-term debt ≤ working capital |
| 3 | Earnings stability | Positive earnings in **every** one of the last 10 years |
| 4 | Dividend record | Uninterrupted dividends for **20** years |
| 5 | Earnings growth | ≥ ⅓ growth in per-share earnings over 10 years, 3-year averages |
| 6 | Moderate P/E | ≤ 15× average earnings of the last 3 years |
| 7 | Moderate price/assets | ≤ 1.5× book value, with the P/E × P/B ≤ 22.5 trade-off |

Test 7's trade-off is Graham's own: a multiplier of earnings below 15 justifies a
correspondingly higher multiplier of assets, so 9× earnings against 2.5× book is
acceptable because 9 × 2.5 = 22.5.

`evaluate_defensive()` returns **PASS / FAIL / INCONCLUSIVE** per test.
`margin_of_safety_pct()` implements Ch.20. `inversion_checks()` asks Graham's own
question: what cushion remains if the estimates are wrong?

### Ch.20 — Margin of Safety

Graham's central idea: the cushion is how wrong your estimates can be before you
lose money, and it **must be demonstrable by figures**. If it cannot be
calculated, the position is speculation regardless of how good the story is.
Diversification is its companion — margin of safety on a single name can still
fail; across twenty it is arithmetic.

### Ch.8 — Mr. Market (`mr_market.py`)

`classify_market_mood(recent_prices, vol)` returns a mood of `euphoric`,
`indifferent`, or `panicky`, plus `runup_pct`, `realized_vol_pct`, and
`warning_against_buying`.

The rule from the book: quotations exist for your convenience, not your
instruction. Buy after sharp declines, refrain after substantial advances. When
the mood is `euphoric`, `daily_cycle` blocks new entries — verified in
`test_daily_cycle.py::test_euphoric_market_blocks_new_entries`.

**Limitation, stated plainly:** the classifier uses only run-up and realised
volatility. No breadth, no put/call flow, no sentiment. It is a crude proxy for a
psychological regime and it has **no hysteresis** — the mood is recomputed per
call, so it can flip between two requests on noise. Fix is on the roadmap.

---

## `fundamentals.py` — free data, honest gaps

Alpaca has no fundamentals endpoint, so this uses free public Yahoo Finance
endpoints (cookie + crumb handshake, browser User-Agent, no API key) plus the
chart dividends feed for dividend history. Responses are cached with a 24h TTL
and atomic writes. **Every fetch failure degrades to `None` rather than raising.**

`build_snapshot_with_fundamentals(symbol, price_snapshot)` merges bar-derived
price/volatility with fundamentals into the dict shape the personas expect: P/E,
P/B, current ratio, dividend yield, debt/equity, ROE, margins, growth proxies,
plus derived helpers (earnings yield, a conservative 15×EPS intrinsic value for
margin-of-safety).

**Where history is insufficient, the input stays `None` so the test reports
INCONCLUSIVE rather than FAIL.** A test that cannot be evaluated is not the same
as a test that was failed, and conflating them would slander companies for the
data provider's gaps.

### The fundamentals result — this is the project's turning point

Before fundamentals, all 8 symbols were **HOLD (LOW-CONFIDENCE)**. Six investors
unanimously saying "not sure" about everything is theatre. After merging
fundamentals:

| Symbol | Baseline | Enriched | Δ | Recommendation |
|---|---|---|---|---|
| **NVDA** | 53.9 | **68.0** | +14.1 | HOLD → **ACCUMULATE** |
| **MSFT** | 53.9 | **60.2** | +6.3 | HOLD → **ACCUMULATE** |
| KO | 56.6 | 59.2 | +2.6 | HOLD |
| AAPL | 53.3 | 57.2 | +3.9 | HOLD |
| SPY / QQQ | 56.6 | 55.4 | −1.2 | HOLD |
| JPM | 56.6 | 52.0 | −4.6 | HOLD |
| **TSLA** | 53.9 | **43.8** | −10.1 | HOLD (pushed down) |

Four moved up, four moved down. That two-directional movement is the evidence
that fundamentals are actually being weighed rather than uniformly inflating
scores.

Graham test outcomes on real data: NVDA passes financial strength (current ratio
3.4); KO, MSFT, JPM and the index ETFs pass the 20-year dividend record;
**every single name fails the P/E ≤ 15 ceiling** — a fair verdict on 2026 market
valuations from a 1949 standard, not a bug. AAPL's dividend test is INCONCLUSIVE
because Yahoo returned only ~15 years of coverage.

**ETF caveat:** SPY and QQQ are index funds. Trailing P/E, P/B and per-share
fundamentals do not meaningfully apply, so their enrichment comes via size and
revenue proxies only and their scores stay price/volatility-dominated. This is
noted in the report rather than hidden.

---

## `risk_mitigation.py` — kill-switch and mitigations

Halts new entries on: drawdown > 5%, single-day loss > 2%, or 3 consecutive
stop-losses. See `RISK-MANAGEMENT.md` for the full treatment.

The council report also documents mitigations per risk class:

| Risk | Mitigation |
|---|---|
| Volatility spike | Tier policy tightens delta bands and halves size above 35% vol |
| Assignment risk | Delta ceilings; roll when \|delta\| > 0.40 or DTE < 7 |
| Liquidity risk | Reject candidates on thin option chains |
| Correlation risk | 40% cap on the tech complex measured against deployed overlay capital |
| Catastrophic loss | Kill-switch, checked first in every cycle |

---

## `handoff.py` — how the council instructs the engine

The council's conclusions are not advisory. The HANDOFF section of
`docs/council_report.md` is parsed into a `TierPolicy` that the decision engine
enforces, and blocked candidates carry traces citing the council section that
blocked them.

See `AI-ENGINEER.md` for the tier table and the standing criticism about
markdown-regex parsing.

---

## `report.py` and `run_full_assessment.py`

`report.py` renders assessments to markdown. `run_full_assessment.py` runs the
8-symbol universe and **appends** an addendum to `docs/council_report.md` — it
never overwrites earlier sections, so the report is a chronological record of how
the committee's view changed as data improved.

Current report contents: per-persona criticism, risk mitigation, red-team/blue-team
exchange, the AI Engineer handoff, a Graham Principles Audit, and a
fundamentals-enriched re-assessment.

---

## Honest limitations

1. **Personas are heuristics, not the investors.** These are rule sets inspired
   by published philosophies. Warren Buffett did not write this code and would
   likely disagree with parts of it.
2. **Four of seven Graham tests are usually INCONCLUSIVE** because free sources
   do not supply 10–20 years of history. And at present INCONCLUSIVE counts as
   neutral, which biases the committee **bullish** on thin-data names. This is a
   known defect with a known fix (half-fail weighting), not a design choice.
3. **Mr. Market is a two-input proxy** with no hysteresis.
4. **Consensus weighting is not empirically validated.** No backtest establishes
   that this particular blend of six personas outperforms any one of them.
5. **The fundamentals cache is ephemeral** — in `/tmp`, so a restart silently
   returns the committee to LOW confidence and reverts NVDA/MSFT to HOLD.
