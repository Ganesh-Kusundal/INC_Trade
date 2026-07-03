"""Place-order use case — validate, resolve, idempotency, risk check, POST."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from brokers.adapters.dhan.endpoints import ENDPOINTS
from brokers.adapters.dhan.idempotency import DhanIdempotencyCache
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload
from brokers.adapters.dhan.mapper import map_order_response
from brokers.adapters.dhan.segments import resolve_segment
from brokers.domain import Order, OrderResponse, RiskCheckRequest
from brokers.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from brokers.domain.exceptions import InstrumentNotFoundError
from brokers.services.order_validation import check_notional_warning
from brokers.infrastructure.correlation import get_current_correlation_id
from brokers.utils.price import is_tick_aligned, to_wire_float

logger = logging.getLogger(__name__)


class _HttpClient(Protocol):
    client_id: str

    def post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]: ...


class _Resolver(Protocol):
    def resolve(
        self, symbol: str, exchange: str, *, expected_segment: str | None = None
    ) -> Any: ...


@dataclass(frozen=True)
class PlaceOrderRequest:
    symbol: str
    exchange: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    price: Decimal = Decimal("0")
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    trigger_price: Decimal = Decimal("0")
    correlation_id: str = ""


class PlaceOrderUseCase:
    """Encapsulates the Dhan place-order pipeline."""

    def __init__(
        self,
        client: _HttpClient,
        resolver: _Resolver,
        *,
        idempotency: DhanIdempotencyCache[OrderResponse],
        allow_live_orders: bool = True,
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
        self._idempotency = idempotency
        self._allow_live_orders = allow_live_orders
        self._risk_manager = risk_manager
        self._derivative_segments = derivative_segments
        self._equity_only_products = equity_only_products
        self._side_map = side_map
        self._order_type_map = order_type_map
        self._product_type_map = product_type_map
        self._validity_map = validity_map

    def execute(self, request: PlaceOrderRequest) -> tuple[OrderResponse, Order | None]:
        """Return (response, placed_order_for_events)."""
        if not self._allow_live_orders:
            return OrderResponse.live_orders_disabled(), None

        cid = (
            request.correlation_id
            or get_current_correlation_id()
            or str(uuid.uuid4())
        )

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

            payload = {
                "dhanClientId": self._client.client_id,
                "transactionType": self._side_map.get(request.side.value, 1),
                "exchangeSegment": ref.exchange_segment,
                "securityId": ref.security_id_str(),
                "quantity": request.quantity,
                "orderType": self._order_type_map.get(request.order_type.value, 1),
                "productType": self._product_type_map.get(
                    request.product_type.value, "INTRADAY"
                ),
                "validity": self._validity_map.get(request.validity.value, "DAY"),
                "price": to_wire_float(request.price) if request.price > 0 else 0.0,
                "triggerPrice": (
                    to_wire_float(request.trigger_price)
                    if request.trigger_price > 0
                    else 0.0
                ),
                "correlationId": cid,
            }
            assert_valid_dhan_payload(payload, context="orders.place_order")
            data = self._client.post(ENDPOINTS["orders"], json=payload)
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

    def validate(self, ref: Any, request: PlaceOrderRequest) -> str | None:
        if request.order_type == OrderType.LIMIT and request.price <= 0:
            return "Limit order requires price > 0"
        if request.order_type == OrderType.STOP_LOSS and (
            request.price <= 0 or request.trigger_price <= 0
        ):
            return "Stop-Loss (Limit) order requires price > 0 and trigger_price > 0"
        if (
            request.order_type == OrderType.STOP_LOSS_MARKET
            and request.trigger_price <= 0
        ):
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

        if (
            segment in self._derivative_segments
            and request.product_type == ProductType.DELIVERY
        ):
            return (
                f"Product type DELIVERY is not valid for {segment}. "
                "Use INTRADAY or MARGIN for derivatives."
            )

        tick = getattr(ref, "tick_size", None)
        if request.price > 0 and tick is not None and tick > 0:
            if not is_tick_aligned(request.price, Decimal(str(tick))):
                return (
                    f"Price {request.price} is not aligned to tick size {tick} "
                    f"for {ref.symbol}"
                )

        pt_val = request.product_type.value
        if segment in self._derivative_segments and pt_val in self._equity_only_products:
            return (
                f"Product type {pt_val} is not valid for {segment}. "
                "Use INTRADAY or MARGIN for derivatives."
            )
        return None
