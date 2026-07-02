"""GatewaySubmissionPipeline — shared order submission logic for broker gateways.

Both :class:`~brokers.dhan.gateway.BrokerGateway` and
:class:`~brokers.upstox.gateway.UpstoxBrokerGateway` repeat the same pattern
when placing an order:

1.  Resolve a correlation ID (from caller or thread-local)
2.  Parse the exchange string into an ``ExchangeSegment``
3.  Build a :class:`~brokers.common.dtos.BrokerOrderPayload`
4.  Delegate to the broker-specific order adapter
5.  Convert exceptions to ``OrderResponse.fail()``

This module extracts that shared pipeline into a single helper so both
gateways (and future brokers) can delegate to it.

Usage
-----
In a gateway's ``place_order`` method::

    from brokers.common.submission_pipeline import build_payload

    request = build_payload(
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
        exchange_segment=exchange_segment,
        provider_metadata=provider_metadata,
    )
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from brokers.common.dtos import BrokerOrderPayload
from domain import OrderResponse, OrderStatus
from domain import OrderType as DomainOrderType
from domain import ProductType as DomainProductType
from domain import Side as DomainSide
from domain import Validity as DomainValidity
from domain.exchange_segments import parse_segment
from domain.types import ExchangeSegment

logger = logging.getLogger(__name__)


def resolve_correlation_id(correlation_id: str | None = None) -> str | None:
    """Resolve a correlation ID for order tracing.

    If *correlation_id* is provided, returns it as-is.  Otherwise attempts
    to read the current thread's active correlation ID set via
    :func:`infrastructure.correlation.with_correlation`.

    Returns None if no correlation ID is available.
    """
    if correlation_id is not None:
        return correlation_id
    try:
        from infrastructure.correlation import get_current_correlation_id

        return get_current_correlation_id()
    except ImportError:
        return None


def parse_exchange_segment(
    exchange: str,
    *,
    symbol: str = "",
    index_segment: ExchangeSegment | None = None,
) -> ExchangeSegment:
    """Parse a user-facing exchange string into a canonical ``ExchangeSegment``.

    For recognised index symbols (NIFTY, BANKNIFTY, etc.) the segment defaults
    to ``ExchangeSegment.IDX_I`` when *index_segment* is not provided.  Callers
    can pass a custom *index_segment* for broker-specific index mapping.

    Args:
        exchange: User-facing exchange string (e.g. ``"NSE"``, ``"NFO"``).
        symbol: Optional symbol for index detection.
        index_segment: Optional override segment for index symbols.

    Returns:
        Canonical ``ExchangeSegment`` value.

    Raises:
        ValueError: If the exchange string is not a recognised segment.
    """
    # Check for index symbols if a symbol is provided
    if symbol:
        try:
            from config.indices import index_upstox_key

            if index_upstox_key(symbol) is not None:
                return index_segment or ExchangeSegment.IDX_I
        except ImportError:
            pass

    parsed = parse_segment(exchange)
    if parsed is None:
        raise ValueError(f"Unknown exchange segment: {exchange!r}")
    return parsed


def build_payload(
    *,
    symbol: str,
    exchange: str,
    side: str,
    quantity: int,
    price: Decimal,
    order_type: str,
    product_type: str,
    validity: str,
    trigger_price: Decimal,
    correlation_id: str | None,
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE,
    provider_metadata: dict[str, Any] | None = None,
) -> BrokerOrderPayload:
    """Build a canonical ``BrokerOrderPayload`` from flat parameters.

    This is the shared payload-construction step that both Dhan and Upstox
    gateways use.  It normalises enums, constructs the payload, and returns
    it ready for broker-adapter submission.

    Important: Exchange-segment parsing is **not** done here — the caller
    must parse the exchange string at the gateway level where broker-specific
    segment logic lives.  The *exchange_segment* parameter defaults to NSE
    and the caller should override it with the result of a broker-specific
    ``parse_exchange_segment`` call.

    Args:
        symbol: Trading symbol.
        exchange: Exchange identifier (e.g. ``"NSE"``, ``"NFO"``).
        side: ``"BUY"`` or ``"SELL"``.
        quantity: Order quantity.
        price: Limit price (``Decimal("0")`` for MARKET orders).
        order_type: ``"MARKET"``, ``"LIMIT"``, ``"STOP_LOSS"``, ``"STOP_LOSS_MARKET"``.
        product_type: ``"INTRADAY"``, ``"CNC"``, ``"MARGIN"``, etc.
        validity: ``"DAY"`` or ``"IOC"``.
        trigger_price: Trigger price for SL orders.
        correlation_id: Optional correlation ID for tracing.
        exchange_segment: Canonical exchange segment (default NSE).
        provider_metadata: Optional broker-specific transport metadata.

    Returns:
        A new ``BrokerOrderPayload`` (immutable).
    """
    return BrokerOrderPayload(
        symbol=symbol,
        exchange=exchange,
        exchange_segment=exchange_segment,
        transaction_type=DomainSide(side.upper()),
        quantity=quantity,
        price=price,
        trigger_price=trigger_price if trigger_price > Decimal("0") else None,
        order_type=DomainOrderType(order_type.upper()),
        product_type=DomainProductType(product_type.upper()),
        validity=DomainValidity(validity.upper()),
        correlation_id=correlation_id,
        provider_metadata=provider_metadata or {},
    )


def order_response_from_result(
    order_id: str | None,
    *,
    message: str = "Order placed",
    status: OrderStatus = OrderStatus.OPEN,
) -> OrderResponse:
    """Create a success ``OrderResponse`` from a placement result."""
    return OrderResponse.ok(order_id=order_id or "", message=message, status=status)


def order_response_from_error(exc: Exception) -> OrderResponse:
    """Convert an exception to a failure ``OrderResponse``.

    Handles common broker exception types and logs the error for
    observability.  Returns ``OrderResponse.fail()`` so the caller
    never needs to catch inside the gateway.
    """
    error_message = str(exc)
    logger.warning(
        "order_placement_failed",
        extra={"error": error_message, "error_type": type(exc).__name__},
    )
    return OrderResponse.fail(error_message)


__all__ = [
    "build_payload",
    "order_response_from_error",
    "order_response_from_result",
    "parse_exchange_segment",
    "resolve_correlation_id",
]
