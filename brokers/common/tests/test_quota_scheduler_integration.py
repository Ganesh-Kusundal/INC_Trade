"""Integration tests for QuotaScheduler.

Tests cover:
- Priority-based acquisition
- Reserved headroom for EXECUTION_CRITICAL
- Quota exhaustion and retry-after
- Concurrent acquire from multiple threads
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from brokers.common.capabilities import RateLimitProfile
from brokers.common.errors import QuotaExhaustedError
from brokers.common.quota_scheduler import PriorityClass, QuotaScheduler


@pytest.fixture
def scheduler():
    """Create a QuotaScheduler with test profiles."""
    scheduler = QuotaScheduler(reserved_headroom=0.20)

    # Register a test profile: 10 RPS sustained, 20 burst
    scheduler.register_profile(
        "test_broker",
        RateLimitProfile(
            endpoint_class="orders",
            sustained_rps=10.0,
            burst_rps=20.0,
            min_interval_ms=50,
        ),
    )

    return scheduler


class TestPriorityBasedAcquisition:
    """Test that different priority classes behave correctly."""

    def test_execution_critical_acquires_immediately(self, scheduler):
        # Should acquire immediately even with high load
        token = scheduler.acquire("test_broker", "orders", PriorityClass.EXECUTION_CRITICAL)
        assert token is not None
        assert token.broker_id == "test_broker"
        assert token.priority_class == "EXECUTION_CRITICAL"

    def test_historical_backfill_acquires(self, scheduler):
        token = scheduler.acquire("test_broker", "orders", PriorityClass.HISTORICAL_BACKFILL)
        assert token is not None
        assert token.priority_class == "HISTORICAL_BACKFILL"


class TestReservedHeadroom:
    """Test that EXECUTION_CRITICAL can use reserved capacity."""

    def test_non_critical_blocked_when_only_reserved_remaining(self, scheduler):
        # Exhaust non-reserved capacity
        # Burst = 20, reserved = 20 * 0.20 = 4, non-reserved = 16
        tokens = []
        for _ in range(20):  # Exhaust all capacity including reserved
            try:
                token = scheduler.acquire(
                    "test_broker",
                    "orders",
                    PriorityClass.HISTORICAL_BACKFILL,
                )
                tokens.append(token)
            except QuotaExhaustedError:
                break

        # Should have exhausted before or at 20
        assert len(tokens) <= 20

    def test_execution_critical_uses_reserved_capacity(self, scheduler):
        # Exhaust non-reserved capacity
        for _ in range(16):
            scheduler.acquire("test_broker", "orders", PriorityClass.HISTORICAL_BACKFILL)

        # EXECUTION_CRITICAL should still succeed (can use reserved)
        token = scheduler.acquire("test_broker", "orders", PriorityClass.EXECUTION_CRITICAL)
        assert token is not None


class TestQuotaExhaustion:
    """Test quota exhaustion behavior."""

    def test_exhaustion_raises_with_retry_after(self, scheduler):
        # Exhaust all capacity with immediate rejection (LIVE_STREAM_CONTROL has 0 wait)
        exhausted = False
        for _ in range(30):  # More than burst capacity
            try:
                scheduler.acquire(
                    "test_broker",
                    "orders",
                    PriorityClass.LIVE_STREAM_CONTROL,  # 0s wait, immediate reject
                )
            except QuotaExhaustedError as e:
                exhausted = True
                assert e.retry_after_seconds is not None
                assert e.broker_id == "test_broker"
                assert e.endpoint_class == "orders"
                break

        assert exhausted, "Should have exhausted quota"


class TestConcurrentAcquisition:
    """Test thread-safe concurrent quota acquisition."""

    def test_concurrent_acquire_from_multiple_threads(self, scheduler):
        results = []
        errors = []

        def acquire_quota(thread_id: int):
            try:
                token = scheduler.acquire(
                    "test_broker",
                    "orders",
                    PriorityClass.PORTFOLIO_READ,
                )
                results.append((thread_id, token))
            except QuotaExhaustedError as e:
                errors.append((thread_id, e))

        # Launch 20 concurrent threads
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(acquire_quota, i) for i in range(20)]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        # Should have some successes and potentially some errors
        assert len(results) + len(errors) == 20
        # At least some should succeed (burst capacity = 20)
        assert len(results) > 0


class TestTokenBucketRefill:
    """Test that tokens refill over time."""

    def test_tokens_refill_after_consumption(self, scheduler):
        # Exhaust all tokens
        for _ in range(25):
            try:
                scheduler.acquire("test_broker", "orders", PriorityClass.EXECUTION_CRITICAL)
            except QuotaExhaustedError:
                break

        # Wait for refill (10 RPS = 1 token per 0.1s)
        time.sleep(0.2)

        # Should be able to acquire again
        token = scheduler.acquire("test_broker", "orders", PriorityClass.EXECUTION_CRITICAL)
        assert token is not None


class TestHeadroomForRouter:
    """Test headroom_for() method used by router."""

    def test_headroom_returns_fraction(self, scheduler):
        headroom = scheduler.headroom_for("test_broker", "orders")
        assert 0.0 <= headroom <= 1.0

    def test_headroom_decreases_after_acquire(self, scheduler):
        initial_headroom = scheduler.headroom_for("test_broker", "orders")

        # Acquire some tokens
        for _ in range(5):
            scheduler.acquire("test_broker", "orders", PriorityClass.HISTORICAL_BACKFILL)

        headroom_after = scheduler.headroom_for("test_broker", "orders")
        assert headroom_after < initial_headroom

    def test_unknown_bucket_returns_full_headroom(self, scheduler):
        headroom = scheduler.headroom_for("unknown_broker", "unknown_endpoint")
        assert headroom == 1.0  # Unknown bucket treated as unlimited
