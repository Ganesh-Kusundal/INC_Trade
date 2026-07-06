"""Dhan Margin extension adapter."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.domain.enums import OrderType, ProductType
from brokers.ports.http_client_port import HttpClientPort
from brokers.utils.price import to_wire_float

from brokers.adapters.dhan.config import (
    ENDPOINTS,
    ORDER_TYPE_MAP,
    PRODUCT_TYPE_MAP,
)
from brokers.adapters.dhan.extensions.models import MarginResponse
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload

logger = logging.getLogger(__name__)


class DhanMargin:
    def __init__(self, client: HttpClientPort, resolver: DhanInstrumentResolver):
        self._client = client
        self._resolver = resolver

    def calculate_margin(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        product_type: ProductType = ProductType.INTRADAY,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
    ) -> MarginResponse:

        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")

        if order_type in (OrderType.LIMIT, OrderType.STOP_LOSS) and (not price or price <= 0):
            raise ValueError("LIMIT/STOP_LOSS orders require price > 0")

        ref = self._resolver.resolve(symbol, exchange)

        payload = {
            "dhanClientId": self._client.client_id,
            "exchangeSegment": ref.exchange_segment,
            "securityId": ref.security_id_str(),
            "transactionType": 1,  # Default to BUY for margin calc
            "orderType": ORDER_TYPE_MAP.get(order_type.value, 1),
            "productType": PRODUCT_TYPE_MAP.get(product_type.value, "INTRADAY"),
            "quantity": quantity,
        }

        if price is not None and price > 0:
            payload["price"] = to_wire_float(price)
        if trigger_price is not None and trigger_price > 0:
            payload["triggerPrice"] = to_wire_float(trigger_price)

        assert_valid_dhan_payload(payload, context="margin.calculate")

        data = self._client.post(
            f"{ENDPOINTS['orders'].rsplit('/orders', 1)[0]}/margincalculator",
            json=payload,
        )

        response_data = data.get("data", data)
        return MarginResponse(
            total_margin=Decimal(str(response_data.get("totalMargin", 0))),
            order_margin=Decimal(str(response_data.get("orderMargin", 0))),
            exposure_margin=Decimal(str(response_data.get("exposureMargin", 0))),
            available_margin=Decimal(str(response_data["availableMargin"]))
            if "availableMargin" in response_data
            else None,
            span_margin=Decimal(str(response_data["spanMargin"]))
            if "spanMargin" in response_data
            else None,
        )
