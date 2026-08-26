# Investment Council Report — AutoOverlay AI

**Date:** 2026-08-26
**Universe:** AAPL, MSFT, NVDA, TSLA, SPY, QQQ, JPM, KO
**Data source:** `docs/market_snapshots.json` (real Alpaca snapshots, 30 trading days)
**Engine:** `agent.council.engine.CouncilEngine` (six personas, default weights)

---

## 1. Executive Summary

The Council assessed eight underlyings using **price/volatility data only**: last price, day change, 30-day annualized realized volatility, drawdown from 52-week high, and 52-week range.

> **DATA-AS-OF CAVEAT [LOW-CONFIDENCE]:** The snapshot set contains **no fundamental data** (no moat, margins, P/E, growth, ROE, sector tags). Every persona that depends on fundamentals degraded to neutral defaults, compressing all scores toward the HOLD band. **All recommendations in this report are tagged LOW-CONFIDENCE** and must be re-run once a fundamental-enriched snapshot is available. The only genuinely differentiated signal available was realized volatility (via Dalio/Wood personas).

**Headline outcomes:**
- SPY / QQQ / JPM / KO lead at **56.6/100 → HOLD** (2 of 6 personas bullish; Dalio ACCUMULATE on low vol, Munger STRONG_BUY on absence-of-negative).
- AAPL trails at **53.3/100 → HOLD**; MSFT / NVDA / TSLA at **53.9/100 → HOLD**.
- **No ticker reaches ACCUMULATE or STRONG_BUY at council level.** This is itself the finding: with price/vol only, the council refuses to bless entries.
- Charlie Munger registered a **bullish-minority dissent on all four single-name tech/growth names**, on inversion logic ("no obvious position-killer visible").

---

## 2. Market Data Table

| Symbol | Price ($) | Day Chg (%) | Vol30d Ann. (%) | Drawdown from 52w High (%) | 52w Low ($) | 52w High ($) |
|--------|----------:|------------:|----------------:|---------------------------:|------------:|-------------:|
| AAPL | 309.89 | -0.16 | 30.5 | -8.9 | 232.27 | 333.75 |
| MSFT | 491.55 | +0.87 | 48.9 | -6.1 | 356.86 | 523.66 |
| NVDA | 212.96 | +2.15 | 35.9 | -5.5 | 167.07 | 225.31 |
| TSLA | 350.24 | +0.37 | 59.1 | -27.2 | 311.19 | 481.07 |
| SPY  | 765.79 | +0.31 | 12.2 | -1.5 | 634.04 | 776.30 |
| QQQ  | 710.66 | +0.61 | 21.5 | -3.9 | 562.50 | 739.82 |
| JPM  | 356.67 | +0.07 | 17.6 | -2.3 | 282.75 | 362.82 |
| KO   | 91.63  | -0.36 | 24.4 | -0.4 | 65.64 | 91.63 |

Volatility tiers: **Low** (<20%): SPY, JPM · **Mid** (20–35%): QQQ, KO, AAPL · **High** (>35%): NVDA, MSFT, TSLA.
Notable: TSLA carries both the highest vol (59.1%) and deepest drawdown (-27.2%) — the riskiest underlying in the set. KO sits at its 52-week high (-0.4% drawdown).

---

## 3. Per-Persona Verdicts (Top Candidates)

Top candidates by consensus score: SPY, QQQ, JPM, KO (56.6) and the tech cohort MSFT/NVDA/TSLA/AAPL (53.3–53.9). Verdicts below are actual engine output.

### SPY — consensus 56.6 → HOLD
| Persona | Score | Stance | Key rationale (verbatim bullets) |
|---|---:|---|---|
| Warren Buffett | 50.0 | HOLD | "No identifiable moat"; margins/leverage/earnings history missing |
| Charlie Munger | 75.0 | STRONG_BUY | "Inversion found no obvious position-killer in available data" |
| Ray Dalio | 70.0 | ACCUMULATE | "Realized vol 12% — risk-parity friendly." |
| Benjamin Graham | 50.0 | HOLD | Insufficient data — neutral abstention |
| Peter Lynch | 47.5 | HOLD | "No PEG computable"; "No story provided" |
| Cathie Wood | 44.0 | HOLD | "'unknown' lacks visible innovation catalysts" |

**Criticism of this verdict given data limits:** Munger's 75 is an *absence-of-evidence* score, not evidence of quality — with zero fundamentals, "nothing kills it" is nearly tautological for an index ETF and should not be read as conviction. Dalio's 70 rests entirely on one number (12% vol); a vol-calm regime can invert in days. Graham's abstention is the most honest score here. Treat the 56.6 as "no red flags in what we could see," nothing more. [LOW-CONFIDENCE]

