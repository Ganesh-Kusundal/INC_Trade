"""Broker API contracts and SPI definitions.

Note: Brokers should import ports directly from
:mod:`brokers.common.gateway_interfaces` rather than from this package.
This module re-exports a subset for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from brokers.common.api.spi import (
    BrokerSource,
)
from brokers.common.gateway_interfaces import (
    ConditionalAlertProvider,
    CoverOrderProvider,
    FuturesProvider,
    GttOrderProvider,
    IdempotencyCachePort,
    MarginProvider,
    MarketDataProvider,
    MarketStatusProvider,
    NewsProvider,
    OptionsProvider,
    OrderCommand,
    OrderQuery,
    PortfolioProvider,
    SliceOrderCommand,
)
from brokers.common.resilience.errors import TradeXV2Error


class MarginCalculationError(TradeXV2Error):
    """Raised when margin calculation fails."""


@dataclass(frozen=True)
class MarginResult:
    """Result of a margin calculation."""

    required_margin: Decimal
    available_margin: Decimal
    span_margin: Decimal | None = None
    exposure_margin: Decimal | None = None

    @property
    def is_sufficient(self) -> bool:
        """Check if available margin covers required margin."""
        return self.available_margin >= self.required_margin


__all__ = [
    "BrokerSource",
    "ConditionalAlertProvider",
    "CoverOrderProvider",
    "FuturesProvider",
    "GttOrderProvider",
    "IdempotencyCachePort",
    "MarginCalculationError",
    "MarginProvider",
    "MarginResult",
    "MarketDataProvider",
    "MarketStatusProvider",
    "NewsProvider",
    "OptionsProvider",
    "OrderCommand",
    "OrderQuery",
    "PortfolioProvider",
    "SliceOrderCommand",
]
