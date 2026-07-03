"""Streaming data port."""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from brokers.domain.entities import MarketDepth, Quote


@runtime_checkable
class StreamingPort(Protocol):
    """Protocol for real-time WebSocket streaming.

    Provides both market data streaming and order/portfolio streaming.
    All implementations must map broker-native ticks to canonical domain models.
    """

    async def connect(self) -> None:
        """Establish the WebSocket connection."""
        ...

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        ...

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        ...

    async def subscribe_quotes(
        self,
        symbols: list[str],
        exchange: str,
        callback: Callable[[Quote], Any],
    ) -> None:
        """Subscribe to real-time market quotes.

        Parameters
        ----------
        symbols : list[str]
            List of instrument symbols.
        exchange : str
            Exchange identifier.
        callback : Callable[[Quote], Any]
            Callback function invoked on new quote.
        """
        ...

    async def unsubscribe_quotes(
        self,
        symbols: list[str],
        exchange: str,
    ) -> None:
        """Unsubscribe from real-time market quotes."""
        ...
