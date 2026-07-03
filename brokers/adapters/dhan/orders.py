"""Dhan orders adapter — place, cancel, modify, query orders."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from brokers.adapters.dhan.config import (
    DERIVATIVE_SEGMENTS,
    ENDPOINTS,
    EQUITY_ONLY_PRODUCTS,
    ORDER_TYPE_MAP,
    PRODUCT_TYPE_MAP,
    SIDE_MAP,
    VALIDITY_MAP,
)
from brokers.adapters.dhan.exceptions import DhanOrderError
from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.idempotency import DhanIdempotencyCache
from brokers.adapters.dhan.invariants import assert_valid_dhan_payload
from brokers.adapters.dhan.mapper import map_order, map_order_response
from brokers.adapters.dhan.segments import resolve_segment
from brokers.adapters.dhan.use_cases.place_order import PlaceOrderRequest, PlaceOrderUseCase
from brokers.domain import Order, OrderResponse, Trade
from brokers.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from brokers.domain.events import DomainEvent
from brokers.domain.exceptions import InstrumentNotFoundError
from brokers.infrastructure.correlation import get_current_correlation_id
from brokers.infrastructure.event_bus import EventBus
from brokers.ports.risk_manager import RiskManagerPort
from brokers.utils.price import to_wire_float

logger = logging.getLogger(__name__)


class DhanOrders:
    def __init__(
        self,
        client: DhanHttpClient,
        resolver: DhanInstrumentResolver,
        allow_live_orders: bool = True,
        idempotency_cache: DhanIdempotencyCache[OrderResponse] | None = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManagerPort | None = None,
    ):
        self._client = client
        self._resolver = resolver
        self._allow_live_orders = allow_live_orders
        self._idempotency = idempotency_cache or DhanIdempotencyCache()
        self._event_bus = event_bus
        self._risk_manager = risk_manager
        self._place_order_uc = PlaceOrderUseCase(
            client,
            resolver,
            idempotency=self._idempotency,
            allow_live_orders=allow_live_orders,
            risk_manager=risk_manager,
            derivative_segments=DERIVATIVE_SEGMENTS,
            equity_only_products=EQUITY_ONLY_PRODUCTS,
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )

    @property
    def idempotency_cache(self) -> DhanIdempotencyCache[OrderResponse]:
        """Expose idempotency cache for contract tests and diagnostics."""
        return self._idempotency

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
    ) -> OrderResponse:
        request = PlaceOrderRequest(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )
        response, placed = self._place_order_uc.execute(request)
        if placed is not None:
            self._publish("ORDER_PLACED", placed)
        return response

    def _publish(self, event_type: str, order: Order) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(
            DomainEvent.now(
                event_type,
                {"order": order},
                symbol=order.symbol,
                source="DhanOrders",
            )
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        if not self._allow_live_orders:
            logger.warning(
                "Live orders disabled — rejecting cancel_order for %s", order_id
            )
            return OrderResponse.live_orders_disabled()

        endpoint = ENDPOINTS["cancel_order"].format(order_id=order_id)
        try:
            data = self._client.delete(endpoint)
        except Exception as exc:
            logger.warning(
                "order_cancel_network_error",
                extra={"order_id": order_id, "error": str(exc)},
            )
            return OrderResponse.fail(
                f"network error: {exc}",
                error_code="BRO_ERR_CONNECTION_FAILED",
            )

        if not isinstance(data, dict):
            return OrderResponse.fail(
                "malformed broker response (not a dict)",
                error_code="BRO_ERR_MALFORMED_RESPONSE",
            )

        broker_status = str(data.get("status", "")).lower()
        success = broker_status in {"success", "ok"}
        if not success:
            return OrderResponse.fail(
                str(data.get("errorMessage") or data.get("message") or "Cancel failed"),
                error_code=str(data.get("errorCode", "CANCEL_FAILED")),
            )

        existing = self.get_order(order_id)
        if existing and existing.status == OrderStatus.FILLED:
            logger.warning(
                "Post-cancel race: order %s already FILLED before cancel took effect",
                order_id,
            )
            return OrderResponse(
                order_id=order_id,
                success=False,
                message="Order was already FILLED (post-cancel race)",
                error_code="ORDER_ALREADY_FILLED",
            )

        return OrderResponse(
            order_id=order_id,
            success=True,
            message=str(data.get("message", "Order cancelled")),
            status=OrderStatus.CANCELLED,
        )

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> OrderResponse:
        if not self._allow_live_orders:
            return OrderResponse.live_orders_disabled()

        endpoint = ENDPOINTS.get("modify_order", "").format(order_id=order_id)
        payload: dict = {}
        if quantity is not None:
            payload["quantity"] = quantity
        if price is not None:
            payload["price"] = to_wire_float(price)
        if order_type is not None:
            payload["orderType"] = ORDER_TYPE_MAP.get(order_type.value, 1)
        if validity is not None:
            payload["validity"] = VALIDITY_MAP.get(validity.value, "DAY")

        data = self._client.post(endpoint, json=payload)
        return map_order_response(data)

    def get_order(self, order_id: str) -> Order | None:
        endpoint = ENDPOINTS["order_by_id"].format(order_id=order_id)
        data = self._client.get(endpoint)
        if isinstance(data, dict) and "data" in data:
            return map_order(data["data"])
        if isinstance(data, dict) and "orderId" in data:
            return map_order(data)
        return None

    def get_orderbook(self) -> list[Order]:
        data = self._client.get(ENDPOINTS["orderbook"])
        if isinstance(data, list):
            orders_data = data
        elif isinstance(data, dict):
            orders_data = data.get("data", data)
            if not isinstance(orders_data, list):
                orders_data = [orders_data]
        else:
            orders_data = []

        return [map_order(o) for o in orders_data if isinstance(o, dict)]

    def get_trade_book(self) -> list[Trade]:
        """Protocol-compatibility alias. Prefer trades()."""
        return self.trades()

    def trades(self) -> list[Trade]:
        from brokers.adapters.dhan.mapper import map_trade

        data = self._client.get(ENDPOINTS["tradebook"])
        items = data.get("data", []) if isinstance(data, dict) else []
        if isinstance(items, list):
            return [map_trade(t) for t in items]
        return []

    def get_trade_history(
        self, from_date: str, to_date: str, page: int = 0
    ) -> list[Trade]:
        from brokers.adapters.dhan.mapper import map_trade

        endpoint = ENDPOINTS["trade_history"].format(
            from_date=from_date, to_date=to_date, page=page
        )
        data = self._client.get(endpoint)
        items = data.get("data", []) if isinstance(data, dict) else []
        trades = [map_trade(t) for t in items] if isinstance(items, list) else []
        logger.info(
            "trade_history_fetched",
            extra={
                "from_date": from_date,
                "to_date": to_date,
                "page": page,
                "count": len(trades),
            },
        )
        return trades

    def kill_switch(self, enable: bool) -> bool:
        """Activate or deactivate the broker kill switch."""
        if not self._allow_live_orders:
            raise DhanOrderError(
                "Live orders are disabled. Set allow_live_orders=True to enable."
            )
        action = "ACTIVATE" if enable else "DEACTIVATE"
        endpoint = f"{ENDPOINTS['kill_switch']}?killSwitchStatus={action}"
        data = self._client.post(endpoint, json={})
        success = isinstance(data, dict) and str(data.get("status", "")).lower() == "success"
        logger.info("kill_switch", extra={"action": action, "success": success})
        return success

    def place_slice_order(
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
    ) -> OrderResponse:
        """Place a slice order (broker-managed quantity splitting)."""
        if not self._allow_live_orders:
            raise DhanOrderError(
                "Live orders are disabled. Set allow_live_orders=True to enable."
            )

        try:
            ref = self._resolver.resolve(
                symbol,
                exchange,
                expected_segment=resolve_segment(exchange),
            )
        except InstrumentNotFoundError as exc:
            return OrderResponse.fail(str(exc), error_code="INSTRUMENT_NOT_FOUND")

        request = PlaceOrderRequest(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )
        validation_error = self._place_order_uc.validate(ref, request)
        if validation_error:
            return OrderResponse.fail(
                f"Order validation failed: {validation_error}",
                error_code="VALIDATION_FAILED",
            )

        cid = correlation_id or get_current_correlation_id() or str(uuid.uuid4())
        payload = {
            "dhanClientId": self._client.client_id,
            "transactionType": SIDE_MAP.get(side.value, 1),
            "exchangeSegment": ref.exchange_segment,
            "securityId": ref.security_id_str(),
            "quantity": quantity,
            "orderType": ORDER_TYPE_MAP.get(order_type.value, 1),
            "productType": PRODUCT_TYPE_MAP.get(product_type.value, "INTRADAY"),
            "validity": VALIDITY_MAP.get(validity.value, "DAY"),
            "price": to_wire_float(price) if price > 0 else 0.0,
            "triggerPrice": to_wire_float(trigger_price) if trigger_price > 0 else 0.0,
            "correlationId": cid,
        }
        assert_valid_dhan_payload(payload, context="orders.place_slice_order")
        data = self._client.post(ENDPOINTS["slice_order"], json=payload)
        response = map_order_response(data)
        if response.success:
            logger.info(
                "slice_order_placed",
                extra={
                    "order_id": response.order_id,
                    "symbol": symbol,
                    "correlation_id": cid,
                },
            )
        return response
