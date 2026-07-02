"""Tests for EndpointRateLimiter — per-endpoint rate limiter."""

from __future__ import annotations

import threading
import time

from brokers.common.resilience.rate_limiter import EndpointRateLimiter


class TestEndpointRateLimiter:
    def test_acquire_blocks_until_allowed(self):
        limiter = EndpointRateLimiter(rate_per_second=100.0, capacity=10)
        start = time.monotonic()
        limiter.acquire("/test")
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_acquire_per_endpoint(self):
        limiter = EndpointRateLimiter(rate_per_second=10.0, capacity=2)
        limiter.acquire("/endpoint1")
        limiter.acquire("/endpoint1")
        limiter.acquire("/endpoint2")
        limiter.acquire("/endpoint2")

    def test_acquire_with_timeout(self):
        limiter = EndpointRateLimiter(rate_per_second=1.0, capacity=1)
        limiter.acquire("/test")
        result = limiter.acquire("/test", timeout=0.01)
        assert result is None

    def test_rate_property(self):
        limiter = EndpointRateLimiter(rate_per_second=50.0)
        assert limiter.rate == 50.0
        limiter.rate = 100.0
        assert limiter.rate == 100.0

    def test_concurrent_acquire(self):
        limiter = EndpointRateLimiter(rate_per_second=1000.0, capacity=100)
        results = []

        def worker():
            limiter.acquire("/concurrent")
            results.append(True)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 10
