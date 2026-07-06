"""Dhan Forever Orders extension adapter."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from brokers_core.domain.enums import OrderType, ProductType, Side, Validity
from brokers_core.ports.http_client_port import HttpClientPort
from brokers_core.utils.price import to_wire_float

from brokers_core.adapters.dhan.config import (
    ENDPOINTS,
    ORDER_TYPE_MAP,
    PRODUCT_TYPE_MAP,
    SIDE_MAP,
    VALIDITY_MAP,
)
from brokers_core.adapters.dhan.extensions.models import ForeverOrder
from brokers_core.adapters.dhan.identity import DhanInstrumentResolver
from brokers_core.adapters.dhan.invariants import assert_valid_dhan_payload

logger = logging.getLogger(__name__)


class DhanForeverOrders:
    def __init__(self, client: HttpClientPort, resolver: DhanInstrumentResolver):
        self._client = client
        self._resolver = resolver

    def place_forever_order(self, request: dict[str, Any]) -> ForeverOrder:
        symbol = request.get("symbol", "")
        exchange = request.get("exchange", "NSE")
        side = request.get("side", Side.BUY)
        quantity = request.get("quantity", 0)
        price = request.get("price", Decimal("0"))
        trigger_price = request.get("trigger_price", Decimal("0"))
        order_flag = request.get("order_flag", "SINGLE")
        price1 = request.get("price1")
        trigger_price1 = request.get("trigger_price1")
        quantity1 = request.get("quantity1")
        product_type = request.get("product_type", ProductType.DELIVERY)
        order_type = request.get("order_type", OrderType.LIMIT)
        validity = request.get("validity", Validity.DAY)
        correlation_id = request.get("correlation_id")

        errors = self._validate_forever_order(
            order_flag,
            quantity,
            price,
            trigger_price,
            price1,
            trigger_price1,
            quantity1,
        )
        if errors:
            raise ValueError(f"Forever order validation failed: {'; '.join(errors)}")

        ref = self._resolver.resolve(symbol, exchange)

        payload = {
            "dhanClientId": self._client.client_id,
            "exchangeSegment": ref.exchange_segment,
            "securityId": ref.security_id_str(),
            "transactionType": SIDE_MAP.get(side.value, 1),
            "orderType": ORDER_TYPE_MAP.get(order_type.value, 1),
            "productType": PRODUCT_TYPE_MAP.get(product_type.value, "MARGIN"),
            "validity": VALIDITY_MAP.get(validity.value, "DAY"),
            "quantity": quantity,
            "price": to_wire_float(price),
            "triggerPrice": to_wire_float(trigger_price),
            "orderFlag": order_flag,
        }

        if order_flag == "OCO":
            if price1 is not None:
                payload["price1"] = to_wire_float(price1)
            if trigger_price1 is not None:
                payload["triggerPrice1"] = to_wire_float(trigger_price1)
            if quantity1 is not None:
                payload["quantity1"] = quantity1

        if correlation_id:
            payload["correlationId"] = correlation_id

        assert_valid_dhan_payload(payload, context="forever_orders.place_forever_order")

        data = self._client.post(
            f"{ENDPOINTS['orders'].rsplit('/orders', 1)[0]}/forever/orders",
            json=payload,
        )
        order_data = data.get("data", data)
        return self._parse_forever_order(order_data)

    def modify_forever_order(self, order_id: str, changes: dict[str, Any]) -> ForeverOrder:
        raise NotImplementedError("Modify not implemented for DhanForeverOrders")

    def cancel_forever_order(self, order_id: str) -> bool:
        raise NotImplementedError("Cancel not implemented for DhanForeverOrders")

    def get_forever_orders(self) -> list[Any]:
        raise NotImplementedError("Get forever orders not implemented for DhanForeverOrders")

    def _validate_forever_order(
        self,
        order_flag: str,
        quantity: int,
        price: Decimal,
        trigger_price: Decimal,
        price1: Decimal | None,
        trigger_price1: Decimal | None,
        quantity1: int | None,
    ) -> list[str]:
        errors = []
        if order_flag not in ("SINGLE", "OCO"):
            errors.append("order_flag must be SINGLE or OCO")

        if order_flag == "OCO":
            if price1 is None:
                errors.append("OCO requires price1")
            if trigger_price1 is None:
                errors.append("OCO requires trigger_price1")
            if quantity1 is None:
                errors.append("OCO requires quantity1")

        if price <= 0:
            errors.append("price must be positive")
        if trigger_price <= 0:
            errors.append("trigger_price must be positive")
        if quantity <= 0:
            errors.append("quantity must be positive")

        return errors

    def _parse_forever_order(self, data: dict[str, Any]) -> ForeverOrder:
        return ForeverOrder(
            order_id=str(data.get("orderId", "")),
            order_status=data.get("orderStatus", ""),
            order_flag=data.get("orderFlag", ""),
            transaction_type=data.get("transactionType", ""),
            exchange_segment=data.get("exchangeSegment", ""),
            product_type=data.get("productType", ""),
            order_type=data.get("orderType", ""),
            trading_symbol=data.get("tradingSymbol", ""),
            security_id=str(data.get("securityId", "")),
            quantity=int(data.get("quantity", 0)),
            price=Decimal(str(data.get("price", 0))),
            trigger_price=Decimal(str(data.get("triggerPrice", 0))),
            leg_name=data.get("legName"),
            created_time=data.get("createdAt"),
        )
