"""Integration tests for QuotaScheduler priority and headroom reservation."""

import threading

import pytest

from brokers.common.capabilities import RateLimitProfile
from brokers.common.errors import QuotaExhaustedError
from brokers.common.quota_scheduler import PriorityClass, QuotaScheduler


class TestQuotaScheduler:
    def test_acquire_and_release_execution_critical(self):
        scheduler = QuotaScheduler(reserved_headroom=0.20)
        scheduler.register_profile(
            "dhan",
            RateLimitProfile(endpoint_class="orders", sustained_rps=10.0, burst_rps=10.0),
        )
        token = scheduler.acquire("dhan", "orders", PriorityClass.EXECUTION_CRITICAL)
        assert token.broker_id == "dhan"
        assert token.priority_class == "EXECUTION_CRITICAL"
        scheduler.release(token)

    def test_headroom_for_returns_ratio_between_zero_and_one(self):
        scheduler = QuotaScheduler()
        scheduler.register_profile(
            "dhan",
            RateLimitProfile(endpoint_class="historical", sustained_rps=5.0, burst_rps=10.0),
        )
        ratio = scheduler.headroom_for("dhan", "historical")
        assert 0.0 <= ratio <= 1.0

    def test_metrics_snapshot_lists_registered_buckets(self):
        scheduler = QuotaScheduler()
        scheduler.register_profile(
            "upstox",
            RateLimitProfile(endpoint_class="quotes", sustained_rps=1.0, burst_rps=2.0),
        )
        metrics = scheduler.metrics_snapshot()
        assert len(metrics) == 1
        assert metrics[0].broker_id == "upstox"
        assert metrics[0].endpoint_class == "quotes"

    def test_live_stream_control_rejects_immediately_when_exhausted(self):
        scheduler = QuotaScheduler(reserved_headroom=0.50)
        scheduler.register_profile(
            "dhan",
            RateLimitProfile(endpoint_class="quotes", sustained_rps=100.0, burst_rps=1.0),
        )
        scheduler.acquire("dhan", "quotes", PriorityClass.EXECUTION_CRITICAL)
        with pytest.raises(QuotaExhaustedError) as exc_info:
            scheduler.acquire("dhan", "quotes", PriorityClass.LIVE_STREAM_CONTROL)
        assert exc_info.value.priority_class == "LIVE_STREAM_CONTROL"

    def test_execution_can_use_reserved_headroom_when_non_reserved_exhausted(self):
        scheduler = QuotaScheduler(reserved_headroom=0.50)
        scheduler.register_profile(
            "dhan",
            RateLimitProfile(endpoint_class="orders", sustained_rps=100.0, burst_rps=2.0),
        )
        # Drain non-reserved capacity (1 token reserved for execution in 2-token bucket)
        scheduler.acquire("dhan", "orders", PriorityClass.HISTORICAL_BACKFILL)
        # Execution should still succeed using reserved headroom
        token = scheduler.acquire("dhan", "orders", PriorityClass.EXECUTION_CRITICAL)
        assert token.priority_class == "EXECUTION_CRITICAL"

    def test_concurrent_acquires_are_thread_safe(self):
        scheduler = QuotaScheduler()
        scheduler.register_profile(
            "dhan",
            RateLimitProfile(endpoint_class="orders", sustained_rps=1000.0, burst_rps=50.0),
        )
        errors: list[Exception] = []
        acquired = []

        def worker():
            try:
                t = scheduler.acquire("dhan", "orders", PriorityClass.PORTFOLIO_READ)
                acquired.append(t)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(acquired) == 20
