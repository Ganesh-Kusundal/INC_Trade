"""Unit tests for the unified ``run_reconnect_loop`` helper.

These tests exercise the consolidation of the three near-identical reconnect
loops that previously lived in ``websocket_pool.py``, ``websocket_runner.py``,
and ``base_streaming.py``. See ``brokers/infrastructure/reconnect_strategy.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from brokers.infrastructure.reconnect_strategy import ReconnectStrategy, run_reconnect_loop


def _make_strategy(max_retries: int = 0) -> ReconnectStrategy:
    """Create a strategy that does not actually sleep during tests."""
    return ReconnectStrategy(
        base_delay=0.0,
        max_delay=0.0,
        max_retries=max_retries,
    )


class TestRunReconnectLoopHappyPath:
    """The clean case: a single successful connect, then stop."""

    def test_invokes_connect_once_and_returns_when_not_running(self):
        strategy = _make_strategy()
        connect = MagicMock()
        is_running = MagicMock(side_effect=[True, False])

        run_reconnect_loop(strategy=strategy, is_running=is_running, connect=connect)

        connect.assert_called_once()

    def test_resets_strategy_on_successful_connect(self):
        strategy = _make_strategy()
        # Force a non-zero attempt counter so we can prove reset() ran.
        strategy._attempt = 5  # internal state for the test

        run_reconnect_loop(
            strategy=strategy,
            is_running=MagicMock(side_effect=[True, False]),
            connect=MagicMock(),
        )

        assert strategy.attempt == 0

    def test_calls_on_connected_hook_after_success(self):
        strategy = _make_strategy()
        on_connected = MagicMock()

        run_reconnect_loop(
            strategy=strategy,
            is_running=MagicMock(side_effect=[True, False]),
            connect=MagicMock(),
            on_connected=on_connected,
        )

        on_connected.assert_called_once()

    def test_does_not_call_on_connected_when_connect_raises(self):
        strategy = _make_strategy(max_retries=0)
        on_connected = MagicMock()

        def _explode() -> None:
            raise ConnectionError("boom")

        is_running = MagicMock(side_effect=[True, False])

        run_reconnect_loop(
            strategy=strategy,
            is_running=is_running,
            connect=_explode,
            on_connected=on_connected,
        )

        on_connected.assert_not_called()


class TestRunReconnectLoopFailurePath:
    """Reconnect on exception: back off and retry until should_retry says no."""

    def test_retries_then_gives_up_when_max_retries_exceeded(self):
        # Bounded retry budget: 2 attempts allowed.
        strategy = ReconnectStrategy(
            base_delay=0.0,
            max_delay=0.0,
            max_retries=2,
        )
        connect = MagicMock(side_effect=ConnectionError("boom"))
        is_running = MagicMock(return_value=True)

        run_reconnect_loop(
            strategy=strategy,
            is_running=is_running,
            connect=connect,
        )

        # First call: connect fails (attempt 0 -> 1, current_delay stays 0).
        # should_retry (0 < 2) -> True, sleep, attempt=1, current_delay doubles (0.0).
        # Second call: connect fails (attempt 1 -> 2).
        # should_retry (1 < 2) -> True, sleep, attempt=2.
        # Third call: connect fails (attempt 2 -> 3).
        # should_retry (2 < 2) -> False -> return.
        assert connect.call_count == 3

    def test_backoff_doubles_between_failed_attempts(self):
        strategy = ReconnectStrategy(
            base_delay=2.0,
            max_delay=100.0,
            max_retries=3,
        )
        connect = MagicMock(side_effect=ConnectionError("boom"))
        is_running = MagicMock(return_value=True)

        with patch("brokers.infrastructure.reconnect_strategy.time.sleep") as mock_sleep:
            run_reconnect_loop(
                strategy=strategy,
                is_running=is_running,
                connect=connect,
            )

        sleep_values = [c.args[0] for c in mock_sleep.call_args_list]
        # Iteration 1 fails: current_delay=2.0, sleep(2.0), then attempt=1, current_delay=4.0.
        # Iteration 2 fails: current_delay=4.0, sleep(4.0), then attempt=2, current_delay=8.0.
        # Iteration 3 fails: current_delay=8.0, sleep(8.0), then attempt=3.
        # should_retry(3 < 3) -> False -> return.
        assert sleep_values == pytest.approx([2.0, 4.0, 8.0])

    def test_unlimited_retries_continues_until_not_running(self):
        strategy = _make_strategy(max_retries=0)  # 0 = unlimited
        call_count = {"n": 0}

        def _connect() -> None:
            call_count["n"] += 1
            raise ConnectionError("boom")

        # The helper calls is_running() up to 3 times per iteration
        # (top of while, after exception, after backoff). Use a counter so we
        # stop the loop after exactly 5 connect attempts.
        running_checks = {"n": 0}

        def is_running() -> bool:
            # Run for 5 iterations (each iteration calls 3 times = 15 checks),
            # then return False.
            running_checks["n"] += 1
            return running_checks["n"] <= 15

        run_reconnect_loop(
            strategy=strategy,
            is_running=is_running,
            connect=_connect,
        )

        assert call_count["n"] == 5

    def test_returns_early_when_not_running_during_failure(self):
        strategy = _make_strategy(max_retries=10)
        connect = MagicMock(side_effect=ConnectionError("boom"))

        # is_running returns True for the connect call only, then False.
        is_running = MagicMock(side_effect=[True, False])

        run_reconnect_loop(
            strategy=strategy,
            is_running=is_running,
            connect=connect,
        )

        # Connect was attempted once, but the loop exited before the
        # backoff wait because !is_running after the failure.
        connect.assert_called_once()


class TestRunReconnectLoopHooks:
    def test_on_reconnecting_receives_current_delay(self):
        strategy = ReconnectStrategy(
            base_delay=3.0,
            max_delay=100.0,
            max_retries=1,
        )
        connect = MagicMock(side_effect=ConnectionError("boom"))
        is_running = MagicMock(return_value=True)
        on_reconnecting = MagicMock()

        with patch("brokers.infrastructure.reconnect_strategy.time.sleep"):
            run_reconnect_loop(
                strategy=strategy,
                is_running=is_running,
                connect=connect,
                on_reconnecting=on_reconnecting,
            )

        # First attempt fails, on_reconnecting is called with 3.0, then wait (3.0).
        # Second attempt fails, should_retry (attempt=1, max=1) -> False -> return.
        on_reconnecting.assert_called_once_with(3.0)

    def test_sleep_callable_is_forwarded_to_strategy(self):
        """Custom sleep primitives are honored by run_reconnect_loop."""
        strategy = ReconnectStrategy(
            base_delay=0.0,
            max_delay=0.0,
            max_retries=1,
        )
        connect = MagicMock(side_effect=ConnectionError("boom"))
        is_running = MagicMock(return_value=True)
        sleep = MagicMock()

        run_reconnect_loop(
            strategy=strategy,
            is_running=is_running,
            connect=connect,
            sleep=sleep,
        )

        # First failure -> sleep called with base_delay (0.0). After waiting, attempt=1
        # which equals max_retries=1, so should_retry returns False and the loop exits.
        sleep.assert_called_once_with(0.0)

    def test_hook_exceptions_do_not_break_loop(self):
        """Hook exceptions are logged and swallowed; the loop continues."""
        strategy = ReconnectStrategy(
            base_delay=0.0,
            max_delay=0.0,
            max_retries=1,
        )
        connect = MagicMock(side_effect=ConnectionError("boom"))
        is_running_checks = {"n": 0}

        def is_running() -> bool:
            is_running_checks["n"] += 1
            return is_running_checks["n"] <= 3  # 1 iteration only

        def _boom(_delay: float) -> None:
            raise RuntimeError("hook failure")

        # Should not raise despite on_reconnecting raising.
        with patch("brokers.infrastructure.reconnect_strategy.time.sleep"):
            run_reconnect_loop(
                strategy=strategy,
                is_running=is_running,
                connect=connect,
                on_reconnecting=_boom,
            )

        assert connect.call_count == 1

    def test_on_connected_hook_exception_is_swallowed(self):
        strategy = _make_strategy()
        on_connected = MagicMock(side_effect=RuntimeError("hook fail"))

        # Should not raise despite on_connected raising.
        run_reconnect_loop(
            strategy=strategy,
            is_running=MagicMock(side_effect=[True, False]),
            connect=MagicMock(),
            on_connected=on_connected,
        )

        on_connected.assert_called_once()


class TestRunReconnectLoopWaitOnSuccess:
    """The ``wait_on_success`` flag preserves the legacy WebSocketConnection semantics."""

    def test_default_skips_backoff_on_clean_disconnect(self):
        """With wait_on_success=False, a clean connect does not sleep before retrying."""
        strategy = ReconnectStrategy(
            base_delay=10.0,
            max_delay=10.0,
            max_retries=2,
        )
        connect = MagicMock(side_effect=[None, ConnectionError("boom")])
        # Allow up to 2 iterations (3 is_running calls each = 6 checks).
        is_running_checks = {"n": 0}

        def is_running() -> bool:
            is_running_checks["n"] += 1
            return is_running_checks["n"] <= 6

        sleep = MagicMock()

        run_reconnect_loop(
            strategy=strategy,
            is_running=is_running,
            connect=connect,
            sleep=sleep,
            wait_on_success=False,
        )

        # First call: clean success, strategy reset, no wait (wait_on_success=False).
        # Second call: exception -> sleep called with current_delay=10.0.
        sleep.assert_called_once_with(10.0)

    def test_default_waits_on_success(self):
        """With wait_on_success=True (default), a clean connect still backs off."""
        strategy = ReconnectStrategy(
            base_delay=10.0,
            max_delay=100.0,  # allow doubling
            max_retries=5,
        )
        connect = MagicMock(side_effect=[None, ConnectionError("boom")])
        # Allow up to 2 iterations (3 is_running calls each = 6 checks).
        is_running_checks = {"n": 0}

        def is_running() -> bool:
            is_running_checks["n"] += 1
            return is_running_checks["n"] <= 6

        sleep = MagicMock()

        run_reconnect_loop(
            strategy=strategy,
            is_running=is_running,
            connect=connect,
            sleep=sleep,
            wait_on_success=True,
        )

        # First call: clean success (attempt=0, delay=10.0) -> sleep(10.0).
        # Second call: exception (attempt=1, delay=20.0) -> sleep(20.0).
        sleep_values = [c.args[0] for c in sleep.call_args_list]
        assert sleep_values == pytest.approx([10.0, 20.0])


class TestReconnectStrategyWaitInjection:
    """Tests for the optional ``sleep`` argument on ReconnectStrategy.wait()."""

    def test_wait_uses_injected_sleep_callable(self):
        strategy = ReconnectStrategy(base_delay=0.0, max_delay=0.0, max_retries=5)
        sleep = MagicMock()
        strategy.wait(sleep=sleep)
        sleep.assert_called_once_with(0.0)

    def test_wait_default_resolves_to_time_sleep_at_call_time(self):
        """Patching time.sleep at the module level affects default sleep."""
        strategy = ReconnectStrategy(base_delay=0.0, max_delay=0.0, max_retries=5)
        with patch("brokers.infrastructure.reconnect_strategy.time.sleep") as mock_sleep:
            strategy.wait()
        mock_sleep.assert_called_once_with(0.0)
