"""Upstox margin calculator — order margin and brokerage calculations.

API: POST /v2/margin/order — calculate margin for order
     GET /v2/margin/brokerage — get brokerage charges

Methods are ``async`` to satisfy the ``MarginExtension`` protocol
(``await instrument.extensions.margin.calculate(...)``). Synchronous HTTP
calls are offloaded via ``asyncio.to_thread``.
"""
from __future__ import annotations
import asyncio
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxMargin:
    """Margin calculator for Upstox (async — see module doc)."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    async def calculate_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Calculate margin requirements for a hypothetical order (async)."""
        data = await asyncio.to_thread(
            self._client.post, "/v2/margin/order", json=payload
        )
        return data.get("data", data) if isinstance(data, dict) else {}

    async def calculate(self, **kwargs: Any) -> dict[str, Any]:
        """Protocol-compatible alias for :meth:`calculate_margin`."""
        return await self.calculate_margin(kwargs)

    async def get_brokerage(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Get brokerage charges for an order (async)."""
        data = await asyncio.to_thread(
            self._client.post, "/v2/margin/brokerage", json=payload
        )
        return data.get("data", data) if isinstance(data, dict) else {}


__all__ = ["UpstoxMargin"]
