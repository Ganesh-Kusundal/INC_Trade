"""OrderCommand — command side of CQS for write-only order operations.

Splits Instrument's command responsibilities into a dedicated application
service, enabling clean CQS separation while maintaining backward
compatibility through Instrument convenience delegates.

Usage::

    cmd = OrderCommand(instrument, order_provider=adapter)
    result = cmd.buy(quantity=10, price=Decimal("2850"))
    result = cmd.sell(quantity=10)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from inc_trade.market.instrument import Instrument
    from inc_trade.ports.event_publisher import EventPublisherPort
    from inc_trade.ports.providers import OrderProvider

logger = logging.getLogger(__name__)


class OrderCommand:
    """Write-only order operations for an instrument.

    Pure command side of CQS. Every method mutates system state
    (creates an order on the exchange).

    Resolves the order provider in this order:
    1. Explicitly passed ``order_provider`` (highest priority)
    2. Instrument's ``_order_provider`` (attached by factory)
    3. Instrument's ``_provider`` (general provider fallback)

    Args:
        instrument: The target Instrument.
        order_provider: ``OrderProvider`` protocol implementation.
            If None, resolved from the instrument's attached providers.
        event_publisher: Optional ``EventPublisherPort`` for publishing
            domain events after successful order placement.
    """

    def __init__(
        self,
        instrument: Instrument,
        order_provider: OrderProvider | None = None,
        event_publisher: EventPublisherPort | None = None,
    ) -> None:
        self._instrument = instrument
        self._order_provider = order_provider
        self._event_publisher = event_publisher

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _resolve_provider(self) -> OrderProvider:
        """Resolve the order provider."""
        if self._order_provider is not None:
            return self._order_provider
        inst = self._instrument
        # Check instrument's dedicated order provider
        op = getattr(inst, "_order_provider", None)
        if op is not None:
            return op
        # Fall back to general provider
        gp = getattr(inst, "_provider", None)
        if gp is not None:
            return gp
        raise RuntimeError(
            f"No order provider configured for {inst.composite_key}. "
            "Set order_provider via constructor or instrument.with_providers()."
        )

    # ── Public API ──────────────────────────────────────────────────────────

    def buy(
        self,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any:
        """Place a buy order for this instrument.

        Args:
            quantity: Number of units to buy.
            order_type: ``OrderType`` enum value (default: ``OrderType.MARKET``).
            price: Limit price (required for LIMIT orders).
            trigger_price: Trigger price (required for STOP_LOSS orders).
            **kwargs: Additional broker-specific order parameters.

        Returns:
            ``OrderResponse`` from the broker adapter.

        Raises:
            RuntimeError: If no order provider is configured.
        """
        from inc_trade.domain.enums import OrderType as OT

        provider = self._resolve_provider()
        result = provider.place_order(
            symbol=self._instrument.symbol,
            exchange=self._instrument.exchange,
            side="BUY",
            quantity=quantity,
            order_type=order_type or OT.MARKET,
            price=price,
            trigger_price=trigger_price,
            **kwargs,
        )
        self._publish_order_placed_event(result, "BUY", quantity, order_type, price, trigger_price)
        return result

    def sell(
        self,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any:
        """Place a sell order for this instrument.

        Args:
            quantity: Number of units to sell.
            order_type: ``OrderType`` enum value (default: ``OrderType.MARKET``).
            price: Limit price (required for LIMIT orders).
            trigger_price: Trigger price (required for STOP_LOSS orders).
            **kwargs: Additional broker-specific order parameters.

        Returns:
            ``OrderResponse`` from the broker adapter.

        Raises:
            RuntimeError: If no order provider is configured.
        """
        from inc_trade.domain.enums import OrderType as OT

        provider = self._resolve_provider()
        result = provider.place_order(
            symbol=self._instrument.symbol,
            exchange=self._instrument.exchange,
            side="SELL",
            quantity=quantity,
            order_type=order_type or OT.MARKET,
            price=price,
            trigger_price=trigger_price,
            **kwargs,
        )
        self._publish_order_placed_event(result, "SELL", quantity, order_type, price, trigger_price)
        return result

    # ── Event Publishing ────────────────────────────────────────────────────

    def _publish_order_placed_event(
        self,
        result: Any,
        side: str,
        quantity: int,
        order_type: Any,
        price: Decimal,
        trigger_price: Decimal,
    ) -> None:
        """Publish an OrderPlacedEvent after a successful order.

        Failures are logged but never propagated — the order flow is
        never broken by a broken event bus.
        """
        if self._event_publisher is None:
            return
        if not getattr(result, "success", False):
            return
        try:
            from inc_trade.domain.events import OrderPlacedEvent

            event = OrderPlacedEvent(
                symbol=self._instrument.symbol,
                exchange=self._instrument.exchange,
                side=side,
                quantity=quantity,
                order_id=getattr(result, "order_id", ""),
                order_type=str(order_type) if order_type else "",
                price=price,
                trigger_price=str(trigger_price),
            )
            self._event_publisher.publish(event)
        except Exception:
            logger.warning("Failed to publish order placed event", exc_info=True)

    @property
    def instrument(self) -> Any:
        """The instrument this command is bound to."""
        return self._instrument
