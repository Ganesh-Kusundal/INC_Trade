"""Dhan Super Orders extension adapter."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from inc_trade.domain.enums import OrderType, ProductType, Side, Validity
from inc_trade.ports.http_client_port import HttpClientPort
from inc_trade.utils.price import to_wire_float

from brokers.adapters.dhan.config import (
    ENDPOINTS,
    ORDER_TYPE_MAP,
    PRODUCT_TYPE_MAP,
    SIDE_MAP,
    VALIDITY_MAP,
)
from brokers.adapters.dhan.extensions.models import SuperOrder, SuperOrderLeg
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload

logger = logging.getLogger(__name__)


class DhanSuperOrders:
    def __init__(self, client: HttpClientPort, resolver: DhanInstrumentResolver):
        self._client = client
        self._resolver = resolver

    def place_super_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal,
        target_price: Decimal,
        stop_loss_price: Decimal,
        trailing_jump: Decimal,
        product_type: ProductType = ProductType.INTRADAY,
        order_type: OrderType = OrderType.LIMIT,
        validity: Validity = Validity.DAY,
        correlation_id: str | None = None,
    ) -> SuperOrder:

        errors = self._validate_super_order(side, price, target_price, stop_loss_price)
        if errors:
            raise ValueError(f"Super order validation failed: {'; '.join(errors)}")

        ref = self._resolver.resolve(symbol, exchange)

        payload = {
            "dhanClientId": self._client.client_id,
            "exchangeSegment": ref.exchange_segment,
            "securityId": ref.security_id_str(),
            "transactionType": SIDE_MAP.get(side.value, 1),
            "orderType": ORDER_TYPE_MAP.get(order_type.value, 1),
            "productType": PRODUCT_TYPE_MAP.get(product_type.value, "INTRADAY"),
            "validity": VALIDITY_MAP.get(validity.value, "DAY"),
            "quantity": quantity,
            "price": to_wire_float(price),
            "targetPrice": to_wire_float(target_price),
            "stopLossPrice": to_wire_float(stop_loss_price),
            "trailingJump": to_wire_float(trailing_jump),
        }

        if correlation_id:
            payload["correlationId"] = correlation_id

        assert_valid_dhan_payload(payload, context="super_orders.place_super_order")

        data = self._client.post(
            f"{ENDPOINTS['orders'].rsplit('/orders', 1)[0]}/super/orders", json=payload
        )
        order_data = data.get("data", data)
        return self._parse_super_order(order_data)

    def _validate_super_order(
        self,
        side: Side,
        price: Decimal,
        target_price: Decimal,
        stop_loss_price: Decimal,
    ) -> list[str]:
        errors = []
        if side == Side.BUY:
            if target_price <= price:
                errors.append("target_price must be > entry price for BUY")
            if stop_loss_price >= price:
                errors.append("stop_loss_price must be < entry price for BUY")
        else:
            if target_price >= price:
                errors.append("target_price must be < entry price for SELL")
            if stop_loss_price <= price:
                errors.append("stop_loss_price must be > entry price for SELL")

        if price <= 0:
            errors.append("price must be positive")
        if target_price <= 0:
            errors.append("target_price must be positive")
        if stop_loss_price <= 0:
            errors.append("stop_loss_price must be positive")

        return errors

    def _parse_super_order(self, data: dict[str, Any]) -> SuperOrder:
        legs_data = data.get("legDetails", [])
        legs = []
        for leg in legs_data:
            legs.append(
                SuperOrderLeg(
                    leg_name=leg.get("legName", ""),
                    transaction_type=leg.get("transactionType", ""),
                    quantity=leg.get("quantity", 0),
                    price=Decimal(str(leg.get("price", 0))),
                    trigger_price=Decimal(str(leg.get("triggerPrice")))
                    if leg.get("triggerPrice") is not None
                    else None,
                    order_status=leg.get("orderStatus", ""),
                    trailing_jump=Decimal(str(leg.get("trailingJump")))
                    if leg.get("trailingJump") is not None
                    else None,
                )
            )

        return SuperOrder(
            order_id=str(data.get("orderId", "")),
            correlation_id=data.get("correlationId"),
            transaction_type=data.get("transactionType", ""),
            exchange_segment=data.get("exchangeSegment", ""),
            product_type=data.get("productType", ""),
            order_type=data.get("orderType", ""),
            security_id=str(data.get("securityId", "")),
            quantity=int(data.get("quantity", 0)),
            price=Decimal(str(data.get("price", 0))),
            target_price=Decimal(str(data.get("targetPrice", 0))),
            stop_loss_price=Decimal(str(data.get("stopLossPrice", 0))),
            trailing_jump=Decimal(str(data.get("trailingJump", 0))),
            order_status=data.get("orderStatus", ""),
            trading_symbol=data.get("tradingSymbol", ""),
            created_time=data.get("createdAt", ""),
            leg_details=legs,
        )