### QQQ — consensus 56.6 → HOLD
Same persona pattern as SPY (Munger 75, Dalio 70 on 22% vol, rest neutral). **Criticism:** QQQ is a concentrated tech basket — its low realized vol masks single-factor (megacap tech) exposure the snapshot cannot see. The Dalio risk-parity pass overstates diversification. [LOW-CONFIDENCE]

### JPM — consensus 56.6 → HOLD
Same pattern (Dalio 70 on 18% vol). **Criticism:** bank fundamentals (capital ratios, credit cycle) are precisely what the missing data would have carried; a price/vol-only ACCUMULATE-leaning signal on a financial is the weakest kind. Buffett's circle-of-competence check also never ran (no sector field). [LOW-CONFIDENCE]

### KO — consensus 56.6 → HOLD
Same pattern (Dalio 70 on 24% vol). **Criticism:** sitting at its 52-week high with no valuation data means the council is endorsing buying at an unexamined peak; classic value criteria (the one thing that would justify KO) were unavailable. [LOW-CONFIDENCE]

### MSFT / NVDA / TSLA — consensus 53.9 → HOLD each
Buffett 50 (no moat data), Munger 75 (bullish-minory dissent), Dalio 48 ("risk budget hog; size down" at 49%/36%/59% vol), Graham 50 (abstain), Lynch 47.5, Wood 49.2 (vol noted as convexity toll). **Criticism:** the entire spread between these names and SPY comes from one vol penalty line; TSLA's 59% vol deserves more than a 22-point haircut versus reality, and MSFT's 49% vol is anomalously high versus its history — possibly a snapshot-window artifact worth re-checking before sizing anything off it. [LOW-CONFIDENCE]

### AAPL — consensus 53.3 → HOLD
Identical structure; Wood scores lower (44.0) because its 30.5% vol misses even her convexity threshold. **Criticism:** AAPL's near-identical score to TSLA despite wildly different risk profiles shows the model's blindness without fundamentals — do not treat the ranking as meaningful differentiation. [LOW-CONFIDENCE]

---

## 4. Dissent Section

Actual engine dissent output — **Charlie Munger, bullish-minority, on AAPL, MSFT, NVDA, TSLA** (score 75.0 vs consensus ~53–54):

> "ROE missing — can't verify quality." / "Gross margin missing." / "Inversion found no obvious position-killer in available data."

Reading: Munger's inversion method survives the data vacuum better than additive scoring — he found *no disqualifier*, and dissents bullish against a HOLD consensus on all four single names. **Council note:** his own rationale concedes the verification inputs are absent; the dissent is a "cleared for further diligence" flag, not a buy order. No bearish dissents were recorded anywhere in the universe.

---

## 5. Consensus Table & Final Recommendations

| Symbol | Consensus (/100) | Recommendation | Bullish / Neutral / Bearish | Split? | Dissent | Confidence |
|---|---:|---|---|---|---|---|
| SPY | 56.6 | HOLD | 2 / 4 / 0 | No | None | LOW |
| QQQ | 56.6 | HOLD | 2 / 4 / 0 | No | None | LOW |
| JPM | 56.6 | HOLD | 2 / 4 / 0 | No | None | LOW |
| KO | 56.6 | HOLD | 2 / 4 / 0 | No | None | LOW |
| MSFT | 53.9 | HOLD | 1 / 5 / 0 | No | Munger bull | LOW |
| NVDA | 53.9 | HOLD | 1 / 5 / 0 | No | Munger bull | LOW |
| TSLA | 53.9 | HOLD | 1 / 5 / 0 | No | Munger bull | LOW |
| AAPL | 53.3 | HOLD | 1 / 5 / 0 | No | Munger bull | LOW |

**Final recommendation:** **HOLD across the universe — deploy no new capital until fundamental enrichment.** If the overlay must trade anyway, restrict to the low-vol tier (SPY first, then JPM) at minimum size, and treat all single-name tech entries as blocked pending re-scoring.

---

## 6. Risk Mitigation

### Vol-spike-2x exposure analysis
Stress every name to 2× its 30d realized vol:

