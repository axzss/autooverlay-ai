"""Structured markdown council report generator with AI-ENGINEER handoff notes."""

from __future__ import annotations

from .engine import CouncilEngine, UnderlyingAssessment
from .personas import PERSONAS


VOL_BANDS = [
    (25, "low-vol",  "0.20–0.35 delta, 30–45 DTE", "Covered calls are primary; CSPs optional"),
    (40, "mid-vol",  "0.25–0.40 delta, 21–35 DTE",  "Balanced CC + CSP wheel; wider bands capture richer premium"),
]


def _vol_profile(vol: float | None) -> tuple[str, str, str]:
    if vol is None:
        return ("unknown-vol", "default 0.15–0.35 delta, 7–45 DTE", "Use config defaults until realized vol is known")
    for cap, name, band, fit in VOL_BANDS:
        if vol <= cap:
            return (name, band, fit)
    return ("high-vol", "0.15–0.30 delta, 14–30 DTE; smaller size",
            "Cash-secured puts preferred over covered calls; keep extra cash reserve")


def _handoff(a: UnderlyingAssessment, underlying: dict) -> list[str]:
    lines = []
    vol = underlying.get("annualized_volatility_pct")
    profile, band, fit = _vol_profile(vol if isinstance(vol, (int, float)) else None)
    rec = a.recommendation
    if rec == "AVOID":
        lines.append(f"- **{a.symbol}** — AVOID: exclude from overlay candidate set this cycle.")
        return lines
    if rec == "STRONG_BUY":
        lines.append(f"- **{a.symbol}** — prime overlay candidate ({profile}): {fit}.")
    elif rec == "ACCUMULATE":
        lines.append(f"- **{a.symbol}** — good overlay candidate ({profile}): {fit}.")
    else:
        lines.append(f"- **{a.symbol}** — HOLD: run overlays only on existing inventory; no new collateral commitment.")
    lines.append(f"  - Suggested entry delta band: **{band}**.")
    if a.is_split:
        lines.append("  - ⚠ Split council — halve normal position size until next review.")
    if a.dissent:
        who = ", ".join(d["persona"] for d in a.dissent)
        lines.append(f"  - Dissent logged ({who}) — monitor thesis-invalidating events before rolling positions.")
    return lines


def generate_report(portfolio: dict, candidates: list[dict],
                    engine: CouncilEngine | None = None,
                    title: str = "Investment Council Report") -> str:
    engine = engine or CouncilEngine()
    assessments = engine.run(portfolio, candidates)
    L: list[str] = [f"# {title}", ""]

    # ---- Executive summary ----
    L += ["## Executive Summary", ""]
    for a in assessments:
        bulls, bears = a.bullish_count, a.bearish_count
        neutrals = len(a.verdicts) - bulls - bears
        split_tag = " — SPLIT VOTE" if a.is_split else ""
        L.append(f"- **{a.symbol}**: consensus **{a.consensus_score:.0f}/100 → {a.recommendation}** "
                 f"({bulls} bullish / {neutrals} neutral / {bears} bearish{split_tag}).")
    L.append("")

    # ---- Per-persona verdicts ----
    L += ["## Per-Persona Verdicts", ""]
    for key, persona in PERSONAS.items():
        L += [f"### {persona.name}", "", f"*Philosophy:* {persona.philosophy}", ""]
        for a in assessments:
            v = a.verdicts[key]
            L.append(f"**{a.symbol} — {v.score:.0f}/100 ({v.stance})**")
            for b in v.bullets:
                L.append(f"- {b}")
            L.append("")

    # ---- Dissent section ----
    L += ["## Dissent & Minority Reports", ""]
    any_dissent = False
    for a in assessments:
        for d in a.dissent:
            any_dissent = True
            L.append(f"- **{d['persona']} vs consensus on {a.symbol}** ({d['direction']}): "
                     f"scores {d['score']:.0f} against consensus {d['consensus']:.0f}.")
            for w in d["why"][:3]:
                L.append(f"  - {w}")
    if not any_dissent:
        L.append("_No material dissent this session — the council is aligned._")
    L.append("")

    # ---- Consensus table ----
    L += ["## Consensus Table", "",
          "| Symbol | " + " | ".join(p.name.split()[-1] for p in PERSONAS.values())
          + " | Weighted Consensus | Recommendation | Split? |",
          "|" + "---|" * (len(PERSONAS) + 4)]
    for a in assessments:
        cells = " | ".join(f"{a.verdicts[k].score:.0f}" for k in PERSONAS)
        L.append(f"| {a.symbol} | {cells} | **{a.consensus_score:.0f}** | {a.recommendation} | {'yes' if a.is_split else 'no'} |")
    L.append("")

    # ---- Handoff notes for the AI ENGINEER agent ----
    L += ["## Handoff Notes — FOR THE AI ENGINEER AGENT", "",
          "Overlay-fit guidance per underlying. Apply these as candidate-screen inputs;",
          "the decision engine retains final veto via portfolio guards.", ""]
    pos_by_symbol = {p.get("symbol"): p for p in portfolio.get("positions", [])}
    for a in assessments:
        u = next((c for c in candidates if c.get("symbol") == a.symbol), {})
        u = {**pos_by_symbol.get(a.symbol, {}), **u}
        L += _handoff(a, u)

    import datetime
    L += ["", f"_Generated {datetime.datetime.utcnow():%Y-%m-%d %H:%M UTC} by the Investment Council module._"]
    return "\n".join(L)
