"""Daily Cycle — autonomous daily orchestration of the overlay council.

run_daily_cycle(portfolio_positions, cash, open_option_positions=None,
                **kwargs) runs, in order:

  0. Kill-switch check FIRST (risk_mitigation.evaluate_kill_switch) —
     if halted, return immediately with halt reasons and skip everything else.
  a. Snapshot + fundamentals merge: injected snapshot dicts win; missing
     symbols may fall back to the sibling fundamentals provider
     (agent.council.fundamentals) when ``allow_provider=True``.
  b. Mr. Market mood from the index proxy (SPY vol / drawdown) via
     mr_market.classify_market_mood.
  c. CouncilEngine assessments for held underlyings + candidates.
  d. Exit evaluation on open overlays (ExitManager).
  e. New-entry screening with tier policies (handoff) + concentration and
     council §6 sector caps (PortfolioAnalyst). Blocked entries are returned
     as MONITOR directives carrying their cited blocking traces.

Output: {"halted", "kill_switch", "mr_market", "assessments", "directives",
         ...} where every directive is
    {action, symbol, params, priority, reasoning_trace, provenance}
and provenance cites which council rule / persona / test drove it
(e.g. 'council §6', 'graham test 4', 'tier:mid', 'exit:take_profit').

Deterministic over its inputs; no network unless explicitly allowed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .risk_mitigation import evaluate_kill_switch
    from .engine import CouncilEngine
    from .mr_market import classify_market_mood
    from .handoff import effective_policy_for_symbol
except ImportError:  # pragma: no cover - direct-script imports
    from council.risk_mitigation import evaluate_kill_switch
    from council.engine import CouncilEngine
    from council.mr_market import classify_market_mood
    from council.handoff import effective_policy_for_symbol

try:
    from ..config import StrategyConfig
    from ..exit_manager import ExitManager
    from ..portfolio_analyst import PortfolioAnalyst
except ImportError:  # pragma: no cover - direct-script imports
    from exit_manager import ExitManager
    from portfolio_analyst import PortfolioAnalyst
    try:
        from config import StrategyConfig
    except ImportError:  # last resort
        StrategyConfig = None  # type: ignore[assignment,misc]

def _normalize_trace(trace) -> list[str]:
    """Ensure *trace* is a list[str]; coerce tuples, sets, or bare strings."""
    if isinstance(trace, list):
        return [str(t) for t in trace]
    if isinstance(trace, (tuple, set)):
        return [str(t) for t in trace]
    if isinstance(trace, str):
        return [trace]
    return [str(trace)]


# Priority ladder (1 = act first).
PRIORITY_EXIT = 1        # TAKE_PROFIT / STOP_LOSS closes
PRIORITY_ROLL = 2        # rolls reset risk before new risk is added
PRIORITY_INITIATE = 3    # screened new entries
PRIORITY_MONITOR_BLOCKED = 4   # entries that wanted to initiate but were blocked
PRIORITY_HOLD = 5        # passive holds / watches


def _position_value(p: dict) -> float:
    mv = p.get("market_value")
    if mv is None:
        price = p.get("current_price") or p.get("avg_entry_price") or 0
        mv = float(p.get("qty") or 0) * float(price)
    return float(p.get("collateral", mv))


def _build_portfolio_state(positions: List[dict], cash: float,
                           overrides: Optional[dict]) -> dict:
    """Derive kill-switch inputs; explicit overrides always win.

    ``peak_equity`` is a HIGH-WATER MARK, so a caller-supplied value is treated
    as a *candidate* max and never allowed to lower the mark below current
    equity. The live backend passes the account's CURRENT equity here (finding
    B), which made peak == equity and the drawdown ratio always 0. Taking the
    max is what makes that harmless from inside this layer.
    """
    equity = sum(_position_value(p) for p in positions) + float(cash or 0)
    ov = overrides or {}
    state = {
        "equity": equity,
        "peak_equity": ov.get("peak_equity"),
        "prev_equity": ov.get("prev_equity"),
        "consecutive_stop_losses": ov.get("consecutive_stop_losses"),
        "overlay_peak_equity": ov.get("overlay_peak_equity"),
    }
    # A peak below current equity is not a peak.
    try:
        supplied_peak = float(state["peak_equity"]) if state["peak_equity"] is not None else None
    except (TypeError, ValueError):
        supplied_peak = None
    state["peak_equity"] = max(supplied_peak, equity) if supplied_peak is not None else equity
    return {k: v for k, v in state.items() if v is not None}


def _consecutive_stop_losses(exit_decisions: List[dict]) -> int:
    """Count trailing STOP_LOSS exits in this cycle's exit evaluations.

    Nothing in the system produced this signal before — the kill-switch read it
    only from caller overrides and the live backend never sets it, so the
    consecutive-stop-loss trigger could not fire in production (finding B).

    This is the within-cycle producer. It is a floor, not the full answer: a
    durable count across cycles needs the W1 exit_event ledger. Any non-stop
    exit resets the run, matching the documented semantics.
    """
    count = 0
    for decision in reversed(exit_decisions or []):
        action = str((decision or {}).get("action") or "").upper()
        if action == "STOP_LOSS":
            count += 1
        elif action in ("TAKE_PROFIT", "ROLL"):
            break
    return count



def _load_snapshots(symbols: List[str],
                    injected: Optional[Dict[str, dict]],
                    allow_provider: bool,
                    fetch_timeout_seconds: float = 5.0,
                    fetch_retries: int = 2) -> tuple[Dict[str, dict], List[str]]:
    """Merge injected snapshots first; optionally top up via the sibling
    fundamentals provider (never raises — failures degrade to missing).

    Provider calls are wrapped with a per-symbol timeout and retry. On
    persistent failure the bundled docs/market_snapshots.json is loaded as
    fallback (only when the filesystem is readable).
    """
    import concurrent.futures
    import json as _json
    import os as _os
    from pathlib import Path as _Path
    from concurrent.futures import TimeoutError as _FuturesTimeoutError
    import time as _time

    snaps: Dict[str, dict] = {}
    for sym in symbols:
        s = (injected or {}).get(sym)
        if isinstance(s, dict):
            u = dict(s)
            u.setdefault("symbol", sym)
            snaps[sym] = u
    missing = [s for s in symbols if s not in snaps]
    if missing and allow_provider:
        per_symbol = max(fetch_timeout_seconds, 0.1)
        attempts = max(fetch_retries, 1)
        # Overall wall-clock budget for the whole step. The old code applied
        # fetch_timeout_seconds per symbol via `with ThreadPoolExecutor(...)`,
        # but __exit__ calls shutdown(wait=True), which JOINS the worker before
        # the except clause runs — so the timeout never interrupted anything and
        # the real bound was the provider's own 15s socket timeout times four
        # HTTP calls times every symbol and retry (up to ~16 min).
        budget = per_symbol * attempts * max(len(missing), 1)
        deadline = _time.monotonic() + budget

        still_missing: list[str] = list(missing)
        # ONE executor for the batch, not one per symbol per attempt.
        pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=min(8, max(len(still_missing), 1)))
        try:
            futures = {pool.submit(_provider_fetch_snapshot, sym): sym
                       for sym in still_missing}
            remaining = max(deadline - _time.monotonic(), 0.0)
            try:
                for fut in concurrent.futures.as_completed(futures,
                                                          timeout=remaining):
                    sym = futures[fut]
                    try:
                        snap = fut.result(timeout=0)
                    except Exception:
                        continue  # this symbol degrades to missing
                    if isinstance(snap, dict) and snap.get("symbol"):
                        snaps[snap["symbol"]] = snap
                        if sym in still_missing:
                            still_missing.remove(sym)
                        if sym in missing:
                            missing.remove(sym)
            except (_FuturesTimeoutError, TimeoutError):
                pass  # budget exhausted — whatever landed is what we use
            finally:
                for fut in futures:
                    fut.cancel()
        finally:
            # Do NOT wait: an in-flight socket read would re-impose the very
            # stall this budget exists to prevent.
            pool.shutdown(wait=False)


        # Fallback to bundled docs/market_snapshots.json for any still-missing
        if still_missing:
            try:
                repo_root = str(_Path(__file__).resolve().parents[2])
                snap_path = _os.path.join(repo_root, "docs", "market_snapshots.json")
                if _os.path.isfile(snap_path):
                    with open(snap_path) as fh:
                        bundled = _json.load(fh)
                    for entry in bundled:
                        sym = entry.get("symbol", "").upper()
                        if sym in still_missing:
                            snaps[sym] = entry
                            still_missing.remove(sym)
                            if sym in missing:
                                missing.remove(sym)
            except Exception:
                pass  # graceful degradation — never block the cycle
    return snaps, missing


def _provider_fetch_snapshot(symbol: str) -> dict | None:
    """Call the sibling fundamentals provider for a single symbol."""
    try:
        from .fundamentals import build_snapshot_with_fundamentals
        return build_snapshot_with_fundamentals(symbol, {"symbol": symbol})
    except Exception:
        return None


def _provenance(source: str, detail: str | None = None) -> dict:
    p = {"source": source}
    if detail:
        p["detail"] = detail
    return p


def _persona_provenance(assessment) -> List[dict]:
    provs = []
    for key, v in assessment.verdicts.items():
        provs.append({
            "source": f"persona:{v.persona}",
            "detail": f"score {v.score:.0f} → {v.stance}",
        })
    return provs


def _directive(action: str, symbol: str, params: dict, priority: int,
               trace: list[str] | tuple | str | None,
               provenance: list[dict]) -> dict:
    return {
        "action": action,
        "symbol": symbol,
        "params": params,
        "priority": priority,
        "reasoning_trace": _normalize_trace(trace),
        "provenance": provenance,
    }


def run_daily_cycle(
    portfolio_positions: List[dict],
    cash: float,
    open_option_positions: Optional[List[dict]] = None,
    *,
    candidate_snapshots: Optional[Dict[str, dict]] = None,
    candidates: Optional[List[str]] = None,
    portfolio_state_overrides: Optional[dict] = None,
    config=None,
    allow_provider: bool = False,
    fetch_timeout_seconds: float = 5.0,
    fetch_retries: int = 2,
) -> dict:
    """Run one full daily council cycle. See module docstring for ordering.

    fetch_timeout_seconds: per-symbol timeout for provider snapshot fetches.
    fetch_retries: number of retry attempts per symbol on failure.
    On persistent failure the bundled docs/market_snapshots.json is used as
    fallback (if available).
    """
    config = config or StrategyConfig()
    positions = [dict(p) for p in (portfolio_positions or [])]
    open_options = [dict(o) for o in (open_option_positions or [])]
    held = [str(p.get("symbol", "")).upper() for p in positions
            if p.get("symbol")]
    wanted: List[str] = []
    for sym in held + [c.upper() for c in (candidates or [])]:
        if sym and sym not in wanted:
            wanted.append(sym)

    result: Dict[str, Any] = {
        "halted": False,
        "steps_run": [],
        "directives": [],
        "assessments": [],
    }

    def step(name: str) -> None:
        result["steps_run"].append(name)

    # ---- 0. KILL SWITCH FIRST ------------------------------------------- #
    portfolio_state = _build_portfolio_state(
        positions, cash, portfolio_state_overrides)
    # Overlay detection needs the OPTION book. Passing the equity book here was
    # finding A1: every long stock position counted as "overlay collateral".
    kill = evaluate_kill_switch(portfolio_state, config=config,
                                positions=list(positions) + list(open_options))
    result["kill_switch"] = kill

    result["portfolio_state"] = {
        k: round(float(v), 2) if isinstance(v, (int, float)) else v
        for k, v in portfolio_state.items()}
    if kill["halted"]:
        result["halted"] = True
        result["halt_reasons"] = list(kill["reasons"])
        result["directives"] = [_directive(
            "HOLD", "*", {},
            PRIORITY_HOLD,
            ["kill-switch HALT: trading suspended — " + "; ".join(kill["reasons"]),
             "all further cycle steps skipped per risk_mitigation policy"],
            [_provenance("kill-switch",
                         "; ".join(kill["reasons"]))])]
        return result  # short-circuit: nothing else runs
    step("kill_switch")

    # ---- a. Snapshots + fundamentals ------------------------------------- #
    snapshots, missing = _load_snapshots(
        wanted, candidate_snapshots, allow_provider,
        fetch_timeout_seconds=fetch_timeout_seconds,
        fetch_retries=fetch_retries)
    result["snapshot_symbols_missing"] = missing
    step("snapshots")

    # ---- b. Mr. Market mood from index proxy ------------------------------ #
    spy = snapshots.get("SPY") or {}
    prices = spy.get("recent_prices") or []
    mood = classify_market_mood(list(prices), spy.get("vol30d_annualized_pct"))
    result["mr_market"] = {
        "mood": mood.mood,
        "runup_pct": round(mood.runup_pct, 2) if mood.runup_pct is not None else None,
        "realized_vol_pct": round(mood.realized_vol_pct, 2)
        if mood.realized_vol_pct is not None else None,
        "favorable_for_buying": mood.is_favorable_for_buying,
        "warning_against_buying": mood.is_warning_against_buying,
        "guidance": list(mood.guidance),
    }
    step("mr_market")

    # ---- c. Council assessments ------------------------------------------ #
    engine = CouncilEngine()
    analyst = PortfolioAnalyst(config=config)
    portfolio_value = float(portfolio_state["equity"])
    portfolio_ctx = {
        "positions": positions,
        "cash": cash,
        "portfolio_value": portfolio_value,
    }
    assessed: Dict[str, Any] = {}
    for sym in wanted:
        snap = snapshots.get(sym)
        if not snap:
            continue
        u = dict(snap)
        u.setdefault("annualized_volatility_pct",
                     snap.get("vol30d_annualized_pct"))
        assessment = engine.assess_underlying(u)
        assessed[sym] = assessment
        result["assessments"].append({
            "symbol": sym,
            "consensus_score": assessment.consensus_score,
            "recommendation": assessment.recommendation,
            "majority_stance": assessment.majority_stance,
            "is_split": assessment.is_split,
            "verdicts": {k: {"persona": v.persona, "score": v.score,
                             "stance": v.stance, "bullets": list(v.bullets)}
                         for k, v in assessment.verdicts.items()},
            "dissent": [dict(d) for d in assessment.dissent],
            "mr_market_context": assessment.mr_market_context,
        })
    step("council_assessments")

    directives: List[dict] = []

    # ---- d. Exit evaluation on open overlays ------------------------------ #
    exit_mgr = ExitManager(config=config)
    exit_decisions = list(exit_mgr.evaluate_positions(open_options))
    # Produce the consecutive-stop-loss signal. Before this, nothing computed it
    # and the live backend never supplied it, so that kill-switch trigger was
    # unreachable in production (finding B). An explicit override still wins.
    observed_stops = _consecutive_stop_losses(exit_decisions)
    result["consecutive_stop_losses_observed"] = observed_stops
    if "consecutive_stop_losses" not in portfolio_state and observed_stops:
        portfolio_state["consecutive_stop_losses"] = observed_stops
        recheck = evaluate_kill_switch(
            portfolio_state, config=config,
            positions=list(positions) + list(open_options))
        if recheck["halted"]:
            result["halted"] = True
            result["kill_switch"] = recheck
            result["halt_reasons"] = list(recheck["reasons"])
            result["directives"] = [_directive(
                "HOLD", "*", {}, PRIORITY_HOLD,
                ["kill-switch HALT after exit evaluation — "
                 + "; ".join(recheck["reasons"]),
                 f"{observed_stops} stop-loss exits observed this cycle",
                 "new entries suppressed per risk_mitigation policy"],
                [_provenance("kill-switch:post-exit",
                             "; ".join(recheck["reasons"]))])]
            step("exits")
            return result
    for ex in exit_decisions:

        action = ex["action"]
        if action == "TAKE_PROFIT" or action == "STOP_LOSS":
            directive_action, prio = "EXIT", PRIORITY_EXIT
        elif action == "ROLL":
            directive_action, prio = "ROLL", PRIORITY_ROLL
        else:
            directive_action, prio = "HOLD", PRIORITY_HOLD
        provenance = [_provenance(
            f"exit:{action.lower()}",
            ex.get("rule_triggered") or "no mechanical exit rule triggered")]
        trace = list(ex.get("reasoning_trace") or [])
        trace.append(f"source: ExitManager mechanical rules → {action}")
        directives.append(_directive(
            directive_action, ex.get("symbol", "?"),
            {"strategy": ex.get("strategy"),
             "contracts": ex.get("contracts"),
             "option_symbol": ex.get("option_symbol"),
             "order_side": ex.get("order_side"),
             "rule_triggered": ex.get("rule_triggered"),
             "premium_captured_pct": ex.get("premium_captured_pct")},
            prio, trace, provenance))
    step("exits")

    # ---- e. New-entry screening + holds/monitors on held names ------------ #
    blocked_traces_by_symbol: Dict[str, List[str]] = {}

    def screen_entry(sym: str, assessment) -> None:
        snap = snapshots[sym] or {}
        vol = snap.get("annualized_volatility_pct") \
            or snap.get("vol30d_annualized_pct") or 0
        try:
            vol_f = float(vol)
        except (TypeError, ValueError):
            vol_f = 999.0  # unknown vol treated conservatively as high tier
        policy, tier_notes = effective_policy_for_symbol(sym, vol_f)
        provs = [_provenance(
            f"tier:{policy.name}",
            "; ".join(tier_notes)),
            _provenance("council handoff HANDOFF section",
                        f"{policy.name} tier policy "
                        f"(delta {policy.delta_min:.2f}-{policy.delta_max:.2f})")]
        persona_provs = _persona_provenance(assessment)
        trace: List[str] = [
            f"council consensus {assessment.consensus_score:.1f} → "
            f"{assessment.recommendation}",
            f"Mr. Market mood: {result['mr_market']['mood']} "
            f"(buying {'favorable' if result['mr_market']['favorable_for_buying'] else 'not favorable'})",
        ] + tier_notes

        bull_ok = assessment.recommendation in ("STRONG_BUY", "ACCUMULATE")
        mood_ok = not result["mr_market"]["warning_against_buying"]
        graham_failed = []
        for key, v in assessment.verdicts.items():
            if "graham" in key.lower() and not v.is_bullish:
                graham_failed.append(key)
        if not bull_ok or not mood_ok:
            why = []
            if not bull_ok:
                why.append(f"council says {assessment.recommendation}")
            if not mood_ok:
                why.append("Mr. Market euphoric — refrain from new buying")
            trace.append(f"new entry NOT permitted ({'; '.join(why)})")
            directives.append(_directive(
                "MONITOR", sym,
                {"consensus_score": assessment.consensus_score,
                 "recommendation": assessment.recommendation},
                PRIORITY_HOLD, trace,
                provs + persona_provs
                + [_provenance("mr_market ch.8", result["mr_market"]["mood"])]))
            return

        # Graham persona citation when bullish (e.g. passed defensive tests).
        graham_prov: List[dict] = []
        gv = assessment.verdicts.get("graham")
        if gv is not None and gv.is_bullish:
            graham_prov.append(_provenance(
                "graham tests ch.14",
                f"graham persona bullish at {gv.score:.0f}: "
                + " | ".join(gv.bullets[:3])))

        # Concentration + sector cap gating (collateral estimate: 100 shares
        # × price for covered-call style sizing scaled by tier size multiplier).
        price = float(snap.get("price") or 0)
        collateral = round(price * 100 * max(policy.size_multiplier, 0.01), 2)
        existing_for_sym = sum(_position_value(p) for p in positions
                               if str(p.get("symbol", "")).upper() == sym)
        allowed, gate_trace = analyst.check_new_position(
            sym, collateral, existing_for_sym, portfolio_value, cash,
            contracts=1, existing_positions=positions)
        full_trace = trace + gate_trace
        entry_params = {
            "strategy_allowed": list(policy.allowed_strategies),
            "delta_band": [policy.delta_min, policy.delta_max],
            "max_dte": policy.max_dte,
            "size_multiplier": policy.size_multiplier,
            "estimated_collateral": collateral,
            "consensus_score": assessment.consensus_score,
        }
        if allowed:
            full_trace.append(
                "all gates passed → INITIATE new overlay per tier policy")
            directives.append(_directive(
                "INITIATE", sym, entry_params, PRIORITY_INITIATE, full_trace,
                provs + persona_provs + graham_prov
                + [_provenance("concentration ≤25% rule", "gate passed"),
                   _provenance("council §6 sector cap", "gate passed")]))
        else:
            cited = [ln for ln in gate_trace if "BLOCKED" in ln or "§6" in ln]
            full_trace.append(
                "entry BLOCKED by portfolio gates → MONITOR only; cited: "
                + ("; ".join(cited) if cited else "see gate traces"))
            directives.append(_directive(
                "MONITOR", sym,
                dict(entry_params, blocked=True,
                     blocking_rules=[ln for ln in cited]),
                PRIORITY_MONITOR_BLOCKED, full_trace,
                provs + persona_provs + graham_prov
                + [_provenance("concentration ≤25% rule",
                               "BLOCKED" if any("concentration" in ln
                                                for ln in cited) else "passed"),
                   _provenance("council §6 sector cap",
                               "BLOCKED" if any("§6" in ln or "sector-cap"
                                                in ln for ln in cited)
                               else "passed")]))
            blocked_traces_by_symbol[sym] = full_trace

    for sym, assessment in assessed.items():
        if sym not in held:
            screen_entry(sym, assessment)

    # Holds/MONITORs for held underlyings without an open option evaluated.
    handled_exit_syms = {d["symbol"] for d in directives
                         if d["action"] in ("EXIT", "ROLL")}
    for sym in held:
        assessment = assessed.get(sym)
        provs = _persona_provenance(assessment) if assessment else []
        base = {
            "consensus_score": assessment.consensus_score if assessment else None,
            "recommendation": assessment.recommendation if assessment else None,
        }
        if sym in handled_exit_syms:
            continue
        rec = assessment.recommendation if assessment else "HOLD"
        if rec in ("AVOID",):
            directives.append(_directive(
                "MONITOR", sym, dict(base, watch="council bearish on holding"),
                PRIORITY_MONITOR_BLOCKED,
                [f"council consensus "
                 f"{(assessment.consensus_score if assessment else 0):.1f} → AVOID "
                 "on a currently-held underlying — watch closely, no adds",
                 "source: CouncilEngine weighted consensus"],
                provs + [_provenance("council consensus",
                                     f"{rec} on held name")]))
        else:
            directives.append(_directive(
                "HOLD", sym, base, PRIORITY_HOLD,
                [f"held underlying {sym}: council consensus "
                 f"{(assessment.consensus_score if assessment else 0):.1f} → {rec}; "
                 "keep existing overlay, collect premium",
                 "source: CouncilEngine weighted consensus"],
                provs + [_provenance("council consensus",
                                     f"{rec} on held name")]))
    step("entry_screening")

    directives.sort(key=lambda d: d["priority"])
    result["directives"] = directives
    step("directives")
    result["blocked_entries"] = {
        sym: tr for sym, tr in blocked_traces_by_symbol.items()}  # type: ignore[assignment]
    return result
