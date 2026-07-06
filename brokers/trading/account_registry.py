"""AccountRegistry — thread-safe registry ensuring one Account per account_id.

Architecture:
    Only one Account instance exists per ``account_id``. This guarantees
    a single source of truth for account state, orders, and portfolio.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class AccountRegistry:
    """Thread-safe registry guaranteeing one Account per account_id.

    Usage::

        registry = AccountRegistry()
        acct1 = registry.get_or_create("dhan/default", lambda: Account(...))
        acct2 = registry.get_or_create("dhan/default", lambda: ...)
        assert acct1 is acct2  # Single identity guarantee
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._accounts: dict[str, Any] = {}

    def get_or_create(self, key: str, factory: Callable[[], Any]) -> Any:
        """Return existing account or create with factory.

        The factory is called at most once per key. Thread-safe.

        Args:
            key: Account identifier (e.g., ``"dhan/default"``).
            factory: Zero-argument callable that creates the account.

        Returns:
            The existing or newly created account instance.
        """
        with self._lock:
            if key in self._accounts:
                return self._accounts[key]
            instance = factory()
            self._accounts[key] = instance
            return instance

    def get(self, key: str) -> Any | None:
        """Look up an account by identifier.

        Args:
            key: Account identifier.

        Returns:
            The account instance, or None if not registered.
        """
        with self._lock:
            return self._accounts.get(key)

    def get_all(self) -> dict[str, Any]:
        """Return a snapshot of all registered accounts.

        Returns:
            Copy of the internal registry dictionary.
        """
        with self._lock:
            return dict(self._accounts)

    def clear(self) -> None:
        """Clear all registered accounts (primarily for testing)."""
        with self._lock:
            self._accounts.clear()

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._accounts

    def __len__(self) -> int:
        with self._lock:
            return len(self._accounts)
