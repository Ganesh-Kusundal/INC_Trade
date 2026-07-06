"""Dhan Margin Trading Facility (MTF) adapter."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from brokers.domain.enums import OrderType, Side, Validity
from brokers.ports.http_client_port import HttpClientPort
from brokers.utils.price import wire_price_or_zero

from brokers.adapters.dhan.config import (
    ENDPOINTS,
    ORDER_TYPE_MAP,
    SIDE_MAP,
    VALIDITY_MAP,
)
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload

logger = logging.getLogger(__name__)


class DhanMTF:
    """Margin Trading Facility (MTF) adapter for Dhan."""

    def __init__(
        self,
        client: HttpClientPort,
        resolver: DhanInstrumentResolver,
    ) -> None:
        self._client = client
        self._resolver = resolver

    def place_mtf_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
    ) -> dict[str, Any]:
        """Place an MTF (Margin Trading Facility) order.

        MTF uses the standard order endpoint but with productType set to MTF.
        """
        ref = self._resolver.resolve(symbol, exchange)
        payload = {
            "dhanClientId": self._client.client_id,
            "transactionType": SIDE_MAP.get(side.value, 1),
            "exchangeSegment": ref.exchange_segment,
            "securityId": ref.security_id_str(),
            "quantity": quantity,
            "orderType": ORDER_TYPE_MAP.get(order_type.value, 1),
            "productType": "MTF",
            "validity": VALIDITY_MAP.get(validity.value, "DAY"),
            "price": wire_price_or_zero(price),
            "triggerPrice": wire_price_or_zero(trigger_price),
        }
        assert_valid_dhan_payload(payload, context="mtf.place_mtf_order")
        logger.info("placing_mtf_order", extra={"payload": payload})

        response = self._client.post(ENDPOINTS.get("orders", "/orders"), json=payload)
        return response
