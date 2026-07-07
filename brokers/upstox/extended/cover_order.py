"""Upstox cover orders — BEST-EFFORT EMULATION, NOT a real Cover Order.

⚠️  NOT A REAL COVER ORDER ⚠️

Upstox has no dedicated cover-order (CO) API. This module emulates one by
placing a LIMIT entry order and attempting a modify-based "exit". This is
NOT an exchange-native bracket/cover order with a guaranteed attached
stop-loss — there is no broker-side protection, no auto-square-off, and the
stop-loss is not enforceable if this process dies. Treat it as a plain
LIMIT order plus a manual exit; do NOT rely on it for risk control.

Correctness of any "stop-loss" semantics is NOT guaranteed. Use at your own
risk. For real bracket/cover semantics, route through a broker that exposes
a native CO endpoint.
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxCoverOrders:
    """BEST-EFFORT EMULATION of a cover order (NOT a real CO — see module doc)."""

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
        """Place a LIMIT entry order (emulated CO — no native stop-loss).

        NOTE: This is a normal LIMIT order. The native-CO stop-loss semantics
        are NOT provided. ``trigger_price`` is accepted for signature parity
        but is NOT enforced as a guaranteed broker-side stop.
        """
        payload = {
            "instrument_token": instrument_key,
            "quantity": quantity,
            "price": price,
            "trigger_price": trigger_price,
            "transaction_type": transaction_type,
            "product": product,
            "order_type": "LIMIT",
        }
        logger.info("upstox_cover_order_place_emulated", instrument=instrument_key)
        return self._client.post("/v2/order/place", json=payload)

    def exit_cover_order(self, order_id: str) -> dict[str, Any]:
        """Exit the emulated CO by modifying it to a MARKET order.

        NOTE: A plain modify-to-MARKET, not a guaranteed CO exit.
        """
        logger.info("upstox_cover_order_exit_emulated", order_id=order_id)
        return self._client.put("/v2/order/modify", json={
            "order_id": order_id,
            "order_type": "MARKET",
        })


__all__ = ["UpstoxCoverOrders"]
