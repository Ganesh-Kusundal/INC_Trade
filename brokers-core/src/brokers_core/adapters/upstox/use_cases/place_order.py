"""Upstox place-order use case — validate, resolve, idempotency, POST.

This module mirrors the architecture established for the Dhan adapter in
:mod:`brokers.adapters.dhan.use_cases.place_order`. Order validation is
delegated to the unified :class:`OrderValidationService` which consolidates
field-level and broker-specific rules. The adapter only owns the
idempotency, instrument resolution, and HTTP POST pipeline.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Protocol

from brokers_core.domain import Order, OrderRequest, OrderResponse
from brokers_core.domain.enums import OrderStatus
from brokers_core.domain.validators.order_validator import (
    check_notional_warning,
)
from brokers_core.services.order_validator import OrderValidationService
from brokers_core.ports.instruments import InstrumentInfo
from brokers_core.utils.idempotency_cache import TypedIdempotencyCache
from brokers_core.utils.price import wire_price_or_zero

from brokers_core.adapters.upstox.config import (
    EXCHANGE_TO_SEGMENT,
    PRODUCT_TYPE_MAP,
    VALIDITY_MAP,
)
from brokers_core.adapters.upstox.instruments import UpstoxInstruments, resolve_upstox_instrument_key
from brokers_core.adapters.upstox.mapper import map_order_response
from brokers_core.adapters.upstox.wire_mapper import UpstoxWireMapper

_WIRE_MAPPER = UpstoxWireMapper()

# Segment codes for Upstox derivative (F&O, MCX, currency) exchanges.
# Used by this use case to enforce the broker-specific product/segment
# matrix and lot-size rules.
DERIVATIVE_SEGMENTS: frozenset[str] = frozenset({"NSE_FO", "BSE_FO", "MCX_FO", "NCD_FO", "BCD_FO"})

# Domain ProductType values that are not valid on derivative segments.
# Upstox maps both DELIVERY and MARGIN to the wire-format "D"; on the
# domain side, DELIVERY/MARGIN are the equity-only products.
EQUITY_ONLY_PRODUCTS: frozenset[str] = frozenset({"DELIVERY", "MARGIN"})

logger = logging.getLogger(__name__)


class _HttpClient(Protocol):
    def post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]: ...


class _Resolver(Protocol):
    def resolve(self, symbol: str, exchange: str) -> InstrumentInfo | None: ...


class UpstoxResolverAdapter:
    """Thin adapter that exposes ``.resolve(symbol, exchange)`` for the use case.

    ``UpstoxInstruments.resolve`` already returns ``InstrumentInfo | None``,
    but the use case's ``_Resolver`` Protocol expects the same shape on a
    non-``None`` callable. When no instrument master is loaded, the use
    case still needs a synthetic ``InstrumentInfo`` (so that ref-dependent
    validation has a segment to inspect) rather than ``None``; this
    adapter handles both cases uniformly by falling back to a segment
    derived from the exchange code.
    """

    __slots__ = ("_instruments",)

    def __init__(self, instruments: UpstoxInstruments | None) -> None:
        self._instruments = instruments

    def resolve(self, symbol: str, exchange: str) -> InstrumentInfo | None:
        if self._instruments is None:
            return _fallback_instrument_info(symbol, exchange)
        return self._instruments.resolve(symbol, exchange)


def _fallback_instrument_info(symbol: str, exchange: str) -> InstrumentInfo:
    """Return a minimal ``InstrumentInfo`` when no instrument master is loaded.

    Mirrors the original ``resolve_upstox_instrument_key`` fallback path so
    that the place-order pipeline can proceed with a synthetic ref. The
    lot size is conservatively set to 1 (no batch enforcement) and the
    segment is derived from the exchange code, which keeps ref-dependent
    validation quiet for the common equity-only case.
    """
    segment = EXCHANGE_TO_SEGMENT.get(exchange.upper(), exchange.upper())
    return InstrumentInfo(
        symbol=symbol,
        exchange=exchange,
        segment=segment,
        lot_size=1,
    )


class PlaceOrderUseCase:
    """Encapsulates the Upstox place-order pipeline."""

    def __init__(
        self,
        client: _HttpClient,
        resolver: _Resolver,
        *,
        urls: Any,  # _UpstoxUrls; injected to keep endpoints out of module-level imports (H-4)
        idempotency_cache: TypedIdempotencyCache[OrderResponse],
        instruments: UpstoxInstruments | None = None,
        derivative_segments: frozenset[str],
        equity_only_products: frozenset[str],
    ) -> None:
        self._client = client
        self._resolver = resolver
        self._urls = urls
        self._idempotency_cache = idempotency_cache
        self._instruments = instruments
        self._derivative_segments = derivative_segments
        self._equity_only_products = equity_only_products
        self._validator = OrderValidationService(
            derivative_segments=derivative_segments,
            equity_only_products=equity_only_products,
        )

    def execute(
        self,
        request: OrderRequest,
        *,
        is_amo: bool = False,
    ) -> tuple[OrderResponse, Order | None]:
        """Return ``(response, placed_order_for_events)``.

        Performs idempotency lookup, instrument resolution, validation,
        notional warning, payload build, POST, and response mapping.
        """
        cid = request.correlation_id

        if cid:
            cached = self._idempotency_cache.get(cid)
            if cached is not None:
                logger.info(
                    "upstox_idempotency_hit",
                    extra={"correlation_id": cid, "order_id": cached.order_id},
                )
                return cached, None

        ref = self._resolver.resolve(request.symbol, request.exchange)
        if ref is None:
            return (
                OrderResponse.fail(
                    f"Instrument not found: {request.symbol} on {request.exchange}",
                    error_code="INSTRUMENT_NOT_FOUND",
                ),
                None,
            )

        validation_error = self.validate(ref, request)
        if validation_error:
            logger.warning(
                "upstox_order_validation_failed",
                extra={"symbol": request.symbol, "error": validation_error},
            )
            return (
                OrderResponse.fail(
                    f"Order validation failed: {validation_error}",
                    error_code="VALIDATION_FAILED",
                ),
                None,
            )

        check_notional_warning(request.quantity, request.price)

        instrument_token = resolve_upstox_instrument_key(
            request.symbol,
            request.exchange,
            self._instruments,
        )
        payload: dict[str, Any] = {
            "quantity": request.quantity,
            "product": PRODUCT_TYPE_MAP.get(request.product_type.value, "I"),
            "validity": VALIDITY_MAP.get(request.validity.value, "DAY"),
            "price": wire_price_or_zero(request.price),
            "instrument_token": instrument_token,
            "order_type": _WIRE_MAPPER.map_order_type(request.order_type),
            "transaction_type": _WIRE_MAPPER.map_side(request.side),
            "disclosed_quantity": 0,
            "trigger_price": wire_price_or_zero(request.trigger_price),
            "is_amo": is_amo,
        }
        if cid:
            payload["tag"] = cid

        data = self._client.post(self._urls.orders_interactive_url(), json=payload)
        response = map_order_response(data)
        placed: Order | None = None
        if response.success and cid:
            self._idempotency_cache.put(cid, response)
        if response.success:
            placed = Order(
                order_id=response.order_id,
                symbol=request.symbol,
                exchange=request.exchange,
                side=request.side,
                order_type=request.order_type,
                quantity=request.quantity,
                status=response.status or OrderStatus.OPEN,
                price=request.price,
                trigger_price=request.trigger_price,
                product_type=request.product_type,
                validity=request.validity,
                correlation_id=cid,
            )
            logger.info(
                "upstox_order_placed",
                extra={
                    "order_id": response.order_id,
                    "symbol": request.symbol,
                    "correlation_id": cid,
                },
            )
        return response, placed

    def validate(self, ref: InstrumentInfo, request: OrderRequest) -> str | None:
        """Return a stable error string for the order, or ``None`` if valid.

        Delegates entirely to the unified :class:`OrderValidationService`.
        ``ref`` is guaranteed non-None by the caller (execute() checks
        before calling validate()).
        """
        return self._validator.validate(
            symbol=request.symbol,
            exchange=request.exchange,
            quantity=request.quantity,
            order_type=request.order_type,
            price=request.price,
            trigger_price=request.trigger_price,
            product_type=request.product_type,
            lot_size=ref.lot_size,
            tick_size=Decimal(str(getattr(ref, "tick_size", "0.05"))),
            segment=ref.segment,
        )