| Symbol | Current vol | 2× stressed | Assessment |
|---|---:|---:|---|
| SPY | 12.2% | 24.4% | Survives comfortably; premium income regime improves |
| JPM | 17.6% | 35.2% | Acceptable but watch financial-sector beta |
| QQQ | 21.5% | 43.0% | Marginal — covered calls OK, CSP collateral strained |
| KO | 24.4% | 48.8% | Single-stock event risk (non-index) becomes real |
| AAPL | 30.5% | 61.0% | Position sizing must halve |
| NVDA | 35.9% | 71.8% | High — tighter strikes, smaller size |
| MSFT | 48.9% | 97.8% | Near-option-impossibility territory; verify snapshot artifact first |
| TSLA | 59.1% | 118.2% | **Do not run naked short-vol structures at any size** under 2× stress |

### Assignment risk
Short puts assigned near the money in a vol spike force purchase into falling knives. Highest assignment probability under stress: TSLA (-27.2% already in drawdown, highest vol), then MSFT/NVDA. Mitigation: roll or close shorts at ≤21 DTE when delta > 0.30; prefer cash-secured only where full collateral is reserved; never sell uncovered puts on the high-vol tier.

### Liquidity risk
All eight names are large-cap/ETF with deep option chains, so outright liquidity risk is low. Residual risks: wide quotes in TSLA options during vol spikes; SPY's high absolute price ($765.79) makes CSP collateral ~$76.6k per contract — material against the position caps below.

### Correlation risk — tech concentration
AAPL, MSFT, NVDA are mega-cap tech and QQQ is a tech-heavy index: **four of eight underlyings load on one factor**. In a tech-specific drawdown, short puts across all four correlate toward simultaneous assignment. **Recommendation: impose a sector-level cap — combined tech-complex exposure (AAPL+MSFT+NVDA+QQQ) limited to ≤40% of deployed overlay capital, and count QQQ as tech, not as a diversifier.**

### Kill-switch criteria (matches `agent/config.py` `kill_*` fields)
Trading halts when any of:
- Portfolio drawdown from peak equity **> 5%** (`kill_max_drawdown_pct = 5.0`)
- Single-day portfolio loss **> 2%** (`kill_max_single_day_loss_pct = 2.0`)
- **3 consecutive stop-loss exits** (`kill_consecutive_stop_losses = 3`)
Evaluated via `agent.council.risk_mitigation.evaluate_kill_switch`; on halt, no new entries until manual review.

---

## 7. Red Team / Blue Team — Top Consensus Pick (SPY)

**Blue Team (pro-SPY):** Highest council score (56.6, tied), lowest vol in universe (12.2%), shallowest drawdown among ETFs (-1.5%), Dalio risk-parity approved, deepest option market, and the only underlying whose 2× vol stress (24.4%) stays inside normal covered-call parameters. It is also the only pick that needs no fundamental analysis to justify — an S&P 500 index is the diversified-by-construction answer to the missing-data problem.

**Red Team (anti-SPY):** (1) The 56.6 score is inflated by Munger's absence-of-evidence 75 — remove it and SPY is a bland HOLD like everything else. (2) At $765.79/contract, CSPs immobilize ~$76.6k; against a $250k account with a 25% per-position cap, one contract consumes most of a position budget — capital efficiency is poor vs. selling on a lower-priced proxy. (3) Selling covered calls/index puts on SPY caps upside in melt-up regimes; the vol-spike-2x scenario cuts both ways — a calm-vol entry today may be a low-premium, high-regret entry if vol mean-reverts upward. (4) Concentration argument inverted: if everyone's fallback is SPY, the book has zero idiosyncratic alpha and is 100% beta.

**Verdict:** Blue team prevails on risk grounds *for a first, small deployment only* — SPY as the pilot underlying, sized minimally (see §8), explicitly labeled a beta-harvest position pending fundamental-enriched rescoring of single names. Red Team's capital-efficiency point stands: consider spreading pilot premium across SPY + JPM rather than concentrating in SPY alone.

---

## 8. HANDOFF — To AI Engineer Agent

**CSP vs covered-call eligibility by volatility tier** (from §2 tiers + §6 stress):

| Tier | Underlyings | CSP | Covered Call | Notes |
|---|---|---|---|---|
| Low (<20% vol) | SPY, JPM | ✅ PASS | ✅ PASS | Pilot tier; full standard bands |
| Mid (20–35%) | QQQ, KO, AAPL | ⚠️ PASS w/ reduced size | ✅ PASS | QQQ counts toward tech cap |
| High (>35%) | NVDA, MSFT, TSLA | ❌ BLOCKED pending rescore | ⚠️ Only if long shares already held | Do not add short-put exposure |

**Suggested delta band adjustments:**
- Default band (assumed ~0.15–0.30 short delta) applies to the low tier unchanged.
- Mid tier: shift to **0.10–0.25** (sell closer to OTM than default).
- High tier if ever unlocked (NVDA/MSFT/TSLA): tighten to **0.05–0.15**, DTE ≤ 30, and mandatory stop at 2× premium received. For TSLA specifically: given 59.1% vol + -27.2% drawdown, require **delta ≤ 0.10** and half-size until vol < 45%.

