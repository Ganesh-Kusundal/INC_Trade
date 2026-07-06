"""Upstox-specific extension protocols — capabilities unique to Upstox.

These protocols define broker-specific features that are NOT part of the
common broker contract. They live in the adapter layer, not the ports layer,
ensuring common interfaces remain broker-agnostic.

Usage::

    from brokers_core.adapters.upstox.extensions.protocols import (
        GTTProvider,
        NewsProvider,
    )

    registry: ExtensionRegistryPort = ...
    gtt = registry.resolve("upstox", GTTProvider)
    if gtt is not None:
        result = gtt.place_gtt({...})
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from brokers_core.domain.entities import Order, OrderResponse


@runtime_checkable
class GTTProvider(Protocol):
    """Upstox-native GTT (Good Till Triggered) orders.

    Upstox supports server-side GTT orders that trigger a market order
    when the LTP crosses a specified threshold. This is distinct from
    regular limit/stop-loss orders and is managed server-side.
    """

    def place_gtt(self, request: dict[str, Any]) -> OrderResponse: ...
    def modify_gtt(self, gtt_id: str, changes: dict[str, Any]) -> OrderResponse: ...
    def cancel_gtt(self, gtt_id: str) -> OrderResponse: ...
    def get_gtt_orders(self) -> list[Order]: ...


@runtime_checkable
class NewsProvider(Protocol):
    """Upstox-native market news feed.

    Upstox provides market news and announcements that can be filtered
    by symbol. This is a broker-specific capability not available through
    common interfaces.
    """

    def get_news(self, symbol: str | None = None) -> list[dict[str, Any]]: ...
