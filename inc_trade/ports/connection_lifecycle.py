"""Connection lifecycle port — abstract lifecycle for streaming connections."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ConnectionLifecyclePort(Protocol):
    """Protocol for managing a streaming connection's lifecycle.

    Replaces hasattr-based lifecycle detection (``hasattr(gw, 'start')``)
    with an explicit typed protocol.
    """

    def start(self) -> None:
        """Start the connection."""
        ...

    def stop(self) -> None:
        """Stop the connection."""
        ...

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        ...
