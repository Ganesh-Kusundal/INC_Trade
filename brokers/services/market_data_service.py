"""[DEPRECATED] Market data service. Use Instrument.quote() directly. — domain layer for real-time market data.

This service provides business logic for fetching and caching market
data. It depends on the MarketDataPort abstraction, not on any specific
broker implementation.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.domain.constants.exchanges import DEFAULT_EQUITY_EXCHANGE
from brokers.domain.entities import MarketDepth, Quote
from brokers.ports.market_data import MarketDataPort

logger = logging.getLogger(__name__)


class MarketDataService:
    """Domain service for real-time market data.

    Encapsulates business rules for data fetching, caching, and normalization.
    """

    def __init__(
        self,
        market_data_port: MarketDataPort,
        cache_ttl_seconds: float | None = None,
    ):
        """Initialize with a market data port.

        Args:
            market_data_port: Broker-agnostic market data interface
            cache_ttl_seconds: Cache TTL in seconds (backward compat, not used)
        """
        self._market_data_port = market_data_port
        self._cache_ttl_seconds = cache_ttl_seconds

    def ltp(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE) -> Decimal:
        """Get last traded price.

        Args:
            symbol: Instrument symbol
            exchange: Exchange code (default: NSE)

        Returns:
            Last traded price
        """
        return self._market_data_port.ltp(symbol, exchange)

    def quote(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE) -> Quote:
        """Get full quote with bid/ask.

        Args:
            symbol: Instrument symbol
            exchange: Exchange code (default: NSE)

        Returns:
            Quote object
        """
        return self._market_data_port.quote(symbol, exchange)

    def depth(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE) -> MarketDepth:
        """Get market depth (order book).

        Args:
            symbol: Instrument symbol
            exchange: Exchange code (default: NSE)

        Returns:
            MarketDepth object
        """
        return self._market_data_port.depth(symbol, exchange)

    def ltp_batch(
        self, symbols: list[str], exchange: str = DEFAULT_EQUITY_EXCHANGE
    ) -> dict[str, Decimal]:
        """Get LTP for multiple symbols.

        Args:
            symbols: List of instrument symbols
            exchange: Exchange code (default: NSE)

        Returns:
            Dictionary mapping symbol to LTP
        """
        return self._market_data_port.ltp_batch(symbols, exchange)

    def quote_batch(
        self, symbols: list[str], exchange: str = DEFAULT_EQUITY_EXCHANGE
    ) -> dict[str, Quote]:
        """Get quotes for multiple symbols.

        Args:
            symbols: List of instrument symbols
            exchange: Exchange code (default: NSE)

        Returns:
            Dictionary mapping symbol to Quote
        """
        return self._market_data_port.quote_batch(symbols, exchange)

    def invalidate(self, symbol: str) -> None:
        """Invalidate cached data for a symbol (backward compat).

        Args:
            symbol: Symbol to invalidate
        """
        # No-op for now (cache not implemented in this version)
        pass
