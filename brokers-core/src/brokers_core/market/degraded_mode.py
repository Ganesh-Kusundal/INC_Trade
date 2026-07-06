"""Degraded Mode — graceful degradation when a broker is unhealthy.

When a provider fails, the ``DegradedMode`` records the failure and
serves stale cached data instead of erroring. Once the provider
recovers, it returns to normal mode.

This module knows nothing about HTTP, brokers, or trading. It is
pure infrastructure support.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class DegradedMode:
    """Tracks degraded state per key and auto-recovers.

    Args:
        max_degraded_duration_s: After this many seconds, exit degraded
            mode even if no recovery signal is received. Default 300s.
    """

    def __init__(self, max_degraded_duration_s: float = 300.0) -> None:
        self._lock = threading.RLock()
        self._degraded: dict[str, datetime] = {}
        self._max_duration = max_degraded_duration_s

    def is_degraded(self, key: str) -> bool:
        """Check if a key is currently in degraded mode.

        Args:
            key: Identifier (e.g., ``NSE:RELIANCE``).

        Returns:
            True if degraded (and not yet auto-recovered).
        """
        with self._lock:
            entry = self._degraded.get(key)
            if entry is None:
                return False
            age = (datetime.now(UTC) - entry).total_seconds()
            if age > self._max_duration:
                # Auto-recover
                del self._degraded[key]
                logger.info("DegradedMode: auto-recovered %s after %.1fs", key, age)
                return False
            return True

    def enter_degraded(self, key: str) -> None:
        """Mark a key as degraded.

        Args:
            key: Identifier.
        """
        with self._lock:
            if key not in self._degraded:
                logger.warning("DegradedMode: entering degraded mode for %s", key)
            self._degraded[key] = datetime.now(UTC)

    def recover(self, key: str) -> None:
        """Mark a key as recovered.

        Args:
            key: Identifier.
        """
        with self._lock:
            if key in self._degraded:
                logger.info("DegradedMode: recovered %s", key)
                del self._degraded[key]

    def degraded_keys(self) -> list[str]:
        """Snapshot of currently-degraded keys."""
        with self._lock:
            return [
                k
                for k, v in self._degraded.items()
                if (datetime.now(UTC) - v).total_seconds() <= self._max_duration
            ]

    def clear(self) -> None:
        """Clear all degraded state (for testing)."""
        with self._lock:
            self._degraded.clear()


class DegradedGuard:
    """Wrap a callable so failures mark the key as degraded.

    Usage::

        guard = DegradedGuard(degraded, "NSE:RELIANCE")
        result = guard.call(lambda: provider.quote("RELIANCE", "NSE"), fallback=lambda: stale_quote)
    """

    def __init__(self, degraded: DegradedMode, key: str) -> None:
        self._degraded = degraded
        self._key = key

    @property
    def key(self) -> str:
        return self._key

    def call(self, primary: Any, fallback: Any = None) -> Any:
        """Try primary, fall back to fallback on failure.

        Args:
            primary: Zero-argument callable that returns the result.
            fallback: Optional zero-argument callable for fallback.

        Returns:
            Result of primary or fallback.

        Raises:
            Exception: If both primary and fallback fail.
        """
        try:
            result = primary()
            self._degraded.recover(self._key)
            return result
        except Exception as exc:
            self._degraded.enter_degraded(self._key)
            logger.debug(
                "DegradedGuard[%s]: primary failed (%s), serving fallback",
                self._key,
                exc,
            )
            if fallback is None:
                raise
            try:
                return fallback()
            except Exception:
                raise
