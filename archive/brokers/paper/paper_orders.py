"""Simulated order management for paper trading."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock

from domain import (
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Side,
    Trade,
    Validity,
)

from .paper_market_data import PaperMarketData


class PaperOrders:
    """Simulates order placement with instant fills at quoted prices.

    When ``order_manager`` and ``position_manager`` are supplied, the paper
    engine publishes canonical events and delegates state ownership to those
    managers. Otherwise it keeps the state internally for backward
    compatibility.
    """

    def __init__(
        self,
        market_data: PaperMarketData,
        positions: dict[str, Position],
        order_manager: object | None = None,
        position_manager: object | None = None,
    ) -> None:
        self._md = market_data
        self._positions = positions
        self._order_manager = order_manager
        self._position_manager = position_manager
        self._orders: list[Order] = []
        self._trades: list[Trade] = []
        self._order_seq = 0
        self._trade_seq = 0
        self._lock = RLock()

    def _risk_check(self, order: Order) -> tuple[bool, str | None]:
        """Delegate to the central risk manager if available."""
        risk = getattr(self._order_manager, "risk_manager", None)
        if risk is None:
            return True, None
        result = risk.check_order(order)
        return result.allowed, result.reason

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str | Side = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str | OrderType = "MARKET",
        product_type: str | ProductType = "INTRADAY",
        validity: str | Validity = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> Order:
        if isinstance(side, str):
            side = Side(side.upper())
        if isinstance(order_type, str):
            order_type = OrderType(order_type.upper())
        if isinstance(product_type, str):
            product_type = ProductType(product_type.upper())
        if isinstance(validity, str):
            validity = Validity(validity.upper())

        # REF-018: Route through OMS OrderManager for idempotency when available.
        if self._order_manager is not None:
            return self._place_via_oms(
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                price=price,
                order_type=order_type,
                product_type=product_type,
                validity=validity,
                trigger_price=trigger_price,
                correlation_id=correlation_id,
            )

        # Legacy path: no OMS available, manage state internally.
        return self._place_internal(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )

    def _place_via_oms(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal,
        order_type: OrderType,
        product_type: ProductType,
        validity: Validity,
        trigger_price: Decimal,
        correlation_id: str | None,
    ) -> Order:
        """Route through OrderManager.place_order for idempotency + risk + events."""
        from application.oms.order_manager import OmsOrderCommand

        self._order_seq += 1
        seq = self._order_seq

        cmd = OmsOrderCommand(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            correlation_id=correlation_id or f"ppr:{seq}",
        )

        fill_price = (
            price
            if price > 0 and order_type == OrderType.LIMIT
            else self._md.get_ltp(symbol, exchange)
        )

        def _fill(cmd: OmsOrderCommand) -> Order:
            return Order(
                order_id=f"PPR-{seq:06d}",
                symbol=cmd.symbol,
                exchange=cmd.exchange,
                side=cmd.side,
                order_type=cmd.order_type,
                quantity=cmd.quantity,
                filled_quantity=cmd.quantity,
                price=cmd.price,
                trigger_price=trigger_price,
                status=OrderStatus.FILLED,
                timestamp=datetime.now(timezone.utc),
                product_type=cmd.product_type,
                avg_price=fill_price,
                correlation_id=cmd.correlation_id,
            )

        result = self._order_manager.place_order(
            request=cmd,
            submit_fn=_fill,
        )
        if not result.success or result.order is None:
            rejected = Order(
                order_id=f"PPR-{seq:06d}",
                symbol=symbol,
                exchange=exchange,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                status=OrderStatus.REJECTED,
                correlation_id=correlation_id,
            )
            with self._lock:
                self._orders.append(rejected)
            # Upsert rejected order to OMS for audit trail (matches legacy behavior).
            self._order_manager.upsert_order(rejected)
            return rejected

        # Keep internal order/trade list synced for backward-compatible getters.
        with self._lock:
            self._orders.append(result.order)
            self._order_seq = seq  # sync sequence counter

        # Record trade through OMS so PositionManager receives TRADE_APPLIED event.
        self._trade_seq += 1
        trade = Trade(
            trade_id=f"PPR-T-{self._trade_seq:06d}",
            order_id=result.order.order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=fill_price,
            trade_value=fill_price * quantity,
            timestamp=datetime.now(timezone.utc),
            product_type=product_type,
        )
        with self._lock:
            self._trades.append(trade)
            # Sync internal position dict for backward-compatible getters.
            self._positions = self._update_position(
                symbol,
                exchange,
                side,
                quantity,
                fill_price,
                product_type,
            )
        self._order_manager.record_trade(trade)

        return result.order

    def _place_internal(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal,
        order_type: OrderType,
        product_type: ProductType,
        validity: Validity,
        trigger_price: Decimal,
        correlation_id: str | None,
    ) -> Order:
        """Legacy internal order placement (no OMS, backward compatible)."""
        if price > 0 and order_type == OrderType.LIMIT:
            fill_price = price
        else:
            fill_price = self._md.get_ltp(symbol, exchange)

        with self._lock:
            self._order_seq += 1
            order_id = f"PPR-{self._order_seq:06d}"

            preview_order = Order(
                order_id=order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                product_type=product_type,
                validity=validity,
                correlation_id=correlation_id,
            )
            allowed, reason = self._risk_check(preview_order)
            if not allowed:
                rejected = replace(
                    preview_order,
                    status=OrderStatus.REJECTED,
                    reject_reason=reason or "Risk check failed",
                )
                self._orders.append(rejected)
                return rejected

            order = Order(
                order_id=order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                order_type=order_type,
                quantity=quantity,
                filled_quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                status=OrderStatus.FILLED,
                timestamp=datetime.now(timezone.utc),
                product_type=product_type,
                validity=validity,
                avg_price=fill_price,
                correlation_id=correlation_id,
            )

            self._orders.append(order)
            self._trade_seq += 1
            trade = Trade(
                trade_id=f"PPR-T-{self._trade_seq:06d}",
                order_id=order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                price=fill_price,
                trade_value=fill_price * quantity,
                timestamp=datetime.now(timezone.utc),
                product_type=product_type,
            )
            self._trades.append(trade)

            if self._position_manager is not None:
                self._position_manager.apply_trade(trade)
            self._positions = self._update_position(
                symbol, exchange, side, quantity, fill_price, product_type
            )

            return order

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            for i, o in enumerate(self._orders):
                if o.order_id == order_id and o.status == OrderStatus.OPEN:
                    self._orders[i] = o.with_status(OrderStatus.CANCELLED)
                    return True
            return False

    def get_order(self, order_id: str) -> Order | None:
        """Query a single order by ID.

        H1 Critical Fix: Enables post-cancellation verification for paper
        trading by allowing lookup of individual orders.

        Args:
            order_id: Paper order ID to look up

        Returns:
            Order if found, None if not in orderbook
        """
        with self._lock:
            for order in self._orders:
                if order.order_id == order_id:
                    return order
        return None

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        trigger_price: Decimal | None = None,
        validity: Validity | None = None,
    ) -> Order:
        """Modify an open order - simulates order modification.

        P-2.1 Critical Fix: Implements modify_order for paper trading.
        Only allows modification if order is in OPEN status.
        Changes are applied to the order and a new modified order is created.

        Args:
            order_id: Order ID to modify
            quantity: New quantity (optional)
            price: New price (optional)
            order_type: New order type (optional)
            trigger_price: New trigger price for SL orders (optional)
            validity: New validity (optional)

        Returns:
            Modified Order with updated fields

        Raises:
            ValueError: If order not found or not in OPEN status
        """
        with self._lock:
            # Find the order
            original_idx = None
            original_order = None
            for i, o in enumerate(self._orders):
                if o.order_id == order_id:
                    original_idx = i
                    original_order = o
                    break

            if original_order is None:
                raise ValueError(f"Order {order_id} not found")

            if original_order.status != OrderStatus.OPEN:
                raise ValueError(
                    f"Cannot modify order {order_id} with status {original_order.status.value}. "
                    f"Only OPEN orders can be modified."
                )

            # Cancel the original order
            self._orders[original_idx] = original_order.with_status(OrderStatus.CANCELLED)

            # Create a new modified order
            self._order_seq += 1
            new_order_id = f"PPR-{self._order_seq:06d}"

            # Apply modifications
            modified_order = Order(
                order_id=new_order_id,
                symbol=original_order.symbol,
                exchange=original_order.exchange,
                side=original_order.side,
                order_type=order_type if order_type is not None else original_order.order_type,
                quantity=quantity if quantity is not None else original_order.quantity,
                price=price if price is not None else original_order.price,
                trigger_price=trigger_price if trigger_price is not None else original_order.trigger_price,
                validity=validity if validity is not None else original_order.validity,
                product_type=original_order.product_type,
                correlation_id=original_order.correlation_id,
                status=OrderStatus.OPEN,  # New order starts as OPEN
                timestamp=datetime.now(timezone.utc),
            )

            # Risk check on modified order
            allowed, reason = self._risk_check(modified_order)
            if not allowed:
                rejected = replace(
                    modified_order,
                    status=OrderStatus.REJECTED,
                    reject_reason=reason or "Risk check failed on modification",
                )
                self._orders.append(rejected)
                return rejected

            # For paper trading, instantly fill the modified order
            fill_price = (
                modified_order.price
                if modified_order.price > 0 and modified_order.order_type == OrderType.LIMIT
                else self._md.get_ltp(modified_order.symbol, modified_order.exchange)
            )

            filled_order = replace(
                modified_order,
                status=OrderStatus.FILLED,
                filled_quantity=modified_order.quantity,
                avg_price=fill_price,
            )

            self._orders.append(filled_order)

            # Create trade for the fill
            self._trade_seq += 1
            trade = Trade(
                trade_id=f"PPR-T-{self._trade_seq:06d}",
                order_id=new_order_id,
                symbol=modified_order.symbol,
                exchange=modified_order.exchange,
                side=modified_order.side,
                quantity=modified_order.quantity,
                price=fill_price,
                trade_value=fill_price * modified_order.quantity,
                timestamp=datetime.now(timezone.utc),
                product_type=modified_order.product_type,
            )
            self._trades.append(trade)

            # Update position if position_manager exists
            if self._position_manager is not None:
                self._position_manager.apply_trade(trade)
            self._positions = self._update_position(
                modified_order.symbol,
                modified_order.exchange,
                modified_order.side,
                modified_order.quantity,
                fill_price,
                modified_order.product_type,
            )

            return filled_order

    def get_orderbook(self) -> list[Order]:
        with self._lock:
            return list(self._orders)

    def get_trade_book(self) -> list[Trade]:
        with self._lock:
            return list(self._trades)

    def get_positions(self) -> list[Position]:
        with self._lock:
            return list(self._positions.values())

    def _update_position(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: Decimal,
        product_type: ProductType = ProductType.INTRADAY,
    ) -> dict[str, Position]:
        key = f"{symbol}:{exchange}"
        with self._lock:
            old_pos = self._positions.get(
                key, Position(symbol=symbol, exchange=exchange, product_type=product_type)
            )
            delta = quantity if side == Side.BUY else -quantity
            new_pos = old_pos.with_fill(delta, price)
            new_positions = dict(self._positions)
            new_positions[key] = new_pos
            return new_positions
