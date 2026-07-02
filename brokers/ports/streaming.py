"""Streaming data port."""

from __future__ import annotations

import abc
from typing import Any, Callable

from brokers.domain.entities import Quote


class StreamingPort(abc.ABC):
    """Abstract port for real-time WebSocket streaming."""

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish the WebSocket connection."""
        ...

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        ...

    @abc.abstractmethod
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

    @abc.abstractmethod
    async def unsubscribe_quotes(
        self,
        symbols: list[str],
        exchange: str,
    ) -> None:
        """Unsubscribe from real-time market quotes."""
        ...
