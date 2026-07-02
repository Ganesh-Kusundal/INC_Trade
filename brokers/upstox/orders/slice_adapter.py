"""Upstox slice order adapter — implements ``SliceOrderCommand``.

Upstox has no native server-side slice; this is a client-side slicer that
respects ``freeze_qty`` from the instrument master. Each child is a MARKET
order with 100 ms spacing.

Mirrors ``brokers.dhan.orders.special_orders_adapter.DhanSliceOrderAdapter``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from brokers.common.dtos import BrokerOrderPayload
from brokers.common.gateway_interfaces import SliceOrderCommand
from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from domain import Order, SliceOrderRequest
from domain.symbols import normalize_symbol

logger = logging.getLogger(__name__)

DEFAULT_SLICE_SPACING_MS = 100


class UpstoxSliceAdapter(SliceOrderCommand):
    def __init__(
        self,
        order_client: UpstoxRestOrderClient,
        instrument_resolver: UpstoxInstrumentResolver,
        *,
        spacing_ms: int = DEFAULT_SLICE_SPACING_MS,
    ) -> None:
        self._order_client = order_client
        self._instrument_resolver = instrument_resolver
        self._spacing_ms = spacing_ms

    def place_slice_order(self, request: SliceOrderRequest) -> list[Order]:
        instrument_key = self._resolve_instrument_key(request.symbol, request.exchange_segment)
        if not instrument_key:
            return []

        definition = self._instrument_resolver.resolve(instrument_key=instrument_key)
        freeze_qty = (
            definition.freeze_qty
            if definition is not None and definition.freeze_qty
            else self._infer_freeze_qty(request.symbol)
        )
        slice_qty = (
            request.slice_quantity
            if request.slice_quantity
            else (freeze_qty or max(1, request.quantity // 10))
        )

        children: list[Order] = []
        remaining = request.quantity
        correlation = request.correlation_id
        while remaining > 0:
            qty = min(slice_qty, remaining)
            child_request = BrokerOrderPayload(
                symbol=request.symbol,
                exchange_segment=request.exchange_segment,
                transaction_type=request.transaction_type,
                quantity=qty,
                price=request.price,
                trigger_price=request.trigger_price,
                order_type=request.order_type,
                product_type=request.product_type,
                validity=request.validity,
                correlation_id=correlation,
            )
            payload = UpstoxDomainMapper.to_place_payload(child_request, instrument_key)
            result = self._order_client.place_order_v3(payload)
            order_id = ""
            if isinstance(result, dict):
                data = result.get("data")
                if isinstance(data, dict):
                    order_id = str(data.get("order_id") or "")
            children.append(Order(order_id=order_id, symbol=request.symbol, quantity=qty))
            remaining -= qty
            if remaining > 0 and self._spacing_ms > 0:
                time.sleep(self._spacing_ms / 1000.0)
        return children

    def _resolve_instrument_key(self, symbol: str, exchange_segment: Any) -> str:
        seg_wire = UpstoxDomainMapper.segment_to_wire(exchange_segment)
        definition = self._instrument_resolver.resolve(symbol=symbol, exchange_segment=seg_wire)
        if definition is not None:
            return definition.instrument_key
        return f"{seg_wire}|{symbol}"

    def _infer_freeze_qty(self, symbol: str) -> int:
        # Fallback freeze quantities for well-known NSE equities (Q3 2024).
        upper = normalize_symbol(symbol)
        well_known = {
            "RELIANCE": 1800,
            "TCS": 1700,
            "HDFCBANK": 5500,
            "INFY": 7000,
            "ICICIBANK": 27000,
            "SBIN": 15000,
            "HDFC": 5500,
            "BHARTIARTL": 18300,
            "ITC": 32000,
        }
        return well_known.get(upper, 0)
