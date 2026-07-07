"""Dhan execution provider — order placement, modification, cancellation."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import httpx  # noqa: F401 — needed for test patching

from tradex.broker.auth import AuthManager
from tradex.broker.provider import ExecutionProvider
from tradex.broker.session import SessionManager
from tradex.core.errors import BrokerError
from tradex.core.events import EventBus
from tradex.core.logging_config import get_logger
from tradex.core.metrics import MetricsCollector
from tradex.core.rate_limiter import RateLimiter
from tradex.core.validation import validate_order_params
from tradex.domain.enums import (
    OrderType,
    ProductType,
    Side,
    Validity,
)
from tradex.domain.events import OrderCancelled, OrderModified, OrderPlaced
from tradex.domain.execution import ForeverOrder, Order, SuperOrder, Trade
from tradex.providers.dhan.config import DhanConfig
from tradex.providers.dhan.http_client import DhanHTTPClient
from tradex.providers.dhan.instruments import DhanInstrumentMapper

logger = get_logger("providers.dhan.execution")

# Dhan exchange segment strings for the order API
_DHAN_EXCHANGE_MAP = {
    "NSE_EQ": "NSE_EQ",
    "BSE_EQ": "BSE_EQ",
    "NSE_FNO": "NSE_FNO",
    "BSE_FNO": "BSE_FNO",
    "MCX_COMM": "MCX_COMM",
    "NSE_CURRENCY": "NSE_CURRENCY",
    "IDX_I": "IDX_I",
}


class DhanExecutionProvider(ExecutionProvider):
    """Dhan-specific order execution."""

    def __init__(
        self,
        config: DhanConfig,
        auth_manager: AuthManager,
        session: SessionManager,
        http_client: Optional[DhanHTTPClient] = None,
        rate_limiter: Optional[RateLimiter] = None,
        mapper: Optional[DhanInstrumentMapper] = None,
        event_bus: Optional[EventBus] = None,
        metrics: Optional[MetricsCollector] = None,
    ) -> None:
        self._config = config
        self._auth = auth_manager
        self._session = session
        self._http_client = http_client or DhanHTTPClient(config, auth_manager)
        self._rate_limiter = rate_limiter
        self._mapper = mapper
        self._event_bus = event_bus
        self._metrics = metrics

    async def place_order(
        self,
        security_id: str,
        exchange_segment: str,
        side: Side,
        quantity: int,
        order_type: OrderType,
        product_type: ProductType,
        price: float,
        trigger_price: float = 0,
        disclosed_quantity: int = 0,
        after_market_order: bool = False,
        validity: Validity = Validity.DAY,
        tag: str = "",
    ) -> Order:
        """Place an order with Dhan."""
        # Validate
        validate_order_params(
            security_id=security_id,
            exchange=exchange_segment,
            side=side.value,
            quantity=quantity,
            order_type=order_type.value,
            product_type=product_type.value,
            price=price,
            trigger_price=trigger_price,
        )

        # Rate limit
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "transactionType": side.value,
            "quantity": quantity,
            "orderType": order_type.value,
            "productType": product_type.value,
            "price": str(price),
            "triggerPrice": str(trigger_price),
            "disclosedQuantity": disclosed_quantity,
            "afterMarketOrder": after_market_order,
            "validity": validity.value,
            "correlationID": tag,
        }

        if self._metrics:
            self._metrics.increment(
                "dhan.orders.placed", exchange=exchange_segment, side=side.value
            )

        try:
            data = await self._http_client.post("/v2/orders", json=payload)

            order_data = data.get("data", {})
            order = Order(
                order_id=str(order_data.get("orderId", "")),
                correlation_id=tag,
                security_id=security_id,
                exchange_segment=exchange_segment,
                side=side,
                order_type=order_type,
                product_type=product_type,
                quantity=quantity,
                price=Decimal(str(price)),
                trigger_price=Decimal(str(trigger_price)),
                validity=validity,
                tag=tag,
                raw=order_data,
            )

            if self._event_bus:
                await self._event_bus.publish(
                    OrderPlaced(
                        order_id=order.order_id,
                        correlation_id=tag,
                        security_id=security_id,
                        side=side,
                        quantity=quantity,
                        source="dhan",
                    )
                )

            logger.info("order_placed", order_id=order.order_id, symbol=security_id)
            return order

        except BrokerError:
            if self._metrics:
                self._metrics.increment("dhan.orders.failed", exchange=exchange_segment)
            logger.error("order_placement_failed", security_id=security_id)
            raise

    async def modify_order(
        self,
        order_id: str,
        order_type: OrderType,
        quantity: int,
        price: float,
        trigger_price: float = 0,
        disclosed_quantity: int = 0,
        validity: Validity = Validity.DAY,
    ) -> Order:
        """Modify an existing order."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        payload = {
            "orderId": order_id,
            "orderType": order_type.value,
            "quantity": quantity,
            "price": str(price),
            "triggerPrice": str(trigger_price),
            "disclosedQuantity": disclosed_quantity,
            "validity": validity.value,
        }

        try:
            await self._http_client.put(f"/v2/orders/{order_id}", json=payload)

            if self._event_bus:
                await self._event_bus.publish(
                    OrderModified(
                        order_id=order_id,
                        source="dhan",
                    )
                )
            logger.info("order_modified", order_id=order_id)
            # Fetch updated order
            return await self.get_order(order_id)

        except BrokerError:
            logger.error("order_modify_failed", order_id=order_id)
            raise

    async def cancel_order(self, order_id: str) -> None:
        """Cancel an order."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            await self._http_client.delete(f"/v2/orders/{order_id}")

            if self._event_bus:
                await self._event_bus.publish(
                    OrderCancelled(
                        order_id=order_id,
                        source="dhan",
                    )
                )
            logger.info("order_cancelled", order_id=order_id)

        except BrokerError:
            logger.error("order_cancel_failed", order_id=order_id)
            raise

    async def get_order(self, order_id: str) -> Order:
        """Get order by ID."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        data = await self._http_client.get(f"/v2/orders/{order_id}")
        return Order.from_dhan(data.get("data", {}))

    async def get_orders(self) -> list[Order]:
        """Get all orders."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get("/v2/orders")
            orders_raw = data.get("data", [])
            if isinstance(orders_raw, list):
                return [Order.from_dhan(o) for o in orders_raw]
        except BrokerError:
            logger.warning("orders_fetch_failed")
        return []

    async def get_trades(self, order_id: Optional[str] = None) -> list[Trade]:
        """Get trades."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get("/v2/trades")
            trades_raw = data.get("data", [])
            if isinstance(trades_raw, list):
                trades = [Trade.from_dhan(t) for t in trades_raw]
                if order_id:
                    trades = [t for t in trades if t.order_id == order_id]
                return trades
        except BrokerError:
            logger.warning("trades_fetch_failed")
        return []

    async def get_trade_history(self, start_date: str, end_date: str, page: int = 0) -> list[Trade]:
        """Get trade history."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get(
                "/v2/trades/history",
                params={"from": start_date, "to": end_date, "page": page},
            )
            trades_raw = data.get("data", [])
            if isinstance(trades_raw, list):
                return [Trade.from_dhan(t) for t in trades_raw]
        except BrokerError:
            logger.warning("trade_history_fetch_failed")
        return []

    # ------------------------------------------------------------------
    # Super Orders
    # ------------------------------------------------------------------

    async def place_super_order(
        self,
        security_id: str,
        exchange_segment: str,
        side: Side,
        quantity: int,
        order_type: OrderType,
        product_type: ProductType,
        price: float,
        target_price: float = 0.0,
        stop_loss_price: float = 0.0,
        trailing_jump: float = 0.0,
        tag: str = "",
    ) -> SuperOrder:
        """Place a super (bracket) order with target and stop-loss legs."""
        validate_order_params(
            security_id=security_id,
            exchange=exchange_segment,
            side=side.value,
            quantity=quantity,
            order_type=order_type.value,
            product_type=product_type.value,
            price=price,
        )

        if self._rate_limiter:
            await self._rate_limiter.acquire()

        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "transactionType": side.value,
            "quantity": quantity,
            "orderType": order_type.value,
            "productType": product_type.value,
            "price": str(price),
            "targetPrice": str(target_price),
            "stopLossPrice": str(stop_loss_price),
            "trailingJump": str(trailing_jump),
            "correlationID": tag,
        }

        if self._metrics:
            self._metrics.increment(
                "dhan.super_orders.placed", exchange=exchange_segment, side=side.value
            )

        try:
            data = await self._http_client.post("/v2/superorders", json=payload)
            order_data = data.get("data", {})
            order = SuperOrder.from_dhan_super(order_data)
            order.correlation_id = tag

            if self._event_bus:
                await self._event_bus.publish(
                    OrderPlaced(
                        order_id=order.order_id,
                        correlation_id=tag,
                        security_id=security_id,
                        side=side,
                        quantity=quantity,
                        source="dhan",
                    )
                )

            logger.info("super_order_placed", order_id=order.order_id, symbol=security_id)
            return order

        except BrokerError:
            if self._metrics:
                self._metrics.increment("dhan.super_orders.failed", exchange=exchange_segment)
            logger.error("super_order_placement_failed", security_id=security_id)
            raise

    async def modify_super_order(
        self,
        order_id: str,
        order_type: OrderType,
        leg_name: str,
        quantity: int = 0,
        price: float = 0.0,
        target_price: float = 0.0,
        stop_loss_price: float = 0.0,
        trailing_jump: float = 0.0,
    ) -> SuperOrder:
        """Modify an existing super order."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        payload = {
            "orderId": order_id,
            "orderType": order_type.value,
            "legName": leg_name,
            "quantity": quantity,
            "price": str(price),
            "targetPrice": str(target_price),
            "stopLossPrice": str(stop_loss_price),
            "trailingJump": str(trailing_jump),
        }

        try:
            await self._http_client.put(f"/v2/superorders/{order_id}", json=payload)

            if self._event_bus:
                await self._event_bus.publish(OrderModified(order_id=order_id, source="dhan"))
            logger.info("super_order_modified", order_id=order_id)
            return await self.get_super_order(order_id)

        except BrokerError:
            logger.error("super_order_modify_failed", order_id=order_id)
            raise

    async def cancel_super_order(self, order_id: str, order_leg: str) -> None:
        """Cancel a super order or a specific leg."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            await self._http_client.delete(
                f"/v2/superorders/{order_id}",
                params={"orderLeg": order_leg},
            )

            if self._event_bus:
                await self._event_bus.publish(OrderCancelled(order_id=order_id, source="dhan"))
            logger.info("super_order_cancelled", order_id=order_id, leg=order_leg)

        except BrokerError:
            logger.error("super_order_cancel_failed", order_id=order_id)
            raise

    async def get_super_order(self, order_id: str) -> SuperOrder:
        """Get a single super order by ID."""
        orders = await self.get_super_orders()
        for o in orders:
            if o.order_id == order_id:
                return o
        from tradex.core.errors import ProviderError

        raise ProviderError(f"Super order {order_id} not found", code="DH-404")

    async def get_super_orders(self) -> list[SuperOrder]:
        """Get all super orders."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get("/v2/superorders")
            orders_raw = data.get("data", [])
            if isinstance(orders_raw, list):
                return [SuperOrder.from_dhan_super(o) for o in orders_raw]
        except BrokerError:
            logger.warning("super_orders_fetch_failed")
        return []

    # ------------------------------------------------------------------
    # Forever Orders
    # ------------------------------------------------------------------

    async def place_forever(
        self,
        security_id: str,
        exchange_segment: str,
        side: Side,
        product_type: ProductType,
        order_type: OrderType,
        quantity: int,
        price: float,
        trigger_price: float,
        order_flag: str = "SINGLE",
        disclosed_quantity: int = 0,
        validity: Validity = Validity.DAY,
        price1: float = 0.0,
        trigger_price1: float = 0.0,
        quantity1: int = 0,
        tag: str = "",
    ) -> ForeverOrder:
        """Place a forever (GTC) trigger order."""
        validate_order_params(
            security_id=security_id,
            exchange=exchange_segment,
            side=side.value,
            quantity=quantity,
            order_type=order_type.value,
            product_type=product_type.value,
            price=price,
            trigger_price=trigger_price,
        )

        if self._rate_limiter:
            await self._rate_limiter.acquire()

        payload: dict[str, Any] = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "transactionType": side.value,
            "productType": product_type.value,
            "orderType": order_type.value,
            "quantity": quantity,
            "price": str(price),
            "triggerPrice": str(trigger_price),
            "orderFlag": order_flag,
            "disclosedQuantity": disclosed_quantity,
            "validity": validity.value,
            "price1": str(price1),
            "triggerPrice1": str(trigger_price1),
            "quantity1": quantity1,
            "correlationID": tag,
        }

        if self._metrics:
            self._metrics.increment(
                "dhan.forever_orders.placed",
                exchange=exchange_segment,
                side=side.value,
            )

        try:
            data = await self._http_client.post("/v2/forever", json=payload)
            order_data = data.get("data", {})
            order = ForeverOrder.from_dhan_forever(order_data)
            order.correlation_id = tag

            if self._event_bus:
                await self._event_bus.publish(
                    OrderPlaced(
                        order_id=order.order_id,
                        correlation_id=tag,
                        security_id=security_id,
                        side=side,
                        quantity=quantity,
                        source="dhan",
                    )
                )

            logger.info("forever_order_placed", order_id=order.order_id, symbol=security_id)
            return order

        except BrokerError:
            if self._metrics:
                self._metrics.increment("dhan.forever_orders.failed", exchange=exchange_segment)
            logger.error("forever_order_placement_failed", security_id=security_id)
            raise

    async def modify_forever(
        self,
        order_id: str,
        order_type: OrderType,
        quantity: int,
        price: float,
        trigger_price: float = 0.0,
        disclosed_quantity: int = 0,
        validity: Validity = Validity.DAY,
    ) -> ForeverOrder:
        """Modify an existing forever order."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        payload = {
            "orderId": order_id,
            "orderType": order_type.value,
            "quantity": quantity,
            "price": str(price),
            "triggerPrice": str(trigger_price),
            "disclosedQuantity": disclosed_quantity,
            "validity": validity.value,
        }

        try:
            await self._http_client.put(f"/v2/forever/{order_id}", json=payload)

            if self._event_bus:
                await self._event_bus.publish(OrderModified(order_id=order_id, source="dhan"))
            logger.info("forever_order_modified", order_id=order_id)
            return await self.get_forever_order(order_id)

        except BrokerError:
            logger.error("forever_order_modify_failed", order_id=order_id)
            raise

    async def cancel_forever(self, order_id: str) -> None:
        """Cancel a forever order."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            await self._http_client.delete(f"/v2/forever/{order_id}")

            if self._event_bus:
                await self._event_bus.publish(OrderCancelled(order_id=order_id, source="dhan"))
            logger.info("forever_order_cancelled", order_id=order_id)

        except BrokerError:
            logger.error("forever_order_cancel_failed", order_id=order_id)
            raise

    async def get_forever_order(self, order_id: str) -> ForeverOrder:
        """Get a single forever order by ID."""
        orders = await self.get_forever_orders()
        for o in orders:
            if o.order_id == order_id:
                return o
        from tradex.core.errors import ProviderError

        raise ProviderError(f"Forever order {order_id} not found", code="DH-404")

    async def get_forever_orders(self) -> list[ForeverOrder]:
        """Get all forever orders."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get("/v2/forever")
            orders_raw = data.get("data", [])
            if isinstance(orders_raw, list):
                return [ForeverOrder.from_dhan_forever(o) for o in orders_raw]
        except BrokerError:
            logger.warning("forever_orders_fetch_failed")
        return []

    # ------------------------------------------------------------------
    # Slice Orders
    # ------------------------------------------------------------------

    async def place_slice_order(
        self,
        security_id: str,
        exchange_segment: str,
        side: Side,
        quantity: int,
        order_type: OrderType,
        product_type: ProductType,
        price: float,
        trigger_price: float = 0,
        disclosed_quantity: int = 0,
        after_market_order: bool = False,
        validity: Validity = Validity.DAY,
        tag: str = "",
    ) -> Order:
        """Place an order with automatic slicing for large quantities."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        payload = {
            "securityId": security_id,
            "exchangeSegment": exchange_segment,
            "transactionType": side.value,
            "quantity": quantity,
            "orderType": order_type.value,
            "productType": product_type.value,
            "price": str(price),
            "triggerPrice": str(trigger_price),
            "disclosedQuantity": disclosed_quantity,
            "afterMarketOrder": after_market_order,
            "validity": validity.value,
            "correlationID": tag,
            "shouldSlice": True,
        }

        if self._metrics:
            self._metrics.increment(
                "dhan.slice_orders.placed", exchange=exchange_segment, side=side.value
            )

        try:
            data = await self._http_client.post("/v2/orders", json=payload)
            order_data = data.get("data", {})
            order = Order(
                order_id=str(order_data.get("orderId", "")),
                correlation_id=tag,
                security_id=security_id,
                exchange_segment=exchange_segment,
                side=side,
                order_type=order_type,
                product_type=product_type,
                quantity=quantity,
                price=Decimal(str(price)),
                trigger_price=Decimal(str(trigger_price)),
                validity=validity,
                tag=tag,
                raw=order_data,
            )

            if self._event_bus:
                await self._event_bus.publish(
                    OrderPlaced(
                        order_id=order.order_id,
                        correlation_id=tag,
                        security_id=security_id,
                        side=side,
                        quantity=quantity,
                        source="dhan",
                    )
                )

            logger.info("slice_order_placed", order_id=order.order_id, symbol=security_id)
            return order

        except BrokerError:
            if self._metrics:
                self._metrics.increment("dhan.slice_orders.failed", exchange=exchange_segment)
            logger.error("slice_order_placement_failed", security_id=security_id)
            raise

    # ------------------------------------------------------------------
    # Kill Switch
    # ------------------------------------------------------------------

    async def kill_switch(self, status: str = "ON") -> dict[str, Any]:
        """Toggle the kill switch to unwind all open positions."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.post("/v2/killswitch", json={"status": status})
            logger.info("kill_switch_toggled", status=status)
            return data.get("data", {})

        except BrokerError:
            logger.error("kill_switch_failed", status=status)
            raise

    async def get_kill_switch_status(self) -> dict[str, Any]:
        """Get the current kill switch status."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get("/v2/killswitch")
            return data.get("data", {})
        except BrokerError:
            logger.warning("kill_switch_status_failed")
        return {}

    # ------------------------------------------------------------------
    # Ledger Report
    # ------------------------------------------------------------------

    async def ledger_report(self, start_date: str, end_date: str) -> dict[str, Any]:
        """Fetch ledger report for a date range."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        try:
            data = await self._http_client.get(
                "/v2/ledger",
                params={"from": start_date, "to": end_date},
            )
            return data.get("data", {})
        except BrokerError:
            logger.warning("ledger_fetch_failed")
        return {}
