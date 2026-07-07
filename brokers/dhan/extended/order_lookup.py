"""Dhan order lookup — retrieve orders by correlation ID or order ID.

API: GET /orders — full order book (filter client-side)
     GET /orders/{order_id} — single order
"""

from __future__ import annotations

from typing import Any

from brokers.dhan.mapper import DhanMapper
from brokers.domain.order import Order
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


class DhanOrderLookup:
    """Order retrieval by ID or correlation tag.

    Usage::

        lookup = DhanOrderLookup(client=dhan_client)
        orders = lookup.get_by_correlation_id("my_tag")
        order = lookup.get_by_order_id("123456")
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_by_order_id(self, order_id: str) -> Order | None:
        """Fetch a single order by its broker order ID."""
        data = self._client.get(f"/orders/{order_id}")
        raw = data.get("data", data) if isinstance(data, dict) else {}
        if isinstance(raw, dict) and raw.get("orderId"):
            return DhanMapper.map_order(raw)
        return None

    def get_by_correlation_id(self, correlation_id: str) -> list[Order]:
        """Fetch all orders matching a correlation ID (tag)."""
        data = self._client.get("/orders")
        items = data.get("data", []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            return []
        return [
            DhanMapper.map_order(item)
            for item in items
            if isinstance(item, dict) and item.get("correlationId") == correlation_id
        ]

    def get_order_book(self) -> list[Order]:
        """Fetch the full order book."""
        data = self._client.get("/orders")
        items = data.get("data", []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            return []
        return [DhanMapper.map_order(item) for item in items if isinstance(item, dict)]


__all__ = ["DhanOrderLookup"]
