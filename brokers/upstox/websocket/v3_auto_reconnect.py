"""Upstox V3 WebSocket auto-reconnect (exponential backoff + jitter).

Mirrors Trade_J ``UpstoxResubscribeUnitTest`` / reconnect logic.
"""

from __future__ import annotations

import random


class UpstoxAutoReconnect:
    def __init__(
        self,
        enabled: bool = True,
        interval_seconds: float = 10.0,
        max_retries: int = 5,
        jitter: float = 0.2,
    ) -> None:
        self._enabled = enabled
        self._interval = float(interval_seconds)
        self._max_retries = int(max_retries)
        self._jitter = float(jitter)
        self._attempts = 0

    def should_retry(self, attempt: int | None = None) -> bool:
        if not self._enabled:
            return False
        n = self._attempts if attempt is None else int(attempt)
        return n < self._max_retries

    def next_delay(self, attempt: int | None = None) -> float:
        n = self._attempts if attempt is None else int(attempt)
        # exponential with jitter: base * 2^n +/- jitter
        base = self._interval * (2**n)
        return base * (1.0 + random.uniform(-self._jitter, self._jitter))

    def reset(self) -> None:
        self._attempts = 0

    def record_failure(self) -> None:
        self._attempts += 1
