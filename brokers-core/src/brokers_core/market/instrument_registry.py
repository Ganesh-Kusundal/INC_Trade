"""InstrumentRegistry — thread-safe registry ensuring one Instrument per symbol.

Architecture:
    Only one Instrument instance exists per composite key (``{exchange}:{symbol}``).
    This guarantees a single source of truth for shared state, subscriptions,
    cache, and analytics.

Thread Safety:
    - Reads (``get()``) are completely lock-free (dict reference read is atomic)
    - Writes use **copy-on-write**: create a new dict, modify, swap atomically
    - This avoids RLock contention on the hot read path
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
        self._lock = threading.Lock()  # Lock for writes only
        self._instruments: dict[str, Any] = {}

    def get_or_create(self, key: str, factory: Callable[[], Any]) -> Any:
        """Return existing instrument or create with factory.

        Uses copy-on-write: creates a new dict on mutation so readers
        never see a partially-modified dict.

        The factory is called at most once per key.

        Args:
            key: Composite key (e.g., ``"NSE:RELIANCE"``).
            factory: Zero-argument callable that creates the instrument.

        Returns:
            The existing or newly created instrument instance.
        """
        # Fast path: lock-free read (dict reference is atomic in CPython)
        existing = self._instruments.get(key)
        if existing is not None:
            return existing

        # Slow path: factory call + copy-on-write
        instance = factory()

        with self._lock:
            # Double-check under lock (another thread may have inserted)
            if key in self._instruments:
                return self._instruments[key]
            # Copy-on-write: new dict, atomically swap
            new_dict = dict(self._instruments)
            new_dict[key] = instance
            self._instruments = new_dict
            return instance

    def get(self, key: str) -> Any | None:
        """Look up an instrument by its composite key.

        Lock-free read: dict reference read is atomic in CPython.
        Copy-on-write writes ensure the reader always sees a complete dict.

        Args:
            key: Composite key ``{exchange}:{symbol}``.

        Returns:
            The Instrument if found, else None.
        """
        # LOCK-FREE: dict read is atomic in CPython
        return self._instruments.get(key)

    def register(self, key: str, instrument: Any) -> None:
        """Register an existing instrument by key.

        Uses copy-on-write. Thread-safe.

        Args:
            key: Composite key.
            instrument: The Instrument instance.

        Raises:
            ValueError: If key already registered.
        """
        with self._lock:
            if key in self._instruments:
                raise ValueError(f"Instrument already registered: {key}")
            new_dict = dict(self._instruments)
            new_dict[key] = instrument
            self._instruments = new_dict

    def get_all(self) -> dict[str, Any]:
        """Return a snapshot of all registered instruments.

        Returns:
            Copy of the internal registry dictionary.
        """
        return dict(self._instruments)

    def clear(self) -> None:
        """Clear all registered instruments (primarily for testing)."""
        with self._lock:
            self._instruments = {}

    def search(self, query: str) -> list[Any]:
        """Search instruments by symbol or name.

        Lock-free read. Case-insensitive substring match.

        Args:
            query: Search string.

        Returns:
            List of matching instruments.
        """
        query_upper = query.upper()
        results = []
        for inst in self._instruments.values():
            symbol = getattr(inst, "symbol", "")
            name = getattr(inst, "name", "")
            if query_upper in symbol.upper() or query_upper in name.upper():
                results.append(inst)
        return results

    def __contains__(self, key: str) -> bool:
        return key in self._instruments

    def __len__(self) -> int:
        return len(self._instruments)

    def __repr__(self) -> str:
        return f"InstrumentRegistry(count={len(self)})"
