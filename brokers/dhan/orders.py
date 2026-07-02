"""Orders adapter — place, modify, cancel, orderbook, tradebook.

Production-hardened with:
- Pre-trade validation (lot size, product type, quantity, price)
- Idempotency cache (prevents duplicate orders on retry)
- Structured logging (full audit trail)
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any

from brokers.common.dtos import BrokerOrderPayload
from brokers.dhan.exceptions import DhanError, OrderError
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, DhanInstrumentRef, coerce_identity_provider
from brokers.dhan.invariants import assert_dhan_payload
from brokers.dhan.segments import DEFAULT_SEGMENT, EXCHANGE_TO_SEGMENT, segment_to_exchange
from config.endpoints import Dhan
from domain import (
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    ProductType,
    Trade,
    Validity,
)
from domain import (
    Side as OrderSide,
)
from domain.field_mapping import DefaultFieldMapping
from domain.ports.risk_manager import RiskManagerPort
from domain.symbols import normalize_exchange
from infrastructure.event_bus import DomainEvent, EventBus

logger = logging.getLogger(__name__)

# Module-level field mapping instance (reused for all order parsing)
_DHAN_MAPPING = DefaultFieldMapping()

# Segments where only INTRADAY and MARGIN product types are allowed
_DERIVATIVE_SEGMENTS = frozenset(
    {
        "NSE_FNO",
        "BSE_FNO",
        "MCX_COMM",
        "NSE_CURRENCY",
        "BSE_CURRENCY",
    }
)

# Product types NOT allowed for derivatives
_EQUITY_ONLY_PRODUCTS = frozenset({"CNC", "MTF"})


class IdempotencyCache:
    """Prevents duplicate order placement by caching responses keyed on correlation_id.

    Thread-safe: all cache mutations and lookups are guarded by a reentrant lock.
    The ``lock`` context manager can be used to build larger atomic critical
    sections (e.g. check-then-act order placement).
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self._cache: dict[str, tuple[float, Order]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.RLock()

    @contextmanager
    def lock(self, _key: str):
        """Acquire the cache lock for an atomic check-then-act sequence."""
        with self._lock:
            yield self

    def get(self, key: str) -> Order | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, order = entry
            if time.time() - ts > self._ttl:
                del self._cache[key]
                return None
            return order

    def put(self, key: str, order: Order) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[key] = (time.time(), order)


class OrdersAdapter:
    def __init__(
        self,
        client: DhanHttpClient,
        identity: DhanIdentityProvider | object,
        idempotency_cache: IdempotencyCache | None = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManagerPort | None = None,
        allow_live_orders: bool = False,
        allow_duck_identity: bool = False,
    ):
        self._client = client
        # Accept either a DhanIdentityProvider (production path) or a raw
        # SymbolResolver (legacy test fixtures). ``coerce_identity_provider``
        # guarantees the adapter holds a provider-shaped object so the
        # Dhan-internal contract is enforced end-to-end.
        self._identity = coerce_identity_provider(identity, allow_duck=allow_duck_identity)
        # Backward-compat shim for tests/code that still asks the adapter
        # for its underlying resolver. The resolver is owned by the
        # DhanIdentityProvider; this property delegates to it.
        self._resolver = self._identity.resolver
        self._idempotency = idempotency_cache or IdempotencyCache()
        self._event_bus = event_bus
        self._risk_manager = risk_manager
        self._allow_live_orders = allow_live_orders

    # ── Validation ────────────────────────────────────────────────────

    def validate_order(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        order_type: str | OrderType,
        product_type: str | ProductType,
        price: Decimal | None = None,
    ) -> list[str]:
        """Validate an order before submission. Returns list of error strings (empty = valid)."""
        errors: list[str] = []

        if quantity <= 0:
            errors.append(f"Quantity must be positive, got {quantity}")

        ot_val = order_type.value if isinstance(order_type, OrderType) else str(order_type).upper()
        pt_val = (
            product_type.value
            if isinstance(product_type, ProductType)
            else str(product_type).upper()
        )

        if ot_val in ("LIMIT", "STOP_LOSS") and (price is None or price <= 0):
            errors.append(f"LIMIT/SL orders require price > 0, got {price}")

        # Resolve instrument for lot size and segment checks
        try:
            inst = self._identity.resolver.resolve(symbol, exchange)
        except (DhanError, ValueError, KeyError) as exc:
            logger.warning(
                "instrument_resolve_failed",
                extra={"symbol": symbol, "exchange": exchange, "error": str(exc)},
            )
            errors.append(f"Instrument not found: {symbol} on {exchange}")
            return errors

        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, DEFAULT_SEGMENT)

        # Lot size check for derivatives
        if segment in _DERIVATIVE_SEGMENTS and inst.lot_size > 1 and quantity % inst.lot_size != 0:
            errors.append(
                f"Quantity {quantity} is not a multiple of lot size {inst.lot_size} "
                f"for {symbol} on {inst.exchange.value}"
            )

        # Tick size alignment check for priced orders
        if price is not None and price > 0:
            tick = getattr(inst, "tick_size", None)
            if tick is not None and tick > 0:
                from domain.utils.price import is_tick_aligned

                if not is_tick_aligned(price, tick):
                    errors.append(
                        f"Price {price} is not aligned to tick size {tick} "
                        f"for {symbol}"
                    )

        # Product type x segment check
        if segment in _DERIVATIVE_SEGMENTS and pt_val in _EQUITY_ONLY_PRODUCTS:
            errors.append(
                f"Product type {pt_val} is not valid for {segment}. "
                f"Use INTRADAY or MARGIN for derivatives."
            )

        return errors

    def validate_order_warnings(
        self,
        quantity: int,
        price: Decimal | None = None,
    ) -> list[str]:
        """Return non-blocking warnings. High notional is the main check."""
        warnings: list[str] = []
        if price and price > 0:
            notional = Decimal(str(quantity)) * price
            if notional > Decimal("50000"):
                warnings.append(f"High notional: ₹{notional:,.0f} exceeds ₹50,000 threshold")
        return warnings

    # ── Order lifecycle ───────────────────────────────────────────────

    def place_order(self, request: BrokerOrderPayload) -> Order:
        """Place an order via the Dhan API.

        Args:
            request: :class:`BrokerOrderPayload` with canonical order fields
                     plus broker-transport metadata (exchange_segment,
                     transport_only, etc.).

        Returns:
            The placed :class:`Order` domain object.

        Raises:
            OrderError: On validation failure or risk check denial.

        .. note::
            **Exception policy divergence** (F-20, P1): this adapter raises
            ``OrderError`` on validation/risk failures, while
            :class:`~brokers.upstox.orders.order_command_adapter.UpstoxOrderCommandAdapter`
            returns :class:`~brokers.common.core.domain.OrderResponse.fail`.
            The gateway layer (:class:`~brokers.dhan.gateway.DhanGateway`)
            catches ``OrderError`` and converts it to ``OrderResponse.fail()``,
            so callers using the gateway see consistent error handling.
        """
        if not self._allow_live_orders:
            raise OrderError("Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable.")

        correlation_id = request.correlation_id
        symbol = request.symbol or ""
        exchange = request.exchange or "NSE"
        side = request.transaction_type
        quantity = request.quantity
        order_type = request.order_type
        price = request.price
        trigger_price = request.trigger_price
        product_type = request.product_type
        validity = request.validity

        # Always generate a correlation id so every placement is idempotent.
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Atomic check-then-act: one and only one thread posts for this id.
        with self._idempotency.lock(correlation_id):
            cached = self._idempotency.get(correlation_id)
            if cached is not None:
                logger.info(
                    "idempotency_hit",
                    extra={"correlation_id": correlation_id, "order_id": cached.order_id},
                )
                return cached

            # Validation
            errors = self.validate_order(
                symbol, exchange, quantity, order_type, product_type, price
            )
            if errors:
                msg = "; ".join(errors)
                logger.warning(
                    "order_validation_failed", extra={"symbol": symbol, "errors": errors}
                )
                raise OrderError(f"Order validation failed: {msg}")

            warnings = self.validate_order_warnings(quantity, price)
            for w in warnings:
                logger.warning("order_warning", extra={"symbol": symbol, "warning": w})

            # Resolve instrument via the identity provider so the carrier
            # (DhanInstrumentRef) is the only thing that can flow into
            # the payload builder. The provider enforces the Dhan-only
            # contract; any non-Dhan segment or non-digit security_id
            # raises DhanIdentityError before we ever call _client.post.
            # The expected_segment hint maps the user-supplied exchange
            # string to a Dhan segment so the index-fallback is rejected
            # for derivatives queries (PR-C.4).
            from brokers.dhan.segments import EXCHANGE_TO_SEGMENT

            ref = self._identity.resolve_ref(
                symbol,
                exchange,
                expected_segment=EXCHANGE_TO_SEGMENT.get(normalize_exchange(exchange)),
            )
            segment = ref.exchange_segment
            side_val, ot_val, pt_val, v_val = self._canonicalize_order_enums(
                side,
                order_type,
                product_type,
                validity,
            )

            # Pre-trade risk check is always enforced at the broker boundary.
            if self._risk_manager is not None:
                preview = Order(
                    order_id="",
                    symbol=symbol,
                    exchange=ref.exchange.value,
                    side=OrderSide(side_val),
                    order_type=OrderType(ot_val),
                    quantity=quantity,
                    price=price if price and price > 0 else Decimal("0"),
                    trigger_price=trigger_price
                    if trigger_price and trigger_price > 0
                    else Decimal("0"),
                    product_type=ProductType(pt_val),
                    validity=Validity(v_val),
                )
                risk_result = self._risk_manager.check_order(preview)
                if not risk_result.allowed:
                    raise OrderError(f"Risk check failed: {risk_result.reason}")

            payload = self._build_order_payload(
                ref,
                segment,
                side_val,
                ot_val,
                pt_val,
                v_val,
                quantity,
                price,
                trigger_price,
                correlation_id,
            )
            # PR-B: defence-in-depth. The carrier already enforced the
            # Dhan-internal contract, but a future change could build a
            # payload from non-carrier sources. Re-verify at the boundary.
            assert_dhan_payload(payload, context="orders.place_order")

            data = self._client.post("/orders", json=payload)

            order = self._build_placed_order(
                data,
                symbol,
                ref.exchange,
                side_val,
                ot_val,
                pt_val,
                v_val,
                quantity,
                price,
                trigger_price,
                correlation_id,
            )

            logger.info(
                "order_placed",
                extra={
                    "order_id": order.order_id,
                    "symbol": symbol,
                    "side": side_val,
                    "quantity": quantity,
                    "order_type": ot_val,
                    "price": str(price or 0),
                    "product_type": pt_val,
                    "exchange": ref.exchange.value,
                },
            )

            self._idempotency.put(correlation_id, order)
            self._publish("ORDER_PLACED", order)
            return order

    def modify_order(self, order_id: str, **changes: Any) -> Order:
        """Modify an existing order via PUT /orders/{order_id}.

        The Dhan API returns a dict with updated order fields on success,
        or an error dict with ``errorCode``/``errorMessage`` on failure.

        Returns:
            Updated :class:`Order` parsed from the API response.

        Raises:
            OrderError: If the API returns an error or response cannot be parsed.
        """
        # Safety guard: prevent live order modifications if disabled
        if not self._allow_live_orders:
            raise OrderError("Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable.")

        payload = {k: v for k, v in changes.items() if v is not None}
        result = self._client.put(f"/orders/{order_id}", json=payload)

        if not isinstance(result, dict):
            raise OrderError(f"Unexpected modify response: {result}")

        error_code = result.get("errorCode")
        if error_code:
            error_msg = result.get("errorMessage", "modify_order_failed")
            raise OrderError(f"Modify order failed [{error_code}]: {error_msg}")

        logger.info("order_modified", extra={"order_id": order_id, "changes": list(changes.keys())})

        # Parse the API response into a canonical Order.
        # The Dhan modify endpoint returns the updated order details.
        try:
            return Order.from_broker_dict(result, field_mapping=_DHAN_MAPPING)
        except (DhanError, ValueError) as exc:
            logger.warning(
                "modify_order_parse_fallback", extra={"order_id": order_id, "error": str(exc)}
            )
            # Fallback: if the response doesn't have full order details,
            # construct from the payload + order_id
            return Order(
                order_id=order_id,
                symbol=str(result.get("tradingSymbol", changes.get("symbol", ""))),
                exchange=str(result.get("exchangeSegment", changes.get("exchange", "NSE"))),
                side=OrderSide(
                    str(result.get("transactionType", changes.get("side", "BUY"))).upper()
                ),
                order_type=OrderType(
                    _DHAN_MAPPING.map_order_type(result)
                    if result.get("orderType")
                    else str(changes.get("order_type", "MARKET")).upper()
                ),
                quantity=int(result.get("quantity", changes.get("quantity", 0))),
                price=Decimal(str(result.get("price", changes.get("price", 0)))),
                trigger_price=Decimal(
                    str(result.get("triggerPrice", changes.get("trigger_price", 0)))
                ),
                status=OrderStatus(
                    _DHAN_MAPPING.map_status(result)
                    if result.get("orderStatus")
                    else str(changes.get("status", "OPEN")).upper()
                ),
            )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order via DELETE /orders/{order_id}.

        The Dhan cancel endpoint returns a body whose ``status`` field
        is ``"success"`` on cancellation, or an error payload with a
        non-empty ``errorCode`` / ``errorMessage`` on failure. The
        previous implementation treated *any* dict response as success
        — that was a P0 bug because the broker also returns dicts on
        authentication errors and on unknown-order errors.

        Returns:
            :class:`OrderResponse` with ``success`` set from the
            broker's ``status`` field (or inferred from
            ``errorCode`` being absent).
        """
        from domain.entities import OrderResponse

        # Safety guard: prevent live order cancellations if disabled
        if not self._allow_live_orders:
            raise OrderError("Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable.")

        try:
            data = self._client.delete(f"/orders/{order_id}")
        except Exception as exc:  # pragma: no cover - network path
            logger.warning(
                "order_cancel_network_error",
                extra={"order_id": order_id, "error": str(exc)},
            )
            return OrderResponse.fail(
                message=f"network error: {exc}",
                error_code="BRO_ERR_CONNECTION_FAILED",
            )

        if not isinstance(data, dict):
            return OrderResponse.fail(
                message="malformed broker response (not a dict)",
                raw_payload={"raw": repr(data)},
            )

        broker_status = str(data.get("status", "")).lower()
        # Dhan uses both "success" and "ok"; both mean "cancelled".
        success = broker_status in {"success", "ok"}
        if success:
            return OrderResponse.ok(
                order_id=order_id,
                message=str(data.get("message", "Order cancelled")),
                status=OrderStatus.CANCELLED,
                raw_payload=data,
            )
        # Failure path
        return OrderResponse.fail(
            message=str(data.get("errorMessage") or data.get("message") or "Cancel failed"),
            error_code=str(data.get("errorCode", "")),
            raw_payload=data,
        )

    def cancel_all_orders(self) -> list[tuple[str, bool]]:
        # Safety guard: prevent live order cancellations if disabled
        if not self._allow_live_orders:
            raise OrderError("Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable.")

        data = self._client.delete("/orders")
        items = data.get("data", []) if isinstance(data, dict) else []
        result = [
            (str(i.get("orderId", i)), True) for i in (items if isinstance(items, list) else [])
        ]
        logger.info("all_orders_cancelled", extra={"count": len(result)})
        return result

    def get_order(self, order_id: str) -> Order:
        data = self._client.get(f"/orders/{order_id}")
        raw = data.get("data", data) if isinstance(data, dict) else data
        return self._parse_order(raw if isinstance(raw, dict) else {})

    def get_orderbook(self) -> list[Order]:
        data = self._client.get("/orders")
        items = data.get("data", []) if isinstance(data, dict) else []
        orders = [self._parse_order(i) for i in (items if isinstance(items, list) else [])]
        logger.info("orderbook_fetched", extra={"count": len(orders)})
        return orders

    def get_trade_book(self) -> list[Trade]:
        data = self._client.get("/trades")
        items = data.get("data", []) if isinstance(data, dict) else []
        trades = [self._parse_trade(item) for item in (items if isinstance(items, list) else [])]
        logger.info("tradebook_fetched", extra={"count": len(trades)})
        return trades

    def get_order_status(self, order_id: str) -> OrderStatus:
        order = self.get_order(order_id)
        return order.status

    def kill_switch(self, enable: bool) -> bool:
        # Safety guard: prevent kill switch activation if live orders disabled
        if not self._allow_live_orders:
            raise OrderError("Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable.")

        action = "ACTIVATE" if enable else "DEACTIVATE"
        data = self._client.post(f"/killswitch?killSwitchStatus={action}", json={})
        success = isinstance(data, dict) and data.get("status", "").lower() == "success"
        logger.info("kill_switch", extra={"action": action, "success": success})
        return success

    def _publish(self, event_type: str, order: Order) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(
            DomainEvent.now(
                event_type,
                {"order": order},
                symbol=order.symbol,
                source="DhanOrdersAdapter",
            )
        )

    # ── Shared order-placement helpers ────────────────────────────────

    @staticmethod
    def _canonicalize_order_enums(
        side: str | OrderSide,
        order_type: str | OrderType,
        product_type: str | ProductType,
        validity: str | Validity,
    ) -> tuple[str, str, str, str]:
        """Canonicalize order enum/mixed values to uppercase strings."""
        sv = side.value if isinstance(side, OrderSide) else str(side).upper()
        ot = order_type.value if isinstance(order_type, OrderType) else str(order_type).upper()
        pt = (
            product_type.value
            if isinstance(product_type, ProductType)
            else str(product_type).upper()
        )
        vl = validity.value if isinstance(validity, Validity) else str(validity).upper()
        return sv, ot, pt, vl

    def _build_order_payload(
        self,
        ref: DhanInstrumentRef,
        segment: str,
        side_val: str,
        ot_val: str,
        pt_val: str,
        v_val: str,
        quantity: int,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Build the Dhan order placement payload dict.

        The *ref* argument is a :class:`DhanInstrumentRef`; the carrier
        is the only thing that can flow into a Dhan HTTP body, and
        ``DhanInstrumentRef.__post_init__`` has already enforced the
        Dhan-internal contract (segment ∈ Dhan's set, security_id is
        a positive digit string).
        """
        payload: dict[str, Any] = {
            "dhanClientId": self._client.client_id,
            "securityId": ref.security_id_str(),
            "exchangeSegment": segment,
            "transactionType": side_val,
            "orderType": ot_val,
            "productType": pt_val,
            "validity": v_val,
            "quantity": quantity,
        }
        if price and price > 0:
            from domain.utils.price import to_wire_float

            payload["price"] = to_wire_float(price)
        if trigger_price and trigger_price > 0:
            from domain.utils.price import to_wire_float

            payload["triggerPrice"] = to_wire_float(trigger_price)
        if correlation_id:
            payload["correlationId"] = correlation_id
        return payload

    @staticmethod
    def _build_placed_order(
        data: dict,
        symbol: str,
        exchange: Any,
        side_val: str,
        ot_val: str,
        pt_val: str,
        v_val: str,
        quantity: int,
        price: Decimal | None,
        trigger_price: Decimal | None,
        correlation_id: str,
    ) -> Order:
        """Build an Order domain object from a place-order API response."""
        order_id = str(data.get("data", {}).get("orderId") or data.get("orderId") or "")
        return Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=OrderSide(side_val),
            order_type=OrderType(ot_val),
            quantity=quantity,
            status=OrderStatus.OPEN,
            price=price if price and price > 0 else Decimal("0"),
            trigger_price=trigger_price if trigger_price and trigger_price > 0 else Decimal("0"),
            product_type=ProductType(pt_val),
            validity=Validity(v_val),
            correlation_id=correlation_id,
        )

    @staticmethod
    def _parse_order(raw: dict) -> Order:
        return Order.from_broker_dict(
            raw, field_mapping=_DHAN_MAPPING, exchange_resolver=segment_to_exchange
        )

    def place_slice_order(self, symbol: str, exchange: str, **kwargs) -> Order:
        """Place a slice order (automatically splits large orders).

        Uses POST /orders/slicing endpoint instead of POST /orders.
        Same payload structure as regular place_order.
        """
        # Safety guard: prevent live slice orders if disabled
        if not self._allow_live_orders:
            raise OrderError("Live orders are disabled. Set DHAN_ALLOW_LIVE_ORDERS=1 to enable.")

        side = kwargs.get("side", "BUY")
        quantity: int = kwargs["quantity"]
        order_type = kwargs.get("order_type", "MARKET")
        product_type = kwargs.get("product_type", "INTRADAY")
        price: Decimal = kwargs.get("price", Decimal("0"))
        trigger_price: Decimal = kwargs.get("trigger_price", Decimal("0"))
        validity = kwargs.get("validity", "DAY")
        correlation_id: str | None = kwargs.get("correlation_id")

        # Resolve instrument via the identity provider so the carrier
        # (DhanInstrumentRef) is the only thing that can flow into
        # the payload builder. Slice orders are broker-managed and have
        # no idempotency/risk check; the identity provider is the
        # single place that enforces the Dhan-internal contract.
        ref = self._identity.resolve_ref(symbol, exchange)
        segment = ref.exchange_segment
        side_val, ot_val, pt_val, v_val = self._canonicalize_order_enums(
            side,
            order_type,
            product_type,
            validity,
        )

        # Pre-trade validation (no idempotency/risk — slice orders are broker-managed).
        self.validate_order(
            symbol=symbol,
            exchange=exchange,
            quantity=quantity,
            order_type=ot_val,
            product_type=pt_val,
            price=price if price > 0 else None,
        )

        payload = self._build_order_payload(
            ref,
            segment,
            side_val,
            ot_val,
            pt_val,
            v_val,
            quantity,
            price,
            trigger_price,
            correlation_id,
        )
        # PR-B: defence-in-depth invariant assertion.
        assert_dhan_payload(payload, context="orders.place_slice_order")

        data = self._client.post(Dhan.SLICE_ORDER, json=payload)
        order_data = data.get("data", data)
        order = self._parse_order(order_data)

        logger.info(
            "slice_order_placed",
            extra={
                "order_id": order.order_id,
                "symbol": symbol,
                "exchange": exchange,
                "side": side_val,
                "quantity": quantity,
            },
        )

        self._publish("ORDER_PLACED", order)
        return order

    def get_trade_history(self, from_date: str, to_date: str, page: int = 0) -> list[Trade]:
        """Get trade history for a date range.

        Args:
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format
            page: Page number for pagination (default 0)

        Returns:
            List of Trade objects

        Raises:
            ValueError: If date format is invalid
        """
        import re

        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if not date_pattern.match(from_date):
            raise ValueError(f"Invalid from_date format: {from_date}. Expected YYYY-MM-DD")
        if not date_pattern.match(to_date):
            raise ValueError(f"Invalid to_date format: {to_date}. Expected YYYY-MM-DD")

        data = self._client.get(f"/trades/{from_date}/{to_date}/{page}")
        items = data.get("data", []) if isinstance(data, dict) else []
        trades = [self._parse_trade(item) for item in (items if isinstance(items, list) else [])]

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

    @staticmethod
    def _parse_trade(raw: dict) -> Trade:
        """Parse trade from API response."""
        return Trade(
            trade_id=str(raw.get("tradeId", raw.get("id", ""))),
            order_id=str(raw.get("orderId", "")),
            symbol=raw.get("tradingSymbol", raw.get("symbol", "")),                exchange=segment_to_exchange(raw.get("exchangeSegment", DEFAULT_SEGMENT)),
            side=OrderSide(raw.get("transactionType", "BUY")),
            quantity=raw.get("tradedQty", raw.get("quantity", 0)),
            price=Decimal(str(raw.get("tradedPrice", raw.get("price", 0)))),
            timestamp=_parse_timestamp(raw.get("tradedTime", raw.get("createdAt"))),
        )





def _opt_dec(val) -> Decimal | None:
    if val in (None, ""):
        return None
    return Decimal(str(val))


def _parse_timestamp(val: Any) -> datetime | None:
    """Parse a timestamp from Dhan API response to datetime.

    Dhan returns ISO-8601 strings like '2026-06-30T10:15:30+05:30'.
    Returns None if the value is missing or unparseable.
    """
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None
