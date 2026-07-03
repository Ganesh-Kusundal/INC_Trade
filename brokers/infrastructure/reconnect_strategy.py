"""Unified reconnect strategy — single exponential-backoff implementation.

Replaces 3 parallel reconnect loops across:
- websocket_pool.py
- websocket_runner.py
- base_streaming.py
"""

from __future__ import annotations

import logging
import time
from typing import Callable

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
    ) -> None:
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._max_retries = max_retries
        self._retry_logger = retry_logger or logger.warning
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

    def wait(self) -> None:
        """Sleep for the current backoff delay.

        After sleeping, increments the attempt counter and doubles the delay
        (capped at *max_delay*).
        """
        time.sleep(self._current_delay)
        self._attempt += 1
        self._current_delay = min(self._current_delay * 2, self._max_delay)

    def reset(self) -> None:
        """Reset backoff after a successful connection."""
        self._attempt = 0
        self._current_delay = self._base_delay

    @property
    def attempt(self) -> int:
        return self._attempt

    @property
    def current_delay(self) -> float:
        return self._current_delay
