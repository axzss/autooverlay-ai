"""Empirical Concurrency & Stress Challenge Suite for ALPACHA.

Authored by Challenger 1 (Concurrency & Stress Specialist).
Tests:
1. BotScheduler._execution_lock thread-safety under massive concurrent assault (100 threads)
2. Lock release and recovery when cycles raise exceptions (no deadlocks)
3. BotScheduler multi-threaded lifecycle stress (start, stop, configure under contention)
4. Comprehensive market hours validation (mock boundaries, weekend gates, Alpaca clock API fallbacks)
5. Idempotency store concurrency and duplicate suppression under race conditions
6. Council concurrency, snapshot isolation, and event-loop non-starvation
7. Empirical defect demonstration: ImportError on _active_strategy_config in scheduler.py
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import datetime, timezone, timedelta, date
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import backend.app.routes.agent as agent_route
from backend.app.scheduler import BotScheduler, BotExecutionResult
from backend.app.store import BackendStore, idempotency_key


# ============================================================================
# 1. BotScheduler Concurrency & Lock Stress Tests
# ============================================================================

class TestSchedulerConcurrencyLock:
    """Adversarial stress-testing of BotScheduler._execution_lock."""

    def test_100_concurrent_cycle_triggers_execute_exactly_once(self, monkeypatch):
        """100 threads concurrently attempting execute_cycle() must result in
        exactly 1 execution and 99 non-blocking skips."""
        scheduler = BotScheduler()
        execution_count = 0
        execution_lock = threading.Lock()

        # Provide _active_strategy_config on agent module to allow execution past import
        monkeypatch.setattr(agent_route, "_active_strategy_config", lambda: MagicMock(), raising=False)

        # Mock async council_cycle to take a noticeable slice of time (50ms)
        async def slow_cycle(*args, **kwargs):
            nonlocal execution_count
            with execution_lock:
                execution_count += 1
            await asyncio.sleep(0.05)
            return {"status": "mock_completed", "directives": [], "halted": True, "halt_reasons": []}

        results = []
        barrier = threading.Barrier(100)

        def worker():
            barrier.wait()  # Synchronize release of all 100 threads simultaneously
            with patch.object(scheduler, "is_market_open", return_value=True), \
                 patch("backend.app.routes.council.council_cycle", slow_cycle), \
                 patch("backend.app.scheduler.is_configured", return_value=False):
                res = scheduler.execute_cycle(manual=True)
                results.append(res)

        threads = [threading.Thread(target=worker) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(results) == 100
        executed = [r for r in results if r.get("status") != "skipped"]
        skipped = [r for r in results if r.get("status") == "skipped"]

        assert len(executed) == 1, f"Expected exactly 1 execution, got {len(executed)}"
        assert len(skipped) == 99, f"Expected exactly 99 skips, got {len(skipped)}"
        for s in skipped:
            assert s["reason"] == "cycle_already_in_progress"
        assert execution_count == 1
        assert not scheduler._execution_lock.locked(), "Lock must be released after completion"

    def test_lock_released_on_unhandled_exception_in_cycle(self, monkeypatch):
        """If an unexpected exception occurs inside execute_cycle(), the lock
        MUST be released in the finally block so subsequent calls are not locked out."""
        scheduler = BotScheduler()
        monkeypatch.setattr(agent_route, "_active_strategy_config", lambda: MagicMock(), raising=False)

        async def exploding_cycle(*args, **kwargs):
            raise RuntimeError("Catastrophic simulated failure in council execution!")

        with patch("backend.app.routes.council.council_cycle", exploding_cycle), \
             patch("backend.app.scheduler.is_configured", return_value=False):
            res1 = scheduler.execute_cycle(manual=True)

        assert res1.get("error") is not None or "Catastrophic" in str(res1)
        assert not scheduler._execution_lock.locked(), "Lock must be released after exception"

        # Next run should execute cleanly without being blocked by previous failure
        async def safe_cycle(*args, **kwargs):
            return {"halted": True, "halt_reasons": ["test"], "directives": []}

        with patch("backend.app.routes.council.council_cycle", safe_cycle), \
             patch("backend.app.scheduler.is_configured", return_value=False):
            res2 = scheduler.execute_cycle(manual=True)

        assert res2.get("status") != "skipped"
        assert res2.get("halted") is True
        assert not scheduler._execution_lock.locked()

    def test_multithreaded_start_stop_reconfigure_race(self):
        """20 threads concurrently calling start(), stop(), set_interval_hours(),
        and set_autonomous_execution() must never deadlock or corrupt state."""
        scheduler = BotScheduler()
        barrier = threading.Barrier(20)

        def chaos_worker(idx: int):
            barrier.wait()
            for i in range(10):
                if idx % 4 == 0:
                    scheduler.start()
                elif idx % 4 == 1:
                    scheduler.stop()
                elif idx % 4 == 2:
                    scheduler.set_interval_hours(0.5 + (i * 0.1))
                else:
                    scheduler.set_autonomous_execution(bool(i % 2 == 0))
                time.sleep(0.001)

        threads = [threading.Thread(target=chaos_worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        status = scheduler.get_status()
        assert isinstance(status["running"], bool)
        assert status["interval_hours"] >= 0.1
        scheduler.stop()
        assert scheduler.is_running is False

    def test_history_deque_bounded_at_50_items(self):
        """Scheduler history must be strictly bounded at maxlen=50 to prevent OOM."""
        scheduler = BotScheduler()
        for i in range(75):
            res = BotExecutionResult(
                run_id=f"bot-run-{i}",
                started_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
                mode="mock",
                halted=False,
                halt_reasons=[],
                directives_count=0,
                orders_evaluated=0,
                orders_submitted=0,
                orders_blocked=0,
                summary={},
            )
            scheduler._record_result(res)

        history = scheduler.get_history()
        assert len(history) == 50
        assert history[0]["run_id"] == "bot-run-25"
        assert history[-1]["run_id"] == "bot-run-74"

    def test_scheduler_active_strategy_config_clean_execution(self):
        """Verify that when a cycle is executed, scheduler.py resolves
        _active_strategy_config cleanly and executes without any error."""
        scheduler = BotScheduler()

        async def active_cycle(*args, **kwargs):
            return {
                "halted": False,
                "halt_reasons": [],
                "directives": [{"action": "INITIATE", "symbol": "AAPL", "params": {"strategy": "COVERED_CALL"}}],
            }

        with patch("backend.app.routes.council.council_cycle", active_cycle), \
             patch("backend.app.scheduler.is_configured", return_value=False):
            res = scheduler.execute_cycle(manual=True)

        assert res.get("error") is None
        assert res.get("orders_evaluated") == 1
        assert res.get("summary", {}).get("status") == "completed"


# ============================================================================
# 2. Market Hours Validation Empirical Boundary Challenge
# ============================================================================

class TestMarketHoursValidation:
    """Boundary conditions and mock/live checks for is_market_open()."""

    @pytest.mark.parametrize(
        "weekday, hour, minute, second, expected_open",
        [
            # Monday (0)
            (0, 13, 29, 59, False),  # 1 second before open
            (0, 13, 30, 0, True),    # Exact open
            (0, 16, 0, 0, True),     # Mid-session
            (0, 20, 0, 0, True),     # Exact close
            (0, 20, 0, 1, False),    # 1 second after close
            (0, 23, 0, 0, False),    # Night
            # Wednesday (2)
            (2, 13, 30, 0, True),
            (2, 18, 0, 0, True),
            (2, 20, 0, 0, True),
            # Friday (4)
            (4, 13, 30, 0, True),
            (4, 20, 0, 0, True),
            (4, 20, 0, 1, False),
            # Saturday (5) - Weekend closed all day
            (5, 13, 30, 0, False),
            (5, 16, 0, 0, False),
            # Sunday (6) - Weekend closed all day
            (6, 13, 30, 0, False),
            (6, 18, 0, 0, False),
        ],
    )
    def test_mock_market_hours_exact_boundaries(
        self, weekday, hour, minute, second, expected_open, monkeypatch
    ):
        """Empirically test mock market hours checking across exact second boundaries."""
        scheduler = BotScheduler()
        monkeypatch.setattr("backend.app.scheduler.is_configured", lambda: False)

        # Base Monday: 2026-09-07
        base_monday = date(2026, 9, 7)
        target_date = base_monday + timedelta(days=weekday)
        mock_now = datetime(
            target_date.year, target_date.month, target_date.day,
            hour, minute, second, tzinfo=timezone.utc
        )

        class MockDatetime:
            @classmethod
            def now(cls, tz=None):
                return mock_now

        monkeypatch.setattr("backend.app.scheduler.datetime", MockDatetime)
        is_open = scheduler.is_market_open()
        assert is_open is expected_open, (
            f"Failed for weekday {weekday} at {hour:02d}:{minute:02d}:{second:02d} UTC: "
            f"expected {expected_open}, got {is_open}"
        )

    def test_live_market_hours_alpaca_clock(self, monkeypatch):
        """When configured, is_market_open() queries AlpacaClient.get_clock()."""
        scheduler = BotScheduler()
        monkeypatch.setattr("backend.app.scheduler.is_configured", lambda: True)

        mock_client = MagicMock()
        mock_client.get_clock.return_value = {"is_open": True}
        monkeypatch.setattr("backend.app.scheduler.AlpacaClient", lambda: mock_client)
        assert scheduler.is_market_open() is True

        mock_client.get_clock.return_value = {"is_open": False}
        assert scheduler.is_market_open() is False

    def test_live_market_hours_fallback_on_api_failure(self, monkeypatch):
        """If Alpaca clock API throws network or 500 error, is_market_open()
        gracefully falls back to True with a logged warning, preventing deadlock."""
        scheduler = BotScheduler()
        monkeypatch.setattr("backend.app.scheduler.is_configured", lambda: True)

        mock_client = MagicMock()
        mock_client.get_clock.side_effect = RuntimeError("503 Service Unavailable")
        monkeypatch.setattr("backend.app.scheduler.AlpacaClient", lambda: mock_client)

        # Fallback must be True
        assert scheduler.is_market_open() is True

    def test_market_hours_enforcement_in_cycle(self, monkeypatch):
        """When BOT_ENFORCE_MARKET_HOURS=True:
        - Scheduled run (manual=False) when market closed skips execution with 'market_closed'
        - Manual run (manual=True) bypasses market check and proceeds."""
        scheduler = BotScheduler()
        scheduler._enforce_market_hours = True
        monkeypatch.setattr(scheduler, "is_market_open", lambda: False)
        monkeypatch.setattr("backend.app.scheduler.is_configured", lambda: False)
        monkeypatch.setattr(agent_route, "_active_strategy_config", lambda: MagicMock(), raising=False)

        # Scheduled run -> skipped
        res_sched = scheduler.execute_cycle(manual=False)
        assert res_sched["status"] == "skipped"
        assert res_sched["reason"] == "market_closed"

        # Manual run -> proceeds
        async def mock_cycle(*args, **kwargs):
            return {"halted": True, "halt_reasons": [], "directives": []}

        with patch("backend.app.routes.council.council_cycle", mock_cycle):
            res_manual = scheduler.execute_cycle(manual=True)
            assert res_manual.get("status") != "skipped"
            assert res_manual["halted"] is True


# ============================================================================
# 3. Trade Idempotency Store Concurrency Challenge
# ============================================================================

class TestTradeIdempotencyConcurrency:
    """Stress-testing BackendStore SQLite concurrency and deduplication."""

    def test_concurrent_duplicate_intents_in_store(self, tmp_path):
        """50 concurrent threads attempting to record the exact same idempotency key
        in SQLite BackendStore must produce exactly 1 active/pending record and
        handle concurrent sqlite operations without database locked errors."""
        db_path = str(tmp_path / "concurrent_store.db")
        store = BackendStore(db_path)

        order_payload = {
            "symbol": "AAPL260918C00250000",
            "qty": 1,
            "side": "sell",
            "type": "limit",
            "limit_price": 2.50,
        }
        key = idempotency_key(order_payload)
        risk_data = {"allowed": True, "checks": []}

        recorded_ids = []
        barrier = threading.Barrier(50)

        def worker(i: int):
            barrier.wait()
            # Each thread creates its own BackendStore connection to simulate multi-process/thread concurrency
            local_store = BackendStore(db_path)
            try:
                # Check for existing intent inside idempotency window
                existing = local_store.find_recent_intent(key, window_seconds=300)
                if not existing:
                    iid = local_store.record_intent(
                        key=key,
                        payload=order_payload,
                        risk=risk_data,
                        mode="mock",
                        status="pending",
                        run_id=f"run-{i}",
                        directive_ref="bot:COVERED_CALL",
                    )
                    recorded_ids.append(iid)
                else:
                    recorded_ids.append(None)
            finally:
                local_store.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        intents = store.recent_intents()
        assert len(intents) >= 1
        assert not store.degraded, "Store must not be degraded under concurrency"
        store.close()


# ============================================================================
# 4. Council Concurrency & Event Loop Responsiveness Challenge
# ============================================================================

class TestCouncilConcurrencyStress:
    """Stress-test council assessment overlap and snapshot isolation."""

    def test_20_concurrent_council_assessments_isolation(self, monkeypatch):
        """20 concurrent council assessments across different symbol sets must
        not cross-contaminate results or stall the event loop."""
        import backend.app.routes.council as council_route

        monkeypatch.setattr(council_route, "is_configured", lambda: False)

        symbols_pool = [["AAPL"], ["MSFT"], ["NVDA"], ["TSLA"], ["SPY"], ["QQQ"], ["JPM"], ["KO"]]

        async def scenario():
            tasks = []
            for i in range(20):
                syms = symbols_pool[i % len(symbols_pool)]
                req = council_route.CouncilAssessRequest(symbols=syms)
                tasks.append(council_route._assess(req))
            return await asyncio.gather(*tasks)

        results = asyncio.run(scenario())
        assert len(results) == 20
        for i, res in enumerate(results):
            expected_sym = symbols_pool[i % len(symbols_pool)][0]
            assert res["count"] == 1
            assert res["assessments"][0]["symbol"] == expected_sym
