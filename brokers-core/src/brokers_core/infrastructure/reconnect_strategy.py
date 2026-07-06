"""Unified reconnect strategy — single exponential-backoff implementation.

Replaces 3 parallel reconnect loops across:
- websocket_pool.py
- websocket_runner.py
- base_streaming.py
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brokers_core.resilience.backoff_policy import BackoffPolicy

logger = logging.getLogger(__name__)


class ReconnectStrategy:
    """Exponential backoff reconnect strategy.

    Typical usage::

        strategy = ReconnectStrategy(base_delay=5.0, max_delay=60.0, max_retries=10)
        while condition:
            if strategy.should_retry():
                strategy.wait()
                try:
                    connect()
                    strategy.reset()
                except ConnectionError:
                    continue
            else:
                break
    """

    def __init__(
        self,
        base_delay: float = 5.0,
        max_delay: float = 60.0,
        max_retries: int = 10,
        retry_logger: Callable[[str], None] | None = None,
        policy: BackoffPolicy | None = None,
    ) -> None:
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._max_retries = max_retries
        self._retry_logger = retry_logger or logger.warning
        self._policy = policy
        self._attempt = 0
        self._current_delay = base_delay

    def should_retry(self) -> bool:
        """Check if another reconnect attempt should be made.

        Returns True when *max_retries* is 0 (unlimited retries) or when
        the number of attempts is still below the limit.
        """
        if self._max_retries == 0:
            return True  # unlimited retries
        return self._attempt < self._max_retries

    def wait(self, sleep: Callable[[float], None] | None = None) -> None:
        """Sleep for the current backoff delay.

        If a BackoffPolicy is set, delegates delay calculation to the policy.
        Otherwise uses built-in exponential doubling (capped at max_delay).

        Args:
            sleep: Optional callable to use instead of ``time.sleep``.
        """
        if self._policy is not None:
            delay = self._policy.next_delay(self._attempt)
        else:
            delay = self._current_delay
            self._current_delay = min(self._current_delay * 2, self._max_delay)
        (sleep or time.sleep)(delay)
        self._attempt += 1

    def reset(self) -> None:
        """Reset backoff after a successful connection."""
        self._attempt = 0
        self._current_delay = self._base_delay
        if self._policy is not None:
            self._policy.reset()

    @property
    def attempt(self) -> int:
        return self._attempt

    @property
    def current_delay(self) -> float:
        return self._current_delay


def run_reconnect_loop(
    connect: Callable[[], None],
    *,
    strategy: ReconnectStrategy | None = None,
    is_running: Callable[[], bool] | None = None,
    on_connected: Callable[[], None] | None = None,
    on_reconnecting: Callable[[float], None] | None = None,
    sleep: Callable[[float], None] | None = None,
    wait_on_success: bool = True,
    label: str = "connection",
    base_delay: float = 5.0,
    max_delay: float = 60.0,
    max_retries: int = 10,
    policy: BackoffPolicy | None = None,
) -> None:
    """Run a reconnect loop using ``ReconnectStrategy``.

    Args:
        connect: Callable that (re)establishes the connection.
        strategy: Pre-configured ``ReconnectStrategy``. If omitted, one is
            created from *base_delay*, *max_delay*, *max_retries*, *policy*.
        is_running: Optional callable returning ``True`` while the outer
            connection loop should keep running. When provided, the loop
            checks this at each stage instead of returning after a single
            successful connect (new-style). When omitted, the function
            preserves the original behaviour (return on success, retry on
            failure until ``max_retries`` exhausted).
        on_connected: Hook called after a successful connect. Exceptions
            are logged and swallowed.
        on_reconnecting: Hook called with the current delay before a
            reconnect wait. Exceptions are logged and swallowed.
        sleep: Optional callable to use instead of ``time.sleep`` for
            backoff waits.
        wait_on_success: When ``True`` (default), the loop sleeps for the
            current backoff delay even after a clean connect (legacy
            WebSocketConnection semantics).
        label: Human-readable label for log messages.
        base_delay: Initial backoff delay in seconds (ignored when
            *strategy* is provided).
        max_delay: Maximum backoff delay in seconds (ignored when
            *strategy* is provided).
        max_retries: Maximum number of reconnect attempts, 0 = unlimited
            (ignored when *strategy* is provided).
        policy: Optional ``BackoffPolicy`` for custom delay calculation
            (ignored when *strategy* is provided).

    This is a shared helper that replaces 3 parallel reconnect loops
    across ``websocket_pool.py``, ``websocket_runner.py``, and
    ``base_streaming.py``.
    """
    if strategy is None:
        strategy = ReconnectStrategy(
            base_delay=base_delay,
            max_delay=max_delay,
            max_retries=max_retries,
            policy=policy,
        )

    _is_running = is_running
    _sleep = sleep or time.sleep

    # --- Old-style callers (no is_running) ---
    # Preserve the original behaviour: return on first success, retry on
    # failure until max_retries is exhausted, then log "giving up".
    if _is_running is None:
        while strategy.should_retry():
            try:
                connect()
                strategy.reset()
                if on_connected is not None:
                    try:
                        on_connected()
                    except Exception:
                        logger.exception("on_connected hook failed")
                logger.info(
                    "reconnect_loop_connected",
                    extra={"backend_name": label},
                )
                return
            except Exception:
                logger.exception(
                    "reconnect_loop_attempt_failed",
                    extra={"backend_name": label, "attempt": strategy.attempt + 1},
                )
                if on_reconnecting is not None:
                    try:
                        on_reconnecting(strategy.current_delay)
                    except Exception:
                        logger.exception("on_reconnecting hook failed")
                strategy.wait(sleep=_sleep)
        logger.error(
            "reconnect_loop_giving_up",
            extra={"backend_name": label, "attempts": strategy.attempt},
        )
        return

    # --- New-style callers (with is_running) ---
    # Loop runs until is_running returns False or should_retry says stop.
    # `should_retry` is checked *after* a failure (before the backoff wait)
    # so that ``max_retries=N`` allows N+1 connect attempts (matching the
    # original semantics of the unified reconnect loop).
    #
    # Each failure iteration: top-check (A), post-exception check (B),
    # post-wait check (C) = 3 is_running calls.
    # Each success iteration: top-check (A), post-success check (B) = 2 calls.
    while True:
        if not _is_running():  # (A) top-of-loop check
            break

        try:
            connect()
            strategy.reset()
            if on_connected is not None:
                try:
                    on_connected()
                except Exception:
                    logger.exception("on_connected hook failed")

            if not _is_running():  # (B) post-success check
                break

            if wait_on_success:
                strategy.wait(sleep=_sleep)
            continue
        except Exception:
            logger.exception(
                "reconnect_loop_attempt_failed",
                extra={"backend_name": label, "attempt": strategy.attempt + 1},
            )

        if not strategy.should_retry():
            break

        if on_reconnecting is not None:
            try:
                on_reconnecting(strategy.current_delay)
            except Exception:
                logger.exception("on_reconnecting hook failed")

        if not _is_running():  # (B) post-failure check
            break

        strategy.wait(sleep=_sleep)

        if not _is_running():  # (C) post-wait check
            break

    logger.error(
        "reconnect_loop_giving_up",
        extra={"backend_name": label, "attempts": strategy.attempt},
    )
