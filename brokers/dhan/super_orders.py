"""Super Orders adapter — place, modify, cancel super orders with Entry + Target + Stop Loss."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.dhan.domain import SuperOrder, SuperOrderLeg
from brokers.dhan.exceptions import SuperOrderError
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, coerce_identity_provider
from brokers.dhan.invariants import assert_dhan_payload
from domain.entities import OrderResponse
from domain.utils.price import to_wire_float

logger = logging.getLogger(__name__)


class SuperOrdersAdapter:
    """Adapter for Dhan Super Orders API.

    Super Orders allow placing an order with automatic Entry, Target,
    and Stop Loss legs with optional trailing SL.
    """

    def __init__(self, client: DhanHttpClient, identity: DhanIdentityProvider | object):
        self._client = client
        self._identity = coerce_identity_provider(identity)
        self._resolver = self._identity.resolver

    def place_super_order(
        self,
        symbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        price: Decimal,
        target_price: Decimal,
        stop_loss_price: Decimal,
        trailing_jump: Decimal,
        product_type: str = "INTRADAY",
        order_type: str = "LIMIT",
        correlation_id: str | None = None,
    ) -> SuperOrder:
        """Place a super order with Entry + Target + Stop Loss legs.

        Args:
            symbol: Trading symbol
            exchange: Exchange (NSE, NFO, etc.)
            transaction_type: BUY or SELL
            quantity: Order quantity
            price: Entry price
            target_price: Target price (must be > entry for BUY, < entry for SELL)
            stop_loss_price: Stop loss price (must be < entry for BUY, > entry for SELL)
            trailing_jump: Trailing stop loss jump value
            product_type: Product type (INTRADAY, MARGIN, CNC, etc.)
            order_type: Order type (LIMIT, STOP_LOSS, etc.)
            correlation_id: Optional correlation ID for idempotency

        Returns:
            SuperOrder with order details including leg information

        Raises:
            ValueError: If validation fails (target/SL logic)
            SuperOrderError: If API call fails
        """
        # Validate request
        errors = self._validate_super_order(transaction_type, price, target_price, stop_loss_price)
        if errors:
            msg = "; ".join(errors)
            logger.warning(
                "super_order_validation_failed",
                extra={
                    "symbol": symbol,
                    "transaction_type": transaction_type,
                    "errors": errors,
                },
            )
            raise ValueError(f"Super order validation failed: {msg}")

        # Resolve instrument via the identity provider. The carrier
        # (DhanInstrumentRef) is the only thing that can flow into the
        # payload builder; the provider enforces the Dhan-internal
        # contract.
        ref = self._identity.resolve_ref(symbol, exchange)
        segment = ref.exchange_segment

        # Build API payload
        payload = {
            "dhanClientId": self._client.client_id,
            "exchangeSegment": segment,
            "securityId": ref.security_id_str(),
            "transactionType": transaction_type,
            "orderType": order_type,
            "productType": product_type,
            "validity": "DAY",
            "quantity": quantity,
            "price": to_wire_float(price),
            "targetPrice": to_wire_float(target_price),
            "stopLossPrice": to_wire_float(stop_loss_price),
            "trailingJump": to_wire_float(trailing_jump),
        }

        if correlation_id:
            payload["correlationId"] = correlation_id

        # PR-B: defence-in-depth invariant assertion.
        assert_dhan_payload(payload, context="super_orders.place_super_order")

        # Call API
        try:
            data = self._client.post("/super/orders", json=payload)
        except Exception as exc:
            raise SuperOrderError(f"Super order placement failed: {exc}") from exc

        # Parse response
        order_data = data.get("data", data)
        order = self._parse_super_order(order_data)

        logger.info(
            "super_order_placed",
            extra={
                "order_id": order.order_id,
                "symbol": symbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
            },
        )

        return order

    def modify_super_order(
        self,
        order_id: str,
        leg_name: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
    ) -> SuperOrder:
        """Modify a specific leg of a super order.

        Args:
            order_id: Super order ID to modify
            leg_name: Leg to modify (ENTRY_LEG, TARGET_LEG, STOP_LOSS_LEG)
            quantity: New quantity (optional)
            price: New price (optional)
            trigger_price: New trigger price (optional, for SL leg)

        Returns:
            SuperOrder with updated details

        Raises:
            SuperOrderError: If API call fails
        """
        payload: dict = {
            "legName": leg_name,
        }

        if quantity is not None:
            payload["quantity"] = quantity
        if price is not None:
            payload["price"] = to_wire_float(price)
        if trigger_price is not None:
            payload["triggerPrice"] = to_wire_float(trigger_price)

        try:
            data = self._client.put(f"/super/orders/{order_id}", json=payload)
        except Exception as exc:
            raise SuperOrderError(f"Super order modification failed: {exc}") from exc

        order_data = data.get("data", data)
        order = self._parse_super_order(order_data)

        logger.info(
            "super_order_modified",
            extra={
                "order_id": order_id,
                "leg_name": leg_name,
            },
        )

        return order

    def cancel_super_order_leg(self, order_id: str, leg_name: str) -> OrderResponse:
        """Cancel a specific leg of a super order.

        Returns:
            :class:`OrderResponse` carrying the broker's structured
            success/failure. The boolean equivalent is
            ``bool(response)`` / ``response.is_success``.

        Raises:
            SuperOrderError: only on network/transport errors.
        """
        try:
            data = self._client.delete(f"/super/orders/{order_id}/{leg_name}")
        except Exception as exc:
            raise SuperOrderError(f"Super order leg cancellation failed: {exc}") from exc

        if not isinstance(data, dict):
            return OrderResponse.fail(
                message="malformed broker response (not a dict)",
                raw_payload={"raw": repr(data)},
            )
        broker_status = str(data.get("status", "")).lower()
        success = broker_status in {"success", "ok"}
        if success:
            logger.info(
                "super_order_leg_cancelled",
                extra={"order_id": order_id, "leg_name": leg_name, "success": True},
            )
            return OrderResponse.ok(
                order_id=order_id,
                message=str(data.get("message", f"Leg {leg_name} cancelled")),
                raw_payload=data,
            )
        logger.warning(
            "super_order_leg_cancel_failed",
            extra={
                "order_id": order_id,
                "leg_name": leg_name,
                "error_code": data.get("errorCode"),
                "error_message": data.get("errorMessage"),
            },
        )
        return OrderResponse.fail(
            message=str(
                data.get("errorMessage") or data.get("message") or "Super order leg cancel failed"
            ),
            error_code=str(data.get("errorCode", "")),
            raw_payload=data,
        )

    def get_super_orders(self) -> list[SuperOrder]:
        """Get all super orders.

        Returns:
            List of SuperOrder objects

        Raises:
            SuperOrderError: If API call fails
        """
        try:
            data = self._client.get("/super/orders")
        except Exception as exc:
            raise SuperOrderError(f"Failed to fetch super orders: {exc}") from exc

        items = data.get("data", []) if isinstance(data, dict) else []
        orders = [
            self._parse_super_order(item) for item in (items if isinstance(items, list) else [])
        ]

        logger.info("super_orders_fetched", extra={"count": len(orders)})
        return orders

    def _validate_super_order(
        self,
        transaction_type: str,
        price: Decimal,
        target_price: Decimal,
        stop_loss_price: Decimal,
    ) -> list[str]:
        """Validate super order parameters. Returns list of errors (empty = valid)."""
        errors = []

        if transaction_type == "BUY":
            if target_price <= price:
                errors.append(
                    f"For BUY orders, target_price ({target_price}) must be greater than entry price ({price})"
                )
            if stop_loss_price >= price:
                errors.append(
                    f"For BUY orders, stop_loss_price ({stop_loss_price}) must be less than entry price ({price})"
                )
        elif transaction_type == "SELL":
            if target_price >= price:
                errors.append(
                    f"For SELL orders, target_price ({target_price}) must be less than entry price ({price})"
                )
            if stop_loss_price <= price:
                errors.append(
                    f"For SELL orders, stop_loss_price ({stop_loss_price}) must be greater than entry price ({price})"
                )
        else:
            errors.append(f"Invalid transaction_type: {transaction_type}. Must be BUY or SELL")

        if price <= 0:
            errors.append(f"Price must be positive, got {price}")
        if target_price <= 0:
            errors.append(f"Target price must be positive, got {target_price}")
        if stop_loss_price <= 0:
            errors.append(f"Stop loss price must be positive, got {stop_loss_price}")

        return errors

    def _parse_super_order(self, data: dict) -> SuperOrder:
        """Parse super order from API response."""
        leg_details_data = data.get("legDetails", [])
        leg_details = [
            SuperOrderLeg(
                leg_name=leg.get("legName", ""),
                transaction_type=leg.get("transactionType", ""),
                quantity=leg.get("quantity", 0),
                price=Decimal(str(leg.get("price", 0))),
                trigger_price=Decimal(str(leg.get("triggerPrice")))
                if leg.get("triggerPrice") is not None
                else None,
                order_status=leg.get("orderStatus"),
                trailing_jump=Decimal(str(leg.get("trailingJump")))
                if leg.get("trailingJump") is not None
                else None,
            )
            for leg in (leg_details_data if isinstance(leg_details_data, list) else [])
        ]

        return SuperOrder(
            order_id=str(data.get("orderId", "")),
            correlation_id=data.get("correlationId"),
            transaction_type=data.get("transactionType", ""),
            exchange_segment=data.get("exchangeSegment", ""),
            product_type=data.get("productType", ""),
            order_type=data.get("orderType", ""),
            security_id=str(data.get("securityId", "")),
            quantity=data.get("quantity", 0),
            price=Decimal(str(data.get("price", 0))),
            target_price=Decimal(str(data.get("targetPrice", 0))),
            stop_loss_price=Decimal(str(data.get("stopLossPrice", 0))),
            trailing_jump=Decimal(str(data.get("trailingJump", 0))),
            order_status=data.get("orderStatus", ""),
            leg_details=leg_details,
            trading_symbol=data.get("tradingSymbol"),
            created_time=data.get("createdAt"),
        )
