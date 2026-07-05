"""Place-order use case — validate, resolve, idempotency, risk check, POST."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any, Protocol

from inc_trade.config.endpoints import Dhan as _DhanEndpoints

ENDPOINTS = _DhanEndpoints.ENDPOINTS
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload
from brokers.adapters.dhan.mapper import map_order_response
from brokers.adapters.dhan.payload import build_dhan_order_payload
from brokers.adapters.dhan.segments import resolve_segment
from inc_trade.domain import Order, OrderRequest, OrderResponse, RiskCheckRequest
from inc_trade.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from inc_trade.domain.exceptions import InstrumentNotFoundError, ValidationError
from inc_trade.domain.validators.order_validator import check_notional_warning, validate_order
from inc_trade.utils.idempotency_cache import TypedIdempotencyCache
from inc_trade.utils.price import is_tick_aligned, to_wire_float

logger = logging.getLogger(__name__)


class _HttpClient(Protocol):
    client_id: str

    def post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]: ...


class _Resolver(Protocol):
    def resolve(
        self, symbol: str, exchange: str, *, expected_segment: str | None = None
    ) -> Any: ...


class PlaceOrderUseCase:
    """Encapsulates the Dhan place-order pipeline."""

    def __init__(
        self,
        client: _HttpClient,
        resolver: _Resolver,
        *,
        endpoints: dict[str, str],
        idempotency: TypedIdempotencyCache[OrderResponse],
        risk_manager: Any | None = None,
        derivative_segments: frozenset[str],
        equity_only_products: frozenset[str],
        side_map: dict[str, int],
        order_type_map: dict[str, int],
        product_type_map: dict[str, str],
        validity_map: dict[str, str],
    ) -> None:
        self._client = client
        self._resolver = resolver
        self._endpoints = endpoints
        self._idempotency = idempotency
        self._risk_manager = risk_manager
        self._derivative_segments = derivative_segments
        self._equity_only_products = equity_only_products
        self._side_map = side_map
        self._order_type_map = order_type_map
        self._product_type_map = product_type_map
        self._validity_map = validity_map

    def execute(self, request: OrderRequest) -> tuple[OrderResponse, Order | None]:
        """Return (response, placed_order_for_events)."""
        cid = request.correlation_id or str(uuid.uuid4())

        with self._idempotency.lock(cid):
            cached = self._idempotency.get(cid)
            if cached is not None:
                logger.info(
                    "idempotency_hit",
                    extra={"correlation_id": cid, "order_id": cached.order_id},
                )
                return cached, None

            try:
                ref = self._resolver.resolve(
                    request.symbol,
                    request.exchange,
                    expected_segment=resolve_segment(request.exchange),
                )
            except InstrumentNotFoundError as exc:
                return OrderResponse.fail(str(exc), error_code="INSTRUMENT_NOT_FOUND"), None

            validation_error = self.validate(ref, request)
            if validation_error:
                logger.warning(
                    "order_validation_failed",
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

            preview = Order(
                order_id="",
                symbol=request.symbol,
                exchange=request.exchange,
                side=request.side,
                order_type=request.order_type,
                quantity=request.quantity,
                status=OrderStatus.OPEN,
                price=request.price,
                trigger_price=request.trigger_price,
                product_type=request.product_type,
                validity=request.validity,
                correlation_id=cid,
            )
            if self._risk_manager is not None:
                risk_request = RiskCheckRequest(
                    symbol=preview.symbol,
                    exchange=preview.exchange,
                    side=preview.side,
                    quantity=preview.quantity,
                    price=preview.price,
                    order_type=preview.order_type,
                )
                risk_result = self._risk_manager.check_order(risk_request)
                if not getattr(risk_result, "allowed", True):
                    reason = getattr(risk_result, "reason", "risk check failed")
                    return OrderResponse.fail(f"Risk check failed: {reason}"), None

            payload = build_dhan_order_payload(
                client_id=self._client.client_id,
                request=request,
                ref=ref,
                side_map=self._side_map,
                order_type_map=self._order_type_map,
                product_type_map=self._product_type_map,
                validity_map=self._validity_map,
            )
            payload["correlationId"] = cid
            assert_valid_dhan_payload(payload, context="orders.place_order")
            data = self._client.post(self._endpoints["orders"], json=payload)
            response = map_order_response(data)
            placed: Order | None = None
            if response.success:
                self._idempotency.put(cid, response)
                placed = Order(
                    order_id=response.order_id,
                    symbol=request.symbol,
                    exchange=request.exchange,
                    side=request.side,
                    order_type=request.order_type,
                    quantity=request.quantity,
                    status=response.status,
                    price=request.price,
                    trigger_price=request.trigger_price,
                    product_type=request.product_type,
                    validity=request.validity,
                    correlation_id=cid,
                )
                logger.info(
                    "order_placed",
                    extra={
                        "order_id": response.order_id,
                        "symbol": request.symbol,
                        "correlation_id": cid,
                    },
                )
            return response, placed

    def validate(self, ref: Any, request: OrderRequest) -> str | None:
        try:
            validate_order(
                symbol=request.symbol,
                exchange=request.exchange,
                quantity=request.quantity,
                order_type=request.order_type,
                price=request.price,
                trigger_price=request.trigger_price,
            )
        except ValidationError as e:
            return str(e)

        if request.order_type == OrderType.LIMIT and request.price <= 0:
            return "Limit order requires price > 0"
        if request.order_type == OrderType.STOP_LOSS and (
            request.price <= 0 or request.trigger_price <= 0
        ):
            return "Stop-Loss (Limit) order requires price > 0 and trigger_price > 0"
        if request.order_type == OrderType.STOP_LOSS_MARKET and request.trigger_price <= 0:
            return "Stop-Loss Market order requires trigger_price > 0"

        segment = ref.exchange_segment
        if (
            segment in self._derivative_segments
            and ref.lot_size > 1
            and request.quantity % ref.lot_size != 0
        ):
            return (
                f"Quantity {request.quantity} is not a multiple of lot size "
                f"{ref.lot_size} for {ref.symbol}"
            )

        if segment in self._derivative_segments and request.product_type == ProductType.DELIVERY:
            return (
                f"Product type DELIVERY is not valid for {segment}. "
                "Use INTRADAY or MARGIN for derivatives."
            )

        tick = getattr(ref, "tick_size", None)
        if request.price > 0 and tick is not None and tick > 0:
            if not is_tick_aligned(request.price, Decimal(str(tick))):
                return f"Price {request.price} is not aligned to tick size {tick} for {ref.symbol}"

        pt_val = request.product_type.value
        if segment in self._derivative_segments and pt_val in self._equity_only_products:
            return (
                f"Product type {pt_val} is not valid for {segment}. "
                "Use INTRADAY or MARGIN for derivatives."
            )
        return None
