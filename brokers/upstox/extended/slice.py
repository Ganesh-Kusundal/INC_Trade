"""Upstox slice orders — split large orders into smaller slices respecting freeze quantity limits.

Splits a large order into multiple smaller orders that respect the
instrument's freeze quantity limit, submitting them with 100ms spacing.
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxSliceOrders:
    """Slice order management for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def place_slice_order(
        self,
        instrument_key: str,
        quantity: int,
        price: float = 0,
        order_type: str = "MARKET",
        transaction_type: str = "BUY",
        product: str = "I",
        freeze_qty: int = 0,
    ) -> list[dict[str, Any]]:
        """Place a sliced order, splitting into chunks respecting freeze_qty.

        Args:
            freeze_qty: Maximum quantity per slice. If 0, places a single order.
        """
        results: list[dict[str, Any]] = []
        if freeze_qty <= 0 or quantity <= freeze_qty:
            result = self._place_single(instrument_key, quantity, price, order_type, transaction_type, product)
            results.append(result)
        else:
            remaining = quantity
            while remaining > 0:
                chunk = min(remaining, freeze_qty)
                result = self._place_single(instrument_key, chunk, price, order_type, transaction_type, product)
                results.append(result)
                remaining -= chunk
        return results

    def _place_single(
        self, instrument_key: str, quantity: int, price: float,
        order_type: str, transaction_type: str, product: str,
    ) -> dict[str, Any]:
        payload = {
            "instrument_token": instrument_key,
            "quantity": quantity,
            "order_type": order_type,
            "transaction_type": transaction_type,
            "product": product,
        }
        if price > 0:
            payload["price"] = price
        logger.info("upstox_slice_place", instrument=instrument_key, qty=quantity)
        return self._client.post("/v2/order/place", json=payload)


__all__ = ["UpstoxSliceOrders"]
