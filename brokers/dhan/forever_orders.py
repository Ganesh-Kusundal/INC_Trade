"""Forever Orders adapter — Single GTT and OCO (One Cancels Other) orders."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.dhan.domain import ForeverOrder, ForeverOrderRequest
from brokers.dhan.exceptions import ForeverOrderError
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, coerce_identity_provider
from brokers.dhan.invariants import assert_dhan_payload
from domain.entities import OrderResponse
from domain.utils.price import to_wire_float

logger = logging.getLogger(__name__)


class ForeverOrdersAdapter:
    """Adapter for Dhan Forever Orders API.

    Forever Orders are GTT (Good Till Trigger) orders that remain active
    until triggered or cancelled. Supports SINGLE and OCO modes.
    """

    def __init__(self, client: DhanHttpClient, identity: DhanIdentityProvider | object):
        self._client = client
        self._identity = coerce_identity_provider(identity)
        self._resolver = self._identity.resolver

    def place_forever_order(self, request: ForeverOrderRequest) -> ForeverOrder:
        """Place a forever order (SINGLE or OCO).

        Args:
            request: ForeverOrderRequest with order details

        Returns:
            ForeverOrder with created order information

        Raises:
            ValueError: If validation fails (OCO requires additional fields)
            ForeverOrderError: If API call fails
        """
        # Validate request
        errors = self._validate_forever_order(request)
        if errors:
            msg = "; ".join(errors)
            logger.warning(
                "forever_order_validation_failed",
                extra={
                    "symbol": request.symbol,
                    "order_flag": request.order_flag,
                    "errors": errors,
                },
            )
            raise ValueError(f"Forever order validation failed: {msg}")

        # Resolve instrument via the identity provider. The carrier
        # (DhanInstrumentRef) is the only thing that can flow into the
        # payload builder; the provider enforces the Dhan-internal
        # contract.
        ref = self._identity.resolve_ref(request.symbol, request.exchange)
        segment = ref.exchange_segment

        # Build API payload
        payload = {
            "dhanClientId": self._client.client_id,
            "exchangeSegment": segment,
            "securityId": ref.security_id_str(),
            "orderFlag": request.order_flag,
            "transactionType": request.transaction_type,
            "productType": request.product_type,
            "orderType": request.order_type,
            "validity": request.validity,
            "quantity": request.quantity,
            "price": to_wire_float(request.price),
            "triggerPrice": to_wire_float(request.trigger_price),
        }

        # OCO-specific fields
        if request.order_flag == "OCO":
            if request.price1 is not None:
                payload["price1"] = to_wire_float(request.price1)
            if request.trigger_price1 is not None:
                payload["triggerPrice1"] = to_wire_float(request.trigger_price1)
            if request.quantity1 is not None:
                payload["quantity1"] = request.quantity1

        if request.correlation_id:
            payload["correlationId"] = request.correlation_id

        # PR-B: defence-in-depth invariant assertion.
        assert_dhan_payload(payload, context="forever_orders.place_forever_order")

        # Call API
        try:
            data = self._client.post("/forever/orders", json=payload)
        except Exception as exc:
            raise ForeverOrderError(f"Forever order placement failed: {exc}") from exc

        # Parse response
        order_data = data.get("data", data)
        order = self._parse_forever_order(order_data)

        logger.info(
            "forever_order_placed",
            extra={
                "order_id": order.order_id,
                "symbol": request.symbol,
                "order_flag": request.order_flag,
                "transaction_type": request.transaction_type,
            },
        )

        return order

    def modify_forever_order(
        self,
        order_id: str,
        request: ForeverOrderRequest,
    ) -> ForeverOrder:
        """Modify an existing forever order.

        Args:
            order_id: Order ID to modify
            request: ForeverOrderRequest with updated details

        Returns:
            ForeverOrder with updated order information

        Raises:
            ForeverOrderError: If API call fails
        """
        ref = self._identity.resolve_ref(request.symbol, request.exchange)
        segment = ref.exchange_segment

        payload = {
            "exchangeSegment": segment,
            "securityId": ref.security_id_str(),
            "orderFlag": request.order_flag,
            "transactionType": request.transaction_type,
            "productType": request.product_type,
            "orderType": request.order_type,
            "validity": request.validity,
            "quantity": request.quantity,
            "price": to_wire_float(request.price),
            "triggerPrice": to_wire_float(request.trigger_price),
        }

        if request.order_flag == "OCO":
            if request.price1 is not None:
                payload["price1"] = to_wire_float(request.price1)
            if request.trigger_price1 is not None:
                payload["triggerPrice1"] = to_wire_float(request.trigger_price1)
            if request.quantity1 is not None:
                payload["quantity1"] = request.quantity1

        # PR-B: defence-in-depth invariant assertion.
        assert_dhan_payload(payload, context="forever_orders.modify_forever_order")

        try:
            data = self._client.put(f"/forever/orders/{order_id}", json=payload)
        except Exception as exc:
            raise ForeverOrderError(f"Forever order modification failed: {exc}") from exc

        order_data = data.get("data", data)
        order = self._parse_forever_order(order_data)

        logger.info(
            "forever_order_modified",
            extra={
                "order_id": order_id,
            },
        )

        return order

    def cancel_forever_order(self, order_id: str) -> OrderResponse:
        """Cancel a forever order.

        Returns:
            :class:`OrderResponse` indicating success or carrying the
            broker's error code in :attr:`OrderResponse.error_code`.

        Raises:
            ForeverOrderError: only on network/transport errors.
        """
        try:
            data = self._client.delete(f"/forever/orders/{order_id}")
        except Exception as exc:
            raise ForeverOrderError(f"Forever order cancellation failed: {exc}") from exc

        if not isinstance(data, dict):
            return OrderResponse.fail(
                message="malformed broker response (not a dict)",
                raw_payload={"raw": repr(data)},
            )
        broker_status = str(data.get("status", "")).lower()
        success = broker_status in {"success", "ok"}
        if success:
            logger.info(
                "forever_order_cancelled",
                extra={"order_id": order_id, "success": True},
            )
            return OrderResponse.ok(
                order_id=order_id,
                message=str(data.get("message", "Forever order cancelled")),
                raw_payload=data,
            )
        logger.warning(
            "forever_order_cancel_failed",
            extra={
                "order_id": order_id,
                "error_code": data.get("errorCode"),
                "error_message": data.get("errorMessage"),
            },
        )
        return OrderResponse.fail(
            message=str(
                data.get("errorMessage") or data.get("message") or "Forever order cancel failed"
            ),
            error_code=str(data.get("errorCode", "")),
            raw_payload=data,
        )

    def get_all_forever_orders(self) -> list[ForeverOrder]:
        """Get all forever orders.

        Returns:
            List of ForeverOrder objects

        Raises:
            ForeverOrderError: If API call fails
        """
        try:
            data = self._client.get("/forever/all")
        except Exception as exc:
            raise ForeverOrderError(f"Failed to fetch forever orders: {exc}") from exc

        items = data.get("data", []) if isinstance(data, dict) else []
        orders = [
            self._parse_forever_order(item) for item in (items if isinstance(items, list) else [])
        ]

        logger.info("forever_orders_fetched", extra={"count": len(orders)})
        return orders

    def _validate_forever_order(self, request: ForeverOrderRequest) -> list[str]:
        """Validate forever order request. Returns list of errors (empty = valid)."""
        errors = []

        if request.order_flag not in ("SINGLE", "OCO"):
            errors.append(f"Invalid order_flag: {request.order_flag}. Must be SINGLE or OCO")

        # OCO validation
        if request.order_flag == "OCO":
            if request.price1 is None:
                errors.append("OCO orders require price1 (target price)")
            if request.trigger_price1 is None:
                errors.append("OCO orders require trigger_price1 (target trigger)")
            if request.quantity1 is None:
                errors.append("OCO orders require quantity1 (target quantity)")

        if request.price <= 0:
            errors.append(f"Price must be positive, got {request.price}")
        if request.trigger_price <= 0:
            errors.append(f"Trigger price must be positive, got {request.trigger_price}")
        if request.quantity <= 0:
            errors.append(f"Quantity must be positive, got {request.quantity}")

        return errors

    def _parse_forever_order(self, data: dict) -> ForeverOrder:
        """Parse forever order from API response."""
        return ForeverOrder(
            order_id=str(data.get("orderId", "")),
            order_status=data.get("orderStatus", ""),
            order_flag=data.get("orderFlag", ""),
            transaction_type=data.get("transactionType", ""),
            exchange_segment=data.get("exchangeSegment", ""),
            product_type=data.get("productType", ""),
            order_type=data.get("orderType", ""),
            trading_symbol=data.get("tradingSymbol", ""),
            security_id=str(data.get("securityId", "")),
            quantity=data.get("quantity", 0),
            price=Decimal(str(data.get("price", 0))),
            trigger_price=Decimal(str(data.get("triggerPrice", 0))),
            leg_name=data.get("legName"),
            created_time=data.get("createdAt"),
        )
