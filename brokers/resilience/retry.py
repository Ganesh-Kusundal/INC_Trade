"""Retry policy — exponential backoff with jitter.

Retries failed operations with configurable delay and exception filtering.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RetryPolicy:
    def __init__(
        self,
        max_retries: int = 3,
        base_delay_ms: int = 500,
        max_delay_ms: int = 5000,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        if max_retries < 0:
            raise ValueError(f"max_retries must be non-negative, got {max_retries}")
        self._max_retries = max_retries
        self._base_delay_ms = base_delay_ms
        self._max_delay_ms = max_delay_ms
        self._retryable = retryable_exceptions

    def call(self, fn: Callable[[], T]) -> T:
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return fn()
            except self._retryable as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    retry_after = getattr(exc, "retry_after", None)
                    if retry_after is not None:
                        time.sleep(float(retry_after))
                    else:
                        delay = self._compute_delay(attempt)
                        time.sleep(delay / 1000.0)

        assert last_exc is not None
        raise last_exc

    def _compute_delay(self, attempt: int) -> int:
        delay: int = self._base_delay_ms * (2**attempt)
        delay = min(delay, self._max_delay_ms)
        jitter: int = random.randint(0, delay // 4)
        result: int = delay + jitter
        return result
