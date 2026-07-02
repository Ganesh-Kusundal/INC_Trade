"""Dhan orders adapter — place, cancel, modify, query orders."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.adapters.dhan.config import (
    ENDPOINTS,
    ORDER_TYPE_MAP,
    PRODUCT_TYPE_MAP,
    SIDE_MAP,
    VALIDITY_MAP,
)
from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload
from brokers.adapters.dhan.mapper import map_order, map_order_response
from brokers.domain import Order, OrderResponse
from brokers.domain.enums import OrderType, ProductType, Side, Validity
from brokers.utils.price import to_wire_float

logger = logging.getLogger(__name__)


class DhanOrders:
    def __init__(self, client: DhanHttpClient, resolver: DhanInstrumentResolver):
        self._client = client
        self._resolver = resolver

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
    ) -> OrderResponse:
        ref = self._resolver.resolve(symbol, exchange)
        payload = {
            "dhanClientId": self._client._client_id,
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
        assert_valid_dhan_payload(payload, context="orders.place_order")
        data = self._client.post(ENDPOINTS["orders"], json=payload)
        return map_order_response(data)

    def cancel_order(self, order_id: str) -> OrderResponse:
        endpoint = ENDPOINTS["cancel_order"].format(order_id=order_id)
        self._client.post(endpoint)
        return OrderResponse(order_id=order_id, success=True)

    def get_order(self, order_id: str) -> Order | None:
        endpoint = ENDPOINTS["order_by_id"].format(order_id=order_id)
        data = self._client.get(endpoint)
        if isinstance(data, dict) and "data" in data:
            return map_order(data["data"])
        if isinstance(data, dict) and "orderId" in data:
            return map_order(data)
        return None

    def get_orderbook(self) -> list[Order]:
        data = self._client.get(ENDPOINTS["orderbook"])
        orders_data = data.get("data", [])
        if isinstance(orders_data, list):
            return [map_order(o) for o in orders_data]
        return []
