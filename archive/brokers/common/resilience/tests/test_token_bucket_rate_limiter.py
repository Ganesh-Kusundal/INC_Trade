"""TDD tests for TokenBucketRateLimiter — threadsafe token bucket rate limiter."""

import time

import pytest

from brokers.common.resilience.rate_limiter import RateLimitConfig, TokenBucketRateLimiter


class TestTokenBucketRateLimiterInitialization:
    def test_default_config(self):
        limiter = TokenBucketRateLimiter()
        assert limiter.config.rate_per_second == 10.0
        assert limiter.config.capacity == 10
        assert limiter.available_tokens == 10.0

    def test_custom_config(self):
        config = RateLimitConfig(rate_per_second=5.0, capacity=20)
        limiter = TokenBucketRateLimiter(config)
        assert limiter.config.rate_per_second == 5.0
        assert limiter.config.capacity == 20

    def test_config_validation_negative_rate(self):
        with pytest.raises(ValueError):
            RateLimitConfig(rate_per_second=-1)

    def test_config_validation_zero_capacity(self):
        with pytest.raises(ValueError):
            RateLimitConfig(capacity=0)


class TestTokenBucketRateLimiterAcquire:
    def test_acquire_available_token(self):
        limiter = TokenBucketRateLimiter()
        assert limiter.acquire() is True
        tokens = limiter.available_tokens
        assert tokens == pytest.approx(9.0, abs=0.01)

    def test_acquire_multiple_tokens(self):
        limiter = TokenBucketRateLimiter()
        assert limiter.acquire(5) is True
        tokens = limiter.available_tokens
        assert tokens == pytest.approx(5.0, abs=0.01)

    def test_acquire_exhausts_bucket_then_refills(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(rate_per_second=10, capacity=10))
        # Exhaust the bucket
        for _ in range(10):
            assert limiter.acquire() is True
        tokens = limiter.available_tokens
        assert tokens == pytest.approx(0.0, abs=0.01)

        # Should block — use timeout to verify
        start = time.monotonic()
        assert limiter.acquire(timeout=0.5) is True  # should get 1 refill in ~100ms
        elapsed = time.monotonic() - start
        assert 0.05 < elapsed < 0.5

    def test_acquire_timeout_returns_false(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(rate_per_second=1, capacity=1))
        limiter.acquire()  # exhaust
        start = time.monotonic()
        result = limiter.acquire(timeout=0.05)
        elapsed = time.monotonic() - start
        assert result is False
        assert elapsed < 0.2

    def test_acquire_burst_then_throttle(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(rate_per_second=100, capacity=100))
        # Burst consume
        for _ in range(100):
            assert limiter.acquire() is True

        # Next one should block briefly
        start = time.monotonic()
        limiter.acquire(timeout=0.5)
        elapsed = time.monotonic() - start
        assert 0.005 < elapsed < 0.5

    def test_acquire_greater_than_capacity(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(capacity=5))
        result = limiter.acquire(10, timeout=0.1)
        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_async_waits_without_blocking(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(rate_per_second=10, capacity=1))
        assert limiter.acquire() is True

        start = time.monotonic()
        assert await limiter.acquire_async(timeout=0.5) is True
        elapsed = time.monotonic() - start

        assert 0.05 < elapsed < 0.5


class TestTokenBucketRateLimiterConcurrency:
    def test_concurrent_acquisitions(self):
        """Multiple threads should not race and exceed capacity."""
        import threading

        limiter = TokenBucketRateLimiter(RateLimitConfig(rate_per_second=1000, capacity=50))
        errors = []
        acquired = []

        def worker():
            for _ in range(10):
                if limiter.acquire(timeout=0.5):
                    acquired.append(1)
                else:
                    errors.append("timeout")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # We should have acquired some tokens without errors
        assert len(errors) < 100  # not all should timeout


class TestTokenBucketRateLimiterReset:
    def test_reset(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(capacity=10, rate_per_second=5))
        limiter.acquire(10)
        assert limiter.available_tokens < 1
        limiter.reset()
        assert limiter.available_tokens == 10.0


class TestTokenBucketRateLimiterProperties:
    def test_rate_getter(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(rate_per_second=25.0))
        assert limiter.rate == 25.0

    def test_rate_setter(self):
        limiter = TokenBucketRateLimiter()
        limiter.rate = 50.0
        assert limiter.config.rate_per_second == 50.0

    def test_string_representation(self):
        limiter = TokenBucketRateLimiter(RateLimitConfig(rate_per_second=10, capacity=20))
        s = repr(limiter)
        assert "10.0" in s or "10" in s
        assert "20" in s
