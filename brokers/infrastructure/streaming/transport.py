"""Async transport protocol — abstraction over WebSocket connections.

The ``AsyncTransport`` protocol defines the interface that the
``StreamOrchestrator`` uses to communicate with a WebSocket connection.
Broker-specific implementations (Dhan JSON, Upstox protobuf) implement
this protocol, keeping the orchestrator broker-agnostic.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AsyncTransport(Protocol):
    """Async WebSocket transport interface.

    Implementations must handle connection lifecycle, sending messages,
    and yielding received messages as an async iterator.
    """

    @property
    def is_connected(self) -> bool:
        """True if the underlying connection is open."""
        ...

    async def connect(self, url: str, *, extra_headers: dict[str, str] | None = None) -> None:
        """Open a WebSocket connection to the given URL."""
        ...

    async def send(self, data: str | bytes) -> None:
        """Send a message over the connection."""
        ...

    async def recv(self) -> str | bytes:
        """Receive a single message. Raises ConnectionClosed on disconnect."""
        ...

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the connection gracefully."""
        ...


class ConnectionClosed(Exception):
    """Raised when a WebSocket connection is closed unexpectedly."""
