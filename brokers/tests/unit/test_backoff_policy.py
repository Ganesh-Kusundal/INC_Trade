"""Unit tests for BackoffPolicy, ExponentialBackoff, JitteredExponentialBackoff, and
ReconnectStrategy policy integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from inc_trade.infrastructure.reconnect_strategy import ReconnectStrategy
from inc_trade.resilience.backoff_policy import (
    BackoffPolicy,
    ExponentialBackoff,
    JitteredExponentialBackoff,
)


class TestExponentialBackoff:
    def test_implements_protocol(self):
        eb = ExponentialBackoff()
        assert isinstance(eb, BackoffPolicy)

    def test_first_attempt_equals_base(self):
        eb = ExponentialBackoff(base=5.0)
        assert eb.next_delay(0) == pytest.approx(5.0)

    def test_doubles_each_attempt(self):
        eb = ExponentialBackoff(base=5.0, max_delay=1000.0)
        delays = [eb.next_delay(i) for i in range(4)]
        assert delays == pytest.approx([5.0, 10.0, 20.0, 40.0])

    def test_capped_at_max_delay(self):
        eb = ExponentialBackoff(base=5.0, max_delay=15.0)
        # attempt=2 → 5*4=20 → capped to 15
        assert eb.next_delay(2) == pytest.approx(15.0)
        assert eb.next_delay(10) == pytest.approx(15.0)

    def test_reset_is_noop(self):
        eb = ExponentialBackoff()
        eb.reset()  # should not raise


class TestJitteredExponentialBackoff:
    def test_implements_protocol(self):
        jeb = JitteredExponentialBackoff()
        assert isinstance(jeb, BackoffPolicy)

    def test_delay_within_jitter_range(self):
        jeb = JitteredExponentialBackoff(base=10.0, max_delay=1000.0, jitter_ratio=0.25)
        # attempt 0 → base_delay=10, jitter=2.5, range [7.5, 12.5]
        for _ in range(50):
            d = jeb.next_delay(0)
            assert 7.5 <= d <= 12.5, f"delay {d} out of expected range [7.5, 12.5]"

    def test_delay_respects_max_delay_cap_before_jitter(self):
        jeb = JitteredExponentialBackoff(base=5.0, max_delay=10.0, jitter_ratio=0.25)
        # attempt 3 → 5*8=40, capped to 10; jitter=[7.5, 12.5]
        for _ in range(20):
            d = jeb.next_delay(3)
            assert 7.5 <= d <= 12.5

    def test_produces_variation(self):
        """Jitter should produce different values across multiple calls."""
        jeb = JitteredExponentialBackoff(base=10.0, max_delay=1000.0, jitter_ratio=0.5)
        delays = {jeb.next_delay(0) for _ in range(30)}
        # With 50% jitter window [5, 15], very unlikely to get all identical values
        assert len(delays) > 1

    def test_reset_is_noop(self):
        jeb = JitteredExponentialBackoff()
        jeb.reset()  # should not raise


class TestReconnectStrategyWithPolicy:
    def test_uses_policy_when_provided(self):
        policy = MagicMock(spec=BackoffPolicy)
        policy.next_delay.return_value = 3.7

        strategy = ReconnectStrategy(max_retries=5, policy=policy)

        with patch("inc_trade.infrastructure.reconnect_strategy.time.sleep") as mock_sleep:
            strategy.wait()

        policy.next_delay.assert_called_once_with(0)
        mock_sleep.assert_called_once_with(3.7)

    def test_policy_receives_incrementing_attempt_number(self):
        policy = MagicMock(spec=BackoffPolicy)
        policy.next_delay.return_value = 1.0

        strategy = ReconnectStrategy(max_retries=5, policy=policy)

        with patch("inc_trade.infrastructure.reconnect_strategy.time.sleep"):
            strategy.wait()
            strategy.wait()
            strategy.wait()

        calls = [c.args[0] for c in policy.next_delay.call_args_list]
        assert calls == [0, 1, 2]

    def test_policy_reset_called_on_strategy_reset(self):
        policy = MagicMock(spec=BackoffPolicy)
        policy.next_delay.return_value = 1.0

        strategy = ReconnectStrategy(policy=policy)
        strategy.reset()

        policy.reset.assert_called_once()

    def test_no_policy_uses_doubling_logic(self):
        """Without policy the legacy exponential doubling behaviour is preserved."""
        strategy = ReconnectStrategy(base_delay=5.0, max_delay=60.0, max_retries=5)

        with patch("inc_trade.infrastructure.reconnect_strategy.time.sleep") as mock_sleep:
            strategy.wait()
            strategy.wait()
            strategy.wait()

        sleep_values = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_values == pytest.approx([5.0, 10.0, 20.0])

    def test_policy_does_not_update_current_delay(self):
        """When policy is active, current_delay should stay at the initial base."""
        policy = MagicMock(spec=BackoffPolicy)
        policy.next_delay.return_value = 99.0

        strategy = ReconnectStrategy(base_delay=5.0, policy=policy)

        with patch("inc_trade.infrastructure.reconnect_strategy.time.sleep"):
            strategy.wait()

        # current_delay should remain 5.0 (no doubling when policy is set)
        assert strategy.current_delay == pytest.approx(5.0)

    def test_reset_clears_attempt_counter(self):
        policy = MagicMock(spec=BackoffPolicy)
        policy.next_delay.return_value = 1.0

        strategy = ReconnectStrategy(policy=policy)

        with patch("inc_trade.infrastructure.reconnect_strategy.time.sleep"):
            strategy.wait()
            strategy.wait()

        assert strategy.attempt == 2
        strategy.reset()
        assert strategy.attempt == 0
