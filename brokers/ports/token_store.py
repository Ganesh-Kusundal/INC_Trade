"""Token store port — abstraction for persisting auth token state.

Adapters implementing this port can store tokens in JSON files,
databases, or secrets managers. The port defines the minimum
interface needed by authentication flows.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TokenStorePort(Protocol):
    """Interface for persisting and retrieving auth token state."""

    def save(self, state: dict[str, Any]) -> None:
        """Persist token state.

        Args:
            state: Dictionary of token state data to persist.
        """
        ...

    def load(self) -> dict[str, Any] | None:
        """Load previously persisted token state.

        Returns:
            Token state dict, or None if no state exists.
        """
        ...
