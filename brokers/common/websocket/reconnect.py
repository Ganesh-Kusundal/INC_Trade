"""ReconnectStrategy — shared exponential-backoff with jitter for WebSocket clients.

Both Dhan (``ReconnectingServiceMixin``) and Upstox (``UpstoxAutoReconnect``)
implemented their own reconnect arithmetic.  This class provides a single
canonical implementation that all broker WS services should use.

Usage
-----
    strategy = ReconnectStrategy(initial_delay=1.0, max_delay=30.0, jitter=0.2)
    while not stopped:
        try:
            await run()
            strategy.reset()
        except Exception:
            delay = strategy.next_delay()
            await asyncio.sleep(delay)
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable


class ReconnectStrategy:
    """Exponential-backoff reconnect strategy with optional jitter.

    Thread-safe: ``next_delay()``, ``reset()``, and ``record_failure()``
    are guarded by a reentrant lock.
    """

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: float = 0.2,
        max_retries: int = 0,
        backoff_multiplier: float = 2.0,
        on_retry_exhausted: Callable[[], None] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        initial_delay : float
            Base delay in seconds before the first retry.
        max_delay : float
            Cap for the exponential backoff.
        jitter : float
            Fraction of jitter applied as ``delay * (1 ± uniform(0, jitter))``.
        max_retries : int
            Maximum number of retry attempts (0 = unlimited).
        backoff_multiplier : float
            Factor applied to delay after each failure (default 2.0).
        on_retry_exhausted : callable, optional
            Invoked when ``max_retries`` is reached (if set).
        """
        self._initial_delay = float(initial_delay)
        self._max_delay = float(max_delay)
        self._jitter = float(jitter)
        self._max_retries = int(max_retries)
        self._multiplier = float(backoff_multiplier)
        self._on_retry_exhausted = on_retry_exhausted
        self._lock = threading.RLock()
        self._attempts = 0

    # ── Public API ─────────────────────────────────────────────────────

    def next_delay(self) -> float:
        """Return the delay in seconds before the next reconnect attempt.

        Thread-safe.  Records a failure and computes the exponential
        backoff with jitter.
        """
        with self._lock:
            self._attempts += 1
            base = self._initial_delay * (self._multiplier ** (self._attempts - 1))
            capped = min(base, self._max_delay)
            if self._jitter > 0:
                return capped * (1.0 + random.uniform(-self._jitter, self._jitter))
            return capped

    def reset(self) -> None:
        """Reset the attempt counter (call on successful connection)."""
        with self._lock:
            self._attempts = 0

    def record_failure(self) -> int:
        """Increment the attempt counter and return current count.

        Returns the number of consecutive failures so far.
        """
        with self._lock:
            self._attempts += 1
            return self._attempts

    @property
    def attempts(self) -> int:
        """Current consecutive failure count."""
        with self._lock:
            return self._attempts

    def should_retry(self) -> bool:
        """Return ``True`` if another reconnect attempt should be made.

        When ``max_retries`` is 0 (default), always returns ``True``.
        """
        if self._max_retries == 0:
            return True
        with self._lock:
            if self._attempts >= self._max_retries:
                if self._on_retry_exhausted is not None:
                    self._on_retry_exhausted()
                return False
            return True

    # ── Compatibility with Dhan's ReconnectingServiceMixin ──────────────

    @property
    def initial_backoff(self) -> float:
        """Alias for Dhan ``INITIAL_BACKOFF`` convention."""
        return self._initial_delay

    @initial_backoff.setter
    def initial_backoff(self, value: float) -> None:
        self._initial_delay = float(value)

    @property
    def max_backoff(self) -> float:
        """Alias for Dhan ``MAX_BACKOFF`` convention."""
        return self._max_delay

    @max_backoff.setter
    def max_backoff(self, value: float) -> None:
        self._max_delay = float(value)

    # ── Blocking sleep helper (for thread-based services) ───────────────

    @staticmethod
    def sleep_or_stop(delay: float, stop_event: threading.Event) -> bool:
        """Sleep for *delay* seconds, interrupted by *stop_event*.

        Returns ``True`` if the stop event was set during sleep
        (caller should exit), ``False`` if the full delay elapsed.
        """
        return stop_event.wait(timeout=delay)
