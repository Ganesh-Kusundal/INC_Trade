"""TDD tests for MultiBucketRateLimiter — manages multiple rate limit buckets by category."""

import pytest

from brokers.common.resilience.rate_limiter import MultiBucketRateLimiter, RateLimitConfig


class TestMultiBucketRateLimiter:
    def test_empty_buckets(self):
        limiter = MultiBucketRateLimiter({})
        assert limiter.categories() == []

    def test_single_bucket(self):
        configs = {"orders": RateLimitConfig(rate_per_second=10, capacity=10)}
        limiter = MultiBucketRateLimiter(configs)
        assert "orders" in limiter.categories()
        assert limiter.acquire("orders") is True

    def test_multiple_buckets(self):
        configs = {
            "orders": RateLimitConfig(rate_per_second=10, capacity=10),
            "quotes": RateLimitConfig(rate_per_second=1, capacity=1),
            "data": RateLimitConfig(rate_per_second=5, capacity=20),
        }
        limiter = MultiBucketRateLimiter(configs)
        assert len(limiter.categories()) == 3

        # Each bucket works independently
        assert limiter.acquire("orders") is True
        assert limiter.acquire("quotes") is True
        assert limiter.acquire("data") is True

    def test_unknown_category(self):
        limiter = MultiBucketRateLimiter({"orders": RateLimitConfig()})
        with pytest.raises(ValueError, match="Unknown category"):
            limiter.acquire("unknown")

    def test_bucket_independence(self):
        """One bucket being exhausted should not affect others."""
        configs = {
            "small": RateLimitConfig(rate_per_second=10, capacity=1),
            "large": RateLimitConfig(rate_per_second=10, capacity=100),
        }
        limiter = MultiBucketRateLimiter(configs)
        # Exhaust small bucket
        limiter.acquire("small")
        assert limiter.acquire("small", timeout=0.05) is False
        # Large bucket still has tokens
        assert limiter.acquire("large") is True

    def test_reduce_rate(self):
        configs = {"orders": RateLimitConfig(rate_per_second=10, capacity=10)}
        limiter = MultiBucketRateLimiter(configs)
        limiter.reduce_rate("orders", factor=0.5)
        limiter.acquire("orders", timeout=0.5)  # drain
        # After draining, rate should be 5/sec
        bucket = limiter.get_bucket("orders")
        assert bucket.rate == 5.0

    def test_increase_rate(self):
        configs = {"orders": RateLimitConfig(rate_per_second=10, capacity=10)}
        limiter = MultiBucketRateLimiter(configs)
        limiter.increase_rate("orders", factor=2.0)
        bucket = limiter.get_bucket("orders")
        assert bucket.rate == 20.0

    def test_reduce_rate_unknown_category(self):
        limiter = MultiBucketRateLimiter({"x": RateLimitConfig()})
        with pytest.raises(ValueError):
            limiter.reduce_rate("unknown", factor=0.5)

    def test_get_bucket(self):
        configs = {"test": RateLimitConfig(rate_per_second=5, capacity=15)}
        limiter = MultiBucketRateLimiter(configs)
        bucket = limiter.get_bucket("test")
        assert bucket is not None
        assert bucket.rate == 5.0
        assert bucket.available_tokens == 15.0

    def test_immutable_categories(self):
        """Categories list should not affect internal state."""
        configs = {"a": RateLimitConfig()}
        limiter = MultiBucketRateLimiter(configs)
        cats = limiter.categories()
        original_len = len(cats)
        cats.append("b")  # should NOT mutate internal state
        assert len(limiter.categories()) == original_len