**Position sizing under constraints (25% single-position cap, 10% cash reserve):**
- On a reference $250k account: cash reserve $25k untouchable; deployable overlay capital ≈ $225k; max single position = $62.5k.
- One SPY CSP ≈ $76.6k collateral → **exceeds the 25% cap; either skip SPY CSPs or use defined-risk spreads (bull put spread) instead**. JPM/KO/AAPL CSPs (~$35k/$9k/$31k) fit within the cap.
- Tech complex (AAPL+MSFT+NVDA+QQQ) ≤ 40% of deployed capital per §6 correlation rule.
- Suggested pilot allocation: JPM CSP (1 contract, ~$35.7k) + KO CSP (1 contract, ~$9.2k) + mid-tier covered calls only against existing holdings — total well under caps, leaving ≥90% of deployable capital in reserve until fundamentals arrive and the council re-runs at HIGH confidence.

---

*Report generated from real Alpaca snapshots (`docs/market_snapshots.json`, n_days_used=30 per ticker) and live `CouncilEngine` output. No code in `agent/` or `backend/` was modified.*

---

## 9. Graham Principles Audit — *The Intelligent Investor* (Graham, Zweig ed.)

Distilled from the full text into `agent/council/graham_principles.py` (Ch. 14 seven defensive tests; Ch. 15 enterprising approaches incl. net-nets; Ch. 8 Mr. Market psychology → `agent/council/mr_market.py`; Ch. 20 margin of safety + inversion). Book text kept local only (gitignored).

### How far the previous screening fell short

| Ch. 14 test | Book criterion | Old persona behavior | Gap now closed |
|---|---|---|---|
| 1. Adequate size | ≥$100M sales (industrial) / $50M assets (utility) | Not scored at all | Scored |
| 2. Financial condition | Current ratio ≥2 AND LT debt ≤ working capital | Only current ratio | Both legs scored |
| 3. Earnings stability | Some earnings **each** of past 10 years | Allowed 2 losing years in 10 — wrong | Strict: any deficit year fails |
| 4. Dividend record | Uninterrupted **20 years** | "dividend_yield > 0 today" — badly short | 20y uninterrupted record required |
| 5. Earnings growth | ≥1/3 over 10y (3-yr averages) | Not scored | Scored at 33.3% |
| 6. Moderate P/E | ≤15× average earnings of past 3 years | P/E ≤ 15 on trailing only | Ceiling retained, keyed to 3-yr avg earnings input |
| 7. Price/assets | ≤1.5× book, or PExPB ≤22.5 tradeoff | Product check existed but not as a formal test | Formal test incl. the 9x-earnings/2.5x-assets tradeoff |

Also previously missing: earnings-yield-vs-bond-rate rule (E/P should clear high-grade bond yields), net-current-asset (net-net) bargain test, and any inversion reasoning.

### Risk mitigation per Graham's own warnings

- **Speculation vs investment (Ch. 20):** a true investment requires a margin demonstrable by figures and reasoning. The persona now labels sub-15% (or negative) margin cases explicitly as speculation, not merely low-scored.
- **Margin-of-safety erosion:** MoS depends entirely on price paid — large at one price, nonexistent higher. Inversion bullets quantify exactly how much estimate error survives: e.g., at 45x earnings, reversion to Graham's 15x ceiling alone implies ~67% downside with zero change in fundamentals.
- **Fair-weather buying:** Graham's chief-loss warning — mistaking prosperity for earning power — is enforced by strict test 3 (no deficit years) rather than averaging.
- **Inflation:** fixed claims erode; equities are not automatic hedges. Council macro inputs (`macro_inflation_pct`) feed Dalio; Graham's answer is demanding real earning power over bond rates (now an explicit scoring component).
- **Market timing / Mr. Market (Ch. 8):** `mr_market_context` on every `UnderlyingAssessment` classifies mood (euphoric / indifferent / panicky) from recent prices + realized vol, with guidance to buy when Mr. Market is frightened, refrain/sell when euphoric, and otherwise ignore quotations and attend to operations and dividends.

### Caveats

Graham's thresholds are 1972 figures ("all our minimum figures must be arbitrary"); they are screening floors, not valuation outputs. The council applies them as exclusion tests with weighted penalties — faithful to their purpose of eliminating most candidates — while margin of safety remains the central, price-dependent concept that no static screen substitutes for.
