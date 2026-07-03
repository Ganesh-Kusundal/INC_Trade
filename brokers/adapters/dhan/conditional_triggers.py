"""Dhan Conditional Triggers (GTT) adapter."""

from __future__ import annotations

import logging

from decimal import Decimal

from brokers.adapters.dhan.config import (
    ORDER_TYPE_MAP,
    PRODUCT_TYPE_MAP,
    SIDE_MAP,
    VALIDITY_MAP,
)
from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.domain.enums import OrderType, ProductType, Side, Validity
from brokers.utils.price import to_wire_float

logger = logging.getLogger(__name__)


class DhanConditionalTriggers:
    """Conditional Triggers (GTT) trading adapter for Dhan.

    Allows placing orders that are triggered when a condition is met.
    """

    def __init__(
        self, client: DhanHttpClient, resolver: DhanInstrumentResolver
    ) -> None:
        self._client = client
        self._resolver = resolver

    def place_conditional_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.LIMIT,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
    ) -> dict:
        """Place a conditional (GTT) order.

        Parameters
        ----------
        symbol : str
            Instrument symbol.
        exchange : str
            Exchange (e.g. NSE, BSE).
        side : Side
            BUY or SELL.
        quantity : int
            Quantity to trade.
        order_type : OrderType, optional
            Type of order (MARKET/LIMIT), by default OrderType.LIMIT.
        price : Decimal, optional
            Limit price.
        product_type : ProductType, optional
            Product type.
        validity : Validity, optional
            Validity of order.
        trigger_price : Decimal, optional
            Price at which the condition is triggered.

        Returns
        -------
        dict
            Broker response containing the trigger ID.
        """
        ref = self._resolver.resolve(symbol, exchange)
        payload = {
            "dhanClientId": self._client.client_id,
            "transactionType": SIDE_MAP.get(side.value, 1),
            "exchangeSegment": ref.exchange_segment,
            "securityId": ref.security_id_str(),
            "quantity": quantity,
            "orderType": ORDER_TYPE_MAP.get(order_type.value, 1),
            "productType": PRODUCT_TYPE_MAP.get(product_type.value, "INTRADAY"),
            "validity": VALIDITY_MAP.get(validity.value, "DAY"),
            "price": to_wire_float(price) if price > 0 else 0.0,
            "triggerPrice": to_wire_float(trigger_price) if trigger_price > 0 else 0.0,
        }

        logger.info("placing_conditional_order", extra={"payload": payload})

        # Using Dhan's conditional order endpoint
        response = self._client.post("/conditionalOrders", json=payload)
        return response

    def cancel_conditional_order(self, trigger_id: str) -> dict:
        """Cancel a pending conditional order."""
        logger.info("canceling_conditional_order", extra={"trigger_id": trigger_id})
        return self._client.delete(f"/conditionalOrders/{trigger_id}")

    def get_conditional_orders(self) -> list[dict]:
        """Fetch all conditional orders."""
        response = self._client.get("/conditionalOrders")
        return response.get("data", []) if isinstance(response, dict) else []
