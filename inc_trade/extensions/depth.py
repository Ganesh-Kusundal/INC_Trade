"""Depth Extension — broker-agnostic market depth capability.

Architecture:
    ``DepthExtension`` is a shared protocol that any broker implementing
    extended depth can satisfy.

    - Dhan implements with 20-level and 200-level depth.
    - Upstox implements with 5-level and 30-level depth.
    - ``Instrument.depth()`` discovers and delegates to this extension.
    - The Instrument never knows broker-specific implementations.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from inc_trade.domain.entities import MarketDepth


@runtime_checkable
class DepthExtension(Protocol):
    """Extended market depth beyond the standard 5-level depth.

    Usage::

        ext = instrument._extension(DepthExtension)
        if ext is not None:
            depth = ext.get_depth(symbol, exchange, mode="depth_20")
    """

    @property
    def supported_depth_modes(self) -> frozenset[str]:
        """Depth modes this extension supports (e.g. ``{"depth_20", "depth_200"}``)."""
        ...

    def get_depth(
        self,
        symbol: str,
        exchange: str,
        mode: str = "depth_20",
    ) -> MarketDepth:
        """Fetch depth for the given mode.

        Args:
            symbol: Trading symbol.
            exchange: Exchange code.
            mode: Depth mode identifier (e.g. ``"depth_20"``, ``"depth_200"``).

        Returns:
            ``MarketDepth`` with the requested number of levels.

        Raises:
            ValueError: If ``mode`` is not in ``supported_depth_modes``.
        """
        ...

    def subscribe_depth(
        self,
        symbol: str,
        exchange: str,
        mode: str,
        callback: Any,
    ) -> None:
        """Subscribe to live depth updates for the given mode."""
        ...

    def unsubscribe_depth(
        self,
        symbol: str,
        exchange: str,
        mode: str,
    ) -> None:
        """Unsubscribe from live depth updates."""
        ...
