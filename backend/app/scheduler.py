"""Autonomous AI Trading Bot & Background Scheduler for AutoOverlay AI.

Manages scheduled hourly autonomous cycle execution:
- Evaluates Layer 1 Pre-Trade Kill-Switch
- Runs 6-persona Investment Council consensus
- Evaluates exit conditions (Take-Profit, Stop-Loss, Roll)
- Screens new overlay opportunities (Covered Calls & Cash-Secured Puts)
- Resolves concrete OCC option contracts with true midpoint pricing
- Evaluates Layer 2 Pre-Trade Risk Gate
- Submits approved orders if autonomous execution is enabled, or prepares
  order intents for human review
- Records full provenance and audit ledger into SQLite
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler

from .alpaca_client import AlpacaClient, is_configured
from .risk import TradeIntent, evaluate_trade, fetch_snapshot
from .store import get_store, idempotency_key

from .logging_config import get_bot_logger

logger = get_bot_logger()


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        val = os.getenv(name)
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


class BotExecutionResult:
    def __init__(
        self,
        run_id: str,
        started_at: str,
        completed_at: str,
        mode: str,
        halted: bool,
        halt_reasons: List[str],
        directives_count: int,
        orders_evaluated: int,
        orders_submitted: int,
        orders_blocked: int,
        summary: Dict[str, Any],
        error: Optional[str] = None,
    ):
        self.run_id = run_id
        self.started_at = started_at
        self.completed_at = completed_at
        self.mode = mode
        self.halted = halted
        self.halt_reasons = halt_reasons
        self.directives_count = directives_count
        self.orders_evaluated = orders_evaluated
        self.orders_submitted = orders_submitted
        self.orders_blocked = orders_blocked
        self.summary = summary
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "mode": self.mode,
            "halted": self.halted,
            "halt_reasons": self.halt_reasons,
            "directives_count": self.directives_count,
            "orders_evaluated": self.orders_evaluated,
            "orders_submitted": self.orders_submitted,
            "orders_blocked": self.orders_blocked,
            "summary": self.summary,
            "error": self.error,
        }


class BotScheduler:
    """Manages autonomous hourly scheduling and trade execution."""

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(daemon=True)
        self._lock = threading.RLock()
        self._is_running = False
        self._interval_hours = max(0.1, _env_float("BOT_SCHEDULE_INTERVAL_HOURS", 1.0))
        self._autonomous_execution = _env_bool("BOT_EXECUTE_ORDERS", False)
        self._auto_start = _env_bool("BOT_AUTONOMOUS_ENABLED", True)
        self._enforce_market_hours = _env_bool("BOT_ENFORCE_MARKET_HOURS", False)
        self._execution_lock = threading.Lock()

        self._run_count = 0
        self._last_run_time: Optional[datetime] = None
        self._last_result: Optional[BotExecutionResult] = None
        self._history: deque[Dict[str, Any]] = deque(maxlen=50)
        self._last_error: Optional[str] = None
        self._job_id = "autooverlay_hourly_cycle"

        self._scalp_daily_trades = 0
        self._scalp_daily_loss = 0.0
        self._scalp_last_date = datetime.now(timezone.utc).date()

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def interval_hours(self) -> float:
        return self._interval_hours

    @property
    def autonomous_execution(self) -> bool:
        return self._autonomous_execution

    def is_market_open(self) -> bool:
        """Check whether US equity options markets are currently open."""
        if not is_configured():
            now = datetime.now(timezone.utc)
            if now.weekday() >= 5:
                return False
            market_open = now.replace(hour=13, minute=30, second=0, microsecond=0)
            market_close = now.replace(hour=20, minute=0, second=0, microsecond=0)
            return market_open <= now <= market_close
        try:
            client = AlpacaClient()
            clock = client.get_clock()
            return bool(clock.get("is_open", False))
        except Exception as exc:
            logger.warning("Could not fetch Alpaca market clock: %s", exc)
            return True

    def set_autonomous_execution(self, enabled: bool) -> None:
        with self._lock:
            self._autonomous_execution = bool(enabled)
            logger.info("Autonomous order execution set to: %s", self._autonomous_execution)

    def set_interval_hours(self, hours: float) -> None:
        with self._lock:
            self._interval_hours = max(0.1, float(hours))
            if self._is_running:
                self._reschedule()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            next_run = None
            job = self._scheduler.get_job(self._job_id)
            if job and job.next_run_time:
                next_run = job.next_run_time.astimezone(timezone.utc).isoformat()

            return {
                "running": self._is_running,
                "interval_hours": self._interval_hours,
                "autonomous_execution": self._autonomous_execution,
                "enforce_market_hours": self._enforce_market_hours,
                "is_market_open": self.is_market_open(),
                "alpaca_configured": is_configured(),
                "run_count": self._run_count,
                "last_run_at": self._last_run_time.isoformat() if self._last_run_time else None,
                "next_run_at": next_run,
                "last_error": self._last_error,
                "last_result": self._last_result.to_dict() if self._last_result else None,
            }

    def get_history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history)

    def start(self) -> None:
        with self._lock:
            if self._is_running:
                return
            if not self._scheduler.running:
                self._scheduler.start()
            self._reschedule()
            self._is_running = True
            logger.info(
                "BotScheduler started. Running every %.1f hour(s). Auto-submit: %s",
                self._interval_hours,
                self._autonomous_execution,
            )
            # Fire one immediate cycle on startup so the bot is useful without
            # requiring the user to click Run Now.
            if self._auto_start:
                import threading
                threading.Thread(target=self.execute_cycle, kwargs={"manual": True}, daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            if not self._is_running:
                return
            if self._scheduler.get_job(self._job_id):
                self._scheduler.remove_job(self._job_id)
            self._is_running = False
            logger.info("BotScheduler stopped.")

    def _reschedule(self) -> None:
        if self._scheduler.get_job(self._job_id):
            self._scheduler.remove_job(self._job_id)
        minutes = int(self._interval_hours * 60)
        self._scheduler.add_job(
            self.execute_cycle,
            "interval",
            minutes=max(1, minutes),
            id=self._job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
        )

    def _reset_scalp_counters_if_new_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._scalp_last_date:
            self._scalp_last_date = today
            self._scalp_daily_trades = 0
            self._scalp_daily_loss = 0.0

    def _allow_scalp(self, config) -> tuple[bool, str | None]:
        if not config.scalp_mode:
            return False, None
        self._reset_scalp_counters_if_new_day()
        if self._scalp_daily_trades >= max(1, int(config.scalp_max_daily_trades)):
            return False, "scalp daily trade limit reached"
        daily_loss_limit = (config.scalp_max_daily_loss_pct / 100.0) * float(
            self._last_result.summary.get("portfolio_equity") or 0.0
        )
        if daily_loss_limit > 0 and abs(self._scalp_daily_loss) >= daily_loss_limit:
            return False, "scalp daily loss limit reached"
        return True, None

    def _record_scalp_result(self, pnl_change: float) -> None:
        self._reset_scalp_counters_if_new_day()
        self._scalp_daily_trades += 1
        self._scalp_daily_loss += pnl_change

    def execute_cycle(self, manual: bool = False) -> Dict[str, Any]:
        """Execute one complete autonomous cycle through the full pipeline."""
        start_moment = datetime.now(timezone.utc)
        run_id = f"bot-{uuid4().hex[:12]}"
        logger.info("Cycle queued run_id=%s manual=%s", run_id, manual)

        # Prevent overlapping cycle execution
        if not self._execution_lock.acquire(blocking=False):
            logger.warning("Cycle skipped: previous run still active run_id=%s", run_id)
            return {
                "status": "skipped",
                "reason": "cycle_already_in_progress",
                "run_id": run_id,
                "started_at": start_moment.isoformat(),
            }

        try:
            if not manual and self._enforce_market_hours and not self.is_market_open():
                logger.info("Cycle skipped: market closed run_id=%s", run_id)
                return {
                    "status": "skipped",
                    "reason": "market_closed",
                    "run_id": run_id,
                    "started_at": start_moment.isoformat(),
                }

            logger.info("Cycle started run_id=%s manual=%s", run_id, manual)

            store = get_store()
            mode = "live" if is_configured() else "mock"
            orders_submitted = 0
            orders_blocked = 0
            orders_evaluated = 0
            error_msg = None

            from .routes.council import CouncilCycleRequest, council_cycle
            from .routes.agent import _order_intents
            from .routes.strategy import _active_strategy_config

            # 1. Run the daily council cycle
            cycle_req = CouncilCycleRequest()
            # Run async council_cycle safely whether in a running event loop thread or worker thread
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    cycle = pool.submit(asyncio.run, council_cycle(cycle_req)).result(timeout=60.0)
            else:
                cycle = asyncio.run(council_cycle(cycle_req))

            halted = bool(cycle.get("halted", False))
            halt_reasons = list(cycle.get("halt_reasons", []))
            directives = list(cycle.get("directives", []))

            # 2. If halted, record halt audit and return
            if halted:
                store.record_audit(
                    route="BOT /scheduler/cycle",
                    action="autonomous_cycle",
                    outcome="halted",
                    detail={"run_id": run_id, "reasons": halt_reasons},
                )
                res = BotExecutionResult(
                    run_id=run_id,
                    started_at=start_moment.isoformat(),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    mode=mode,
                    halted=True,
                    halt_reasons=halt_reasons,
                    directives_count=len(directives),
                    orders_evaluated=0,
                    orders_submitted=0,
                    orders_blocked=0,
                    summary={"status": "halted", "cycle": cycle},
                )
                self._record_result(res)
                return res.to_dict()

            # 3. Generate and evaluate concrete order intents
            intents = _order_intents(directives)
            config = _active_strategy_config()
            snapshot = fetch_snapshot(config=config)

            executed_orders: List[Dict[str, Any]] = []

            for intent_dict in intents:
                orders_evaluated += 1
                opt_sym = intent_dict.get("option_symbol")
                if not opt_sym:
                    orders_blocked += 1
                    continue

                # Scalping safeguard: enforce max daily trades when scalp mode
                # is active and this intent looks scalp-eligible.
                if config.scalp_mode and len(opt_sym) >= 15:
                    allowed_scalp, scalp_reason = self._allow_scalp(config)
                    if not allowed_scalp:
                        orders_blocked += 1
                        executed_orders.append({
                            "symbol": opt_sym,
                            "status": "blocked",
                            "limit_price": intent_dict.get("limit_price"),
                            "risk": {
                                "allowed": False,
                                "checks": [
                                    {
                                        "name": "scalp_safeguard",
                                        "passed": False,
                                        "severity": "BLOCK",
                                        "detail": scalp_reason or "scalp safeguard blocked",
                                        "values": {"daily_trades": self._scalp_daily_trades},
                                    }
                                ],
                            },
                        })
                        continue

                trade_intent = TradeIntent(
                    symbol=opt_sym,
                    qty=float(intent_dict.get("qty", 1)),
                    side=intent_dict.get("side", "sell"),
                    order_type=intent_dict.get("type", "limit"),
                    time_in_force=intent_dict.get("time_in_force", "day"),
                    limit_price=intent_dict.get("limit_price"),
                    run_id=run_id,
                    directive_ref=f"bot:{intent_dict.get('strategy')}",
                )

                decision = evaluate_trade(trade_intent, snapshot, config)

                order_payload = {
                    "symbol": trade_intent.symbol,
                    "qty": trade_intent.contracts,
                    "side": trade_intent.side,
                    "type": trade_intent.order_type,
                    "time_in_force": trade_intent.time_in_force,
                    "limit_price": trade_intent.limit_price,
                }

                key = idempotency_key(order_payload)

                if not decision.allowed:
                    orders_blocked += 1
                    store.record_intent(
                        key=key,
                        payload=order_payload,
                        risk=decision.to_dict(),
                        mode=mode,
                        status="rejected",
                        run_id=run_id,
                        directive_ref=f"bot:{intent_dict.get('strategy')}",
                    )
                    continue

                # Pre-trade risk gate allowed this trade. Check if auto-execution is enabled.
                if self._autonomous_execution and is_configured():
                    intent_id = store.record_intent(
                        key=key,
                        payload=order_payload,
                        risk=decision.to_dict(),
                        mode="live",
                        status="pending",
                        run_id=run_id,
                        directive_ref=f"bot:{intent_dict.get('strategy')}",
                    )
                    client = AlpacaClient()
                    try:
                        submit_res = client.submit_order(order_payload)
                        orders_submitted += 1
                        store.complete_intent(
                            intent_id,
                            status="submitted",
                            response=submit_res,
                            broker_order_id=str(submit_res.get("id") or ""),
                        )
                        executed_orders.append({
                            "symbol": opt_sym,
                            "order_id": submit_res.get("id"),
                            "status": "submitted",
                            "limit_price": trade_intent.limit_price,
                        })
                    except Exception as exc:
                        store.complete_intent(intent_id, status="failed", error=str(exc))
                        logger.error("Failed submitting order %s: %s", opt_sym, exc)
                else:
                    # Simulated or review-only mode
                    intent_id = store.record_intent(
                        key=key,
                        payload=order_payload,
                        risk=decision.to_dict(),
                        mode=mode,
                        status="simulated",
                        run_id=run_id,
                        directive_ref=f"bot:{intent_dict.get('strategy')}",
                    )
                    executed_orders.append({
                        "symbol": opt_sym,
                        "status": "simulated" if mode == "mock" else "review_ready",
                        "limit_price": trade_intent.limit_price,
                        "risk": decision.to_dict(),
                    })

            store.record_audit(
                route="BOT /scheduler/cycle",
                action="autonomous_cycle",
                outcome="completed",
                detail={
                    "run_id": run_id,
                    "evaluated": orders_evaluated,
                    "submitted": orders_submitted,
                    "blocked": orders_blocked,
                    "auto_execution": self._autonomous_execution,
                },
            )

            res = BotExecutionResult(
                run_id=run_id,
                started_at=start_moment.isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                mode=mode,
                halted=False,
                halt_reasons=[],
                directives_count=len(directives),
                orders_evaluated=orders_evaluated,
                orders_submitted=orders_submitted,
                orders_blocked=orders_blocked,
                summary={
                    "status": "completed",
                    "executed_orders": executed_orders,
                    "cycle_halted": halted,
                },
            )
            self._record_result(res)
            return res.to_dict()

        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.exception("Error during autonomous cycle execution: %s", exc)
            store.record_audit(
                route="BOT /scheduler/cycle",
                action="autonomous_cycle",
                outcome="error",
                detail={"run_id": run_id, "error": error_msg},
            )
            res = BotExecutionResult(
                run_id=run_id,
                started_at=start_moment.isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                mode=mode,
                halted=False,
                halt_reasons=[],
                directives_count=0,
                orders_evaluated=0,
                orders_submitted=0,
                orders_blocked=0,
                summary={},
                error=error_msg,
            )
            self._record_result(res)
            return res.to_dict()
        finally:
            self._execution_lock.release()

    def _record_result(self, result: BotExecutionResult) -> None:
        with self._lock:
            self._run_count += 1
            self._last_run_time = datetime.now(timezone.utc)
            self._last_result = result
            self._last_error = result.error
            self._history.append(result.to_dict())


_BOT_SCHEDULER: Optional[BotScheduler] = None


def get_bot_scheduler() -> BotScheduler:
    global _BOT_SCHEDULER
    if _BOT_SCHEDULER is None:
        _BOT_SCHEDULER = BotScheduler()
        if _BOT_SCHEDULER._auto_start:
            _BOT_SCHEDULER.start()
    return _BOT_SCHEDULER
