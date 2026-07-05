"""Backoff policy abstractions for reconnect and retry strategies."""

from __future__ import annotations

import math
import random
from typing import Protocol, runtime_checkable


@runtime_checkable
class BackoffPolicy(Protocol):
    """Protocol for computing inter-attempt delay durations.

    Implementors must provide ``next_delay`` (given an attempt number, returns
    a float number of seconds to wait) and ``reset`` (clears internal state
    after a successful connection).
    """

    def next_delay(self, attempt: int) -> float:
        """Return the delay in seconds for the given attempt number.

        Args:
            attempt: Zero-based attempt counter (0 = first retry).

        Returns:
            Number of seconds to sleep before the next attempt.
        """
        ...

    def reset(self) -> None:
        """Reset any internal state accumulated across attempts."""
        ...


class ExponentialBackoff:
    """Exponential backoff without jitter.

    Delay after attempt *n* is ``min(base * 2^n, max_delay)``.

    Args:
        base: Initial delay in seconds (default 5.0).
        max_delay: Upper bound on delay in seconds (default 60.0).
    """

    def __init__(self, base: float = 5.0, max_delay: float = 60.0) -> None:
        self._base = base
        self._max_delay = max_delay

    def next_delay(self, attempt: int) -> float:
        """Return exponentially increasing delay, capped at *max_delay*."""
        return min(self._base * math.pow(2, attempt), self._max_delay)

    def reset(self) -> None:
        """No-op — ExponentialBackoff is stateless."""


class JitteredExponentialBackoff:
    """Exponential backoff with uniform random jitter to prevent thundering herd.

    Computes a base exponential delay then applies ± *jitter_ratio* fraction of
    that value as uniform random noise::

        jitter_amount = base_delay * jitter_ratio
        delay = uniform(base_delay - jitter_amount, base_delay + jitter_amount)

    Args:
        base: Initial delay in seconds (default 5.0).
        max_delay: Upper bound on delay in seconds before jitter (default 60.0).
        jitter_ratio: Fraction of base delay to use as jitter window (default 0.25).
    """

    def __init__(
        self,
        base: float = 5.0,
        max_delay: float = 60.0,
        jitter_ratio: float = 0.25,
    ) -> None:
        self._base = base
        self._max_delay = max_delay
        self._jitter_ratio = jitter_ratio

    def next_delay(self, attempt: int) -> float:
        """Return jittered exponential delay, capped at *max_delay* + jitter."""
        base_delay = min(self._base * math.pow(2, attempt), self._max_delay)
        jitter_amount = base_delay * self._jitter_ratio
        return random.uniform(base_delay - jitter_amount, base_delay + jitter_amount)

    def reset(self) -> None:
        """No-op — JitteredExponentialBackoff is stateless."""
