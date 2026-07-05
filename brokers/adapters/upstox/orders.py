"""Upstox orders adapter — place, cancel, query orders with production safety guards."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from brokers.adapters.upstox.config import ORDER_TYPE_MAP, PRODUCT_TYPE_MAP, VALIDITY_MAP
from brokers.adapters.upstox.instruments import UpstoxInstruments, resolve_upstox_instrument_key
from brokers.adapters.upstox.mapper import map_order, map_order_response, unwrap_data
from inc_trade.config.endpoints import _UpstoxUrls
from inc_trade.domain import Order, OrderResponse
from inc_trade.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from inc_trade.ports.http_client_port import HttpClientPort
from inc_trade.utils.idempotency_cache import TypedIdempotencyCache as InMemoryIdempotencyCache
from inc_trade.utils.price import to_wire_float

logger = logging.getLogger(__name__)


class UpstoxOrders:
    def __init__(
        self,
        client: HttpClientPort,
        urls: _UpstoxUrls,
        analytics_only: bool = False,
        idempotency_cache: InMemoryIdempotencyCache[OrderResponse] | None = None,
        instruments: UpstoxInstruments | None = None,
    ):
        self._client = client
        self._urls = urls
        self._analytics_only = analytics_only
        self._idempotency_cache = idempotency_cache or InMemoryIdempotencyCache()
        self._instruments = instruments

    def _resolve_key(self, symbol: str, exchange: str) -> str:
        return resolve_upstox_instrument_key(symbol, exchange, self._instruments)

    def _guard_live_order(self) -> OrderResponse | None:
        if self._analytics_only:
            return OrderResponse.fail(
                "Analytics-only token cannot place or modify live orders",
                error_code="ANALYTICS_ONLY",
            )
        return None

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
        correlation_id: str = "",
        is_amo: bool = False,
    ) -> OrderResponse:
        blocked = self._guard_live_order()
        if blocked is not None:
            return blocked

        if correlation_id:
            cached = self._idempotency_cache.get(correlation_id)
            if cached is not None:
                return cached

        instrument_token = self._resolve_key(symbol, exchange)
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
            "is_amo": is_amo,
        }
        if correlation_id:
            payload["tag"] = correlation_id

        data = self._client.post(self._urls.orders_interactive_url(), json=payload)
        response = map_order_response(data)
        if correlation_id and response.success:
            self._idempotency_cache.put(correlation_id, response)
        return response

    def cancel_order(self, order_id: str) -> OrderResponse:
        blocked = self._guard_live_order()
        if blocked is not None:
            return blocked

        endpoint = self._urls.cancel_order_interactive_url(order_id)
        data = self._client.delete(endpoint)
        response = map_order_response(data) if isinstance(data, dict) else None
        if response is None or not response.success:
            response = OrderResponse(order_id=order_id, success=True)

        if response.success:
            order = self.get_order(order_id)
            if order and order.status == OrderStatus.FILLED:
                return OrderResponse(
                    order_id=order_id,
                    success=False,
                    message="Order was already filled before cancel completed",
                    error_code="ALREADY_EXECUTED",
                    status=OrderStatus.FILLED,
                )
        return response

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> OrderResponse:
        blocked = self._guard_live_order()
        if blocked is not None:
            return blocked

        payload: dict[str, Any] = {"order_id": order_id}
        if quantity is not None:
            payload["quantity"] = quantity
        if price is not None:
            payload["price"] = to_wire_float(price)
        if order_type is not None:
            payload["order_type"] = ORDER_TYPE_MAP.get(order_type.value, "MARKET")
        if validity is not None:
            payload["validity"] = VALIDITY_MAP.get(validity.value, "DAY")

        data = self._client.put(self._urls.orders_interactive_url(), json=payload)
        return map_order_response(data)

    def get_order(self, order_id: str) -> Order | None:
        data = self._client.get(self._urls.order_details_interactive_url(order_id))
        if isinstance(data, dict) and "data" in data:
            inner = data["data"]
            if isinstance(inner, list) and inner:
                return map_order(inner[0])
            if isinstance(inner, dict):
                return map_order(inner)
        return None

    def get_orderbook(self) -> list[Order]:
        data = self._client.get(self._urls.orders_book_interactive_url())
        orders_data = unwrap_data(data)
        if isinstance(orders_data, list):
            return [map_order(o) for o in orders_data]
        return []
