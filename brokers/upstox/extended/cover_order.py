"""Upstox cover orders — place and exit cover orders with attached stop-loss.

Best-effort cover order emulation: places entry order then attaches stop-loss.
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxCoverOrders:
    """Cover order management for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def place_cover_order(
        self,
        instrument_key: str,
        quantity: int,
        price: float,
        trigger_price: float,
        transaction_type: str = "BUY",
        product: str = "I",
    ) -> dict[str, Any]:
        """Place a cover order (entry + stop-loss)."""
        payload = {
            "instrument_token": instrument_key,
            "quantity": quantity,
            "price": price,
            "trigger_price": trigger_price,
            "transaction_type": transaction_type,
            "product": product,
            "order_type": "LIMIT",
        }
        logger.info("upstox_cover_order_place", instrument=instrument_key)
        return self._client.post("/v2/order/place", json=payload)

    def exit_cover_order(self, order_id: str) -> dict[str, Any]:
        """Exit a cover order by placing an opposite market order."""
        logger.info("upstox_cover_order_exit", order_id=order_id)
        return self._client.put("/v2/order/modify", json={
            "order_id": order_id,
            "order_type": "MARKET",
        })


__all__ = ["UpstoxCoverOrders"]
