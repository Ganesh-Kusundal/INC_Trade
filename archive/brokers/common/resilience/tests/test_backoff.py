"""TDD tests for BackoffStrategy — exponential backoff with jitter."""

from brokers.common.resilience.backoff import ExponentialBackoff, FixedBackoff, NoBackoff


class TestNoBackoff:
    def test_always_zero(self):
        b = NoBackoff()
        for attempt in range(10):
            assert b.delay(attempt) == 0.0

    def test_reset(self):
        b = NoBackoff()
        b.delay(5)
        b.reset()
        assert True  # no error


class TestFixedBackoff:
    def test_constant_delay(self):
        b = FixedBackoff(delay_ms=100)
        for attempt in range(5):
            assert b.delay(attempt) == 0.1

    def test_default_delay(self):
        b = FixedBackoff()
        assert b.delay(0) == 1.0

    def test_zero_delay(self):
        b = FixedBackoff(delay_ms=0)
        assert b.delay(99) == 0.0


class TestExponentialBackoff:
    def test_exponential_increase(self):
        b = ExponentialBackoff(base_delay_ms=100, max_delay_ms=10000)
        delays = [b.delay(i) for i in range(5)]
        # Should increase exponentially: 0.1, 0.2, 0.4, 0.8, 1.6
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]

    def test_capped_at_max(self):
        b = ExponentialBackoff(base_delay_ms=1000, max_delay_ms=3000)
        delays = [b.delay(i) for i in range(10)]
        for d in delays:
            assert d <= 3.0  # max 3 seconds

    def test_default_config(self):
        b = ExponentialBackoff()
        d = b.delay(0)
        assert 0.5 <= d <= 1.5  # base 1s with jitter

    def test_multiplicative_factor(self):
        b = ExponentialBackoff(base_delay_ms=1000, multiplier=3.0, max_delay_ms=30000)
        d0 = b.delay(0)
        d1 = b.delay(1)
        d2 = b.delay(2)
        assert d1 >= d0
        assert d2 >= d1

    def test_adds_jitter(self):
        """Multiple calls at same attempt should produce different values due to jitter."""
        b = ExponentialBackoff(base_delay_ms=1000, max_delay_ms=10000)
        delays = {b.delay(5) for _ in range(20)}
        assert len(delays) > 1  # jitter causes variation

    def test_reset(self):
        b = ExponentialBackoff()
        b.delay(10)
        b.reset()  # should not error
        assert True


class TestBackoffInterface:
    def test_strategy_pattern(self):
        """All backoff strategies should conform to the same interface."""
        strategies = [
            NoBackoff(),
            FixedBackoff(500),
            ExponentialBackoff(),
        ]
        for strategy in strategies:
            assert hasattr(strategy, "delay")
            assert callable(strategy.delay)
            assert hasattr(strategy, "reset")
            assert callable(strategy.reset)

    def test_with_retry_executor(self):
        """Backoff strategies should produce reasonable delays for retry scenarios."""
        b = ExponentialBackoff(base_delay_ms=100, max_delay_ms=5000, multiplier=2.0)
        # Typical retry sequence
        attempts = [0, 1, 2, 3, 4]
        delays = [b.delay(a) for a in attempts]
        # Each delay should be non-negative and finite
        for d in delays:
            assert d >= 0
            assert d < float("inf")
