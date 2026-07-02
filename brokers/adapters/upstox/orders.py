"""Upstox orders adapter — place, cancel, query orders."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.adapters.upstox.config import (
    ENDPOINTS,
    EXCHANGE_TO_SEGMENT,
    ORDER_TYPE_MAP,
    PRODUCT_TYPE_MAP,
    VALIDITY_MAP,
)
from brokers.adapters.upstox.http import UpstoxHttpClient
from brokers.adapters.upstox.mapper import map_order, map_order_response
from brokers.domain import Order, OrderResponse
from brokers.domain.enums import OrderType, ProductType, Side, Validity
from brokers.utils.price import to_wire_float

logger = logging.getLogger(__name__)


def _instrument_key(symbol: str, exchange: str) -> str:
    segment = EXCHANGE_TO_SEGMENT.get(exchange.upper(), exchange)
    return f"{segment}|{symbol}"


class UpstoxOrders:
    def __init__(self, client: UpstoxHttpClient, allow_live_orders: bool = True):
        self._client = client
        self._allow_live_orders = allow_live_orders

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
        if not self._allow_live_orders:
            logger.warning("Live orders disabled — rejecting place_order for %s", symbol)
            raise PermissionError("Live orders disabled. Set allow_live_orders=True to enable.")
        instrument_token = _instrument_key(symbol, exchange)
        payload = {
            "quantity": quantity,
            "product": PRODUCT_TYPE_MAP.get(product_type.value, "I"),
            "validity": VALIDITY_MAP.get(validity.value, "DAY"),
            "price": to_wire_float(price) if price > 0 else 0.0,
            "instrument_token": instrument_token,
            "order_type": ORDER_TYPE_MAP.get(order_type.value, "MARKET"),
            "transaction_type": side.value,
            "disclosed_quantity": 0,
            "trigger_price": to_wire_float(trigger_price) if trigger_price > 0 else 0.0,
            "is_amo": False,
        }
        data = self._client.post(ENDPOINTS["place_order"], json=payload)
        return map_order_response(data)

    def cancel_order(self, order_id: str) -> OrderResponse:
        endpoint = ENDPOINTS["cancel_order"].format(order_id=order_id)
        data = self._client.delete(endpoint)
        if isinstance(data, dict):
            status = str(data.get("status", "")).lower()
            if status in ("success", "ok"):
                return OrderResponse(order_id=order_id, success=True)
        return OrderResponse(order_id=order_id, success=True)

    def get_order(self, order_id: str) -> Order | None:
        endpoint = ENDPOINTS["order_details"].format(order_id=order_id)
        data = self._client.get(endpoint)
        if isinstance(data, dict) and "data" in data:
            inner = data["data"]
            if isinstance(inner, list) and inner:
                return map_order(inner[0])
            if isinstance(inner, dict):
                return map_order(inner)
        return None

    def get_orderbook(self) -> list[Order]:
        data = self._client.get(ENDPOINTS["order_book"])
        orders_data = data.get("data", [])
        if isinstance(orders_data, list):
            return [map_order(o) for o in orders_data]
        return []
