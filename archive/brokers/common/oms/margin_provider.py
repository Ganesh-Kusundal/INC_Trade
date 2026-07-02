"""Broker-agnostic margin provider adapter.

Bridges broker-specific margin calculation adapters to the RiskManager's
MarginProvider port. This keeps the RiskManager broker-agnostic while
allowing each broker adapter to provide its own margin calculation logic.

Design rules
------------
* The RiskManager depends on the MarginProvider port, NOT on broker-specific
  margin adapters. This adapter bridges the two.
* Fail-closed: if the underlying broker margin API fails, the error
  propagates as MarginCalculationError so the RiskManager can reject
  the order.
* All monetary values use Decimal — never float.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from brokers.common.api import MarginCalculationError, MarginProvider, MarginResult

logger = logging.getLogger(__name__)


class BrokerMarginProvider(MarginProvider):
    """Adapts a broker-specific margin adapter to the RiskManager's MarginProvider port.

    Args:
        broker_margin_provider: The broker-specific margin provider that
            implements the calculate_margin method (or similar).
            Can be any object that has the margin calculation capability.
            If None, margin checks will fail-closed.

    Example usage::

        from brokers.dhan.margin import MarginAdapter
        from brokers.common.oms.margin_provider import BrokerMarginProvider

        dhan_margin = MarginAdapter(client, identity)
        provider = BrokerMarginProvider(dhan_margin)
        risk_manager = RiskManager(
            position_manager=pm,
            config=config,
            margin_provider=provider,
        )
    """

    def __init__(self, broker_margin_provider: Any | None = None) -> None:
        self._broker_margin_provider = broker_margin_provider

    def calculate_margin(self, payload: dict) -> dict:
        """Delegate to broker-specific margin calculator.

        Args:
            payload: Broker-specific margin request payload.

        Returns:
            Raw margin calculation response from the broker.

        Raises:
            MarginCalculationError: If no broker margin provider is configured
                or the broker call fails.
        """
        if self._broker_margin_provider is None:
            raise MarginCalculationError("No broker margin provider configured")
        return self._broker_margin_provider.calculate_margin(payload)

    def calculate_margin_for_order(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: Decimal,
        product_type: str,
        order_type: str,
    ) -> MarginResult:
        """Calculate margin for a specific order via the broker adapter.

        This is the method called by RiskManager during pre-trade risk checks.

        Args:
            symbol: Instrument symbol.
            exchange: Exchange segment (e.g. "NFO", "CDS", "MCX").
            quantity: Order quantity.
            price: Order price.
            product_type: Product type (e.g. "MIS", "NRML", "CNC").
            order_type: Order type (e.g. "LIMIT", "MARKET", "SL").

        Returns:
            MarginResult with required and available margin details.

        Raises:
            MarginCalculationError: If the broker margin API call fails.
        """
        if self._broker_margin_provider is None:
            raise MarginCalculationError("No broker margin provider configured")

        # The broker-specific adapter may have a different interface.
        # This adapter translates between the RiskManager's expectation
        # and the broker's API contract.
        #
        # We call the generic calculate_margin with a standardised payload.
        # Broker adapters that implement calculate_margin_for_order directly
        # should be detected and used instead.
        if hasattr(self._broker_margin_provider, "calculate_margin_for_order"):
            return self._broker_margin_provider.calculate_margin_for_order(
                symbol=symbol,
                exchange=exchange,
                quantity=quantity,
                price=price,
                product_type=product_type,
                order_type=order_type,
            )

        # Fallback: build a payload for the generic calculate_margin
        payload = {
            "symbol": symbol,
            "exchange": exchange,
            "quantity": quantity,
            "price": price,
            "product_type": product_type,
            "order_type": order_type,
        }

        try:
            raw_response = self._broker_margin_provider.calculate_margin(payload)
        except Exception as exc:
            raise MarginCalculationError(f"Broker margin API call failed: {exc}") from exc

        # Parse the raw response into a MarginResult
        return self._parse_margin_response(raw_response)

    def _parse_margin_response(self, raw: dict) -> MarginResult:
        """Parse a raw broker margin response into a MarginResult.

        Different brokers may return different field names. This method
        handles the most common patterns.

        Args:
            raw: Raw response dict from the broker's margin API.

        Returns:
            Parsed MarginResult.
        """
        # Extract required margin — try various field names
        required = Decimal("0")
        for key in (
            "total_margin",
            "totalMargin",
            "order_margin",
            "orderMargin",
            "required_margin",
        ):
            if key in raw:
                required = Decimal(str(raw[key]))
                break

        # Extract available margin
        available = Decimal("0")
        for key in ("available_margin", "availableMargin", "net_available"):
            if key in raw:
                available = Decimal(str(raw[key]))
                break

        # Extract span margin (optional)
        span: Decimal | None = None
        for key in ("span_margin", "spanMargin"):
            if key in raw and raw[key] is not None:
                span = Decimal(str(raw[key]))
                break

        # Extract exposure margin (optional)
        exposure: Decimal | None = None
        for key in ("exposure_margin", "exposureMargin"):
            if key in raw and raw[key] is not None:
                exposure = Decimal(str(raw[key]))
                break

        return MarginResult(
            required_margin=required,
            available_margin=available,
            span_margin=span,
            exposure_margin=exposure,
        )
