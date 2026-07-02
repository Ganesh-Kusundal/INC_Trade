"""Upstox cover order adapter — stub.

Upstox has no native bracket/cover orders; this adapter best-effort emulates
cover by attaching a stop-loss to a regular entry. Returns ``Order`` objects
synthesised from the wire response.

Mirrors ``brokers.dhan.orders.cover_order_adapter.DhanCoverOrderAdapter``.
"""

from __future__ import annotations

from decimal import Decimal

from brokers.common.dtos import BrokerOrderPayload
from brokers.common.gateway_interfaces import CoverOrderProvider
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from domain import Order


class UpstoxCoverOrderAdapter(CoverOrderProvider):
    def __init__(self, order_client: UpstoxRestOrderClient) -> None:
        self._order_client = order_client

    def place_cover_order(self, request: BrokerOrderPayload, stop_loss_price: Decimal) -> Order:
        if request.trigger_price is None or request.trigger_price <= 0:
            request.trigger_price = stop_loss_price
        from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper

        seg_wire = UpstoxDomainMapper.segment_to_wire(request.exchange_segment)
        instrument_key = f"{seg_wire}|{request.symbol}"
        payload = UpstoxDomainMapper.to_place_payload(request, instrument_key)
        result = self._order_client.place_order_v3(payload)
        order_id = ""
        if isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, dict):
                order_id = str(data.get("order_id") or "")
        return Order(
            order_id=order_id or "CO_PENDING",
            symbol=request.symbol,
            quantity=request.quantity,
            trigger_price=stop_loss_price,
        )

    def exit_cover_order(self, order_id: str) -> Order:
        self._order_client.cancel_order_v3(order_id)
        return Order(order_id=order_id)
