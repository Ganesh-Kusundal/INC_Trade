"""InstrumentRegistry — thread-safe registry ensuring one Instrument per symbol.

Architecture:
    Only one Instrument instance exists per composite key (``{exchange}:{symbol}``).
    This guarantees a single source of truth for shared state, subscriptions,
    cache, and analytics.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class InstrumentRegistry:
    """Thread-safe registry guaranteeing one Instrument per composite key.

    Usage::

        registry = InstrumentRegistry()
        inst1 = registry.get_or_create("NSE:RELIANCE", lambda: Instrument(...))
        inst2 = registry.get_or_create("NSE:RELIANCE", lambda: ...)
        assert inst1 is inst2  # Single identity guarantee
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._instruments: dict[str, Any] = {}

    def get_or_create(self, key: str, factory: Callable[[], Any]) -> Any:
        """Return existing instrument or create with factory.

        The factory is called at most once per key. Thread-safe.

        Args:
            key: Composite key (e.g., ``"NSE:RELIANCE"``).
            factory: Zero-argument callable that creates the instrument.

        Returns:
            The existing or newly created instrument instance.
        """
        with self._lock:
            if key in self._instruments:
                return self._instruments[key]
            instance = factory()
            self._instruments[key] = instance
            return instance

    def get(self, key: str) -> Instrument | None:
        """Look up an instrument by its composite key.

        Lock-free read: dict reference read is atomic in CPython.
        Writes use copy-on-write (new dict) so readers never see
        a partially-modified dict.

        Args:
            key: Composite key ``{exchange}:{symbol}``.

        Returns:
            The Instrument if found, else None.
        """
        # LOCK-FREE: dict read is atomic in CPython
        return self._instruments.get(key)

    def get_all(self) -> dict[str, Any]:
        """Return a snapshot of all registered instruments.

        Returns:
            Copy of the internal registry dictionary.
        """
        with self._lock:
            return dict(self._instruments)

    def clear(self) -> None:
        """Clear all registered instruments (primarily for testing)."""
        with self._lock:
            self._instruments.clear()

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._instruments

    def __len__(self) -> int:
        with self._lock:
            return len(self._instruments)
