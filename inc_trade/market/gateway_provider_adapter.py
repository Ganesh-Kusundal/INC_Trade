"""GatewayInstrumentProvider — wraps existing BrokerGateway for backward compat.

Adapts the legacy BrokerGateway interface to the new provider protocols
(InstrumentDataProvider, HistoricalDataProvider, DepthProvider).

This enables gradual migration: instruments can use the new provider
interface while the underlying implementation still delegates to the
existing gateway. When broker adapters are rewritten to implement
the provider protocols directly, this adapter can be removed.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any


class GatewayInstrumentProvider:
    """Adapts BrokerGateway to InstrumentDataProvider protocol.

    Usage::

        from inc_trade.market.gateway_provider_adapter import GatewayInstrumentProvider

        provider = GatewayInstrumentProvider(gateway)
        instrument = InstrumentFactory.create(
            symbol="RELIANCE", exchange="NSE",
            provider=provider,
        )
    """

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    def quote(self, symbol: str, exchange: str) -> Any:
        """Get quote via gateway.market_data.quote()."""
        return self._gateway.market_data.quote(symbol, exchange)

    def ltp(self, symbol: str, exchange: str) -> Decimal:
        """Get LTP via gateway.market_data.ltp()."""
        return self._gateway.market_data.ltp(symbol, exchange)

    def depth(self, symbol: str, exchange: str, levels: int = 5) -> Any:
        """Get market depth via gateway.market_data.depth()."""
        return self._gateway.market_data.depth(symbol, exchange)

    def quote_batch(self, symbols: list[str], exchange: str) -> dict[str, Any]:
        """Get quotes for multiple symbols."""
        results = {}
        for symbol in symbols:
            try:
                results[symbol] = self.quote(symbol, exchange)
            except Exception:
                pass
        return results

    def option_chain(
        self, underlying: str, exchange: str, expiry: str | None = None
    ) -> Any:
        """Get option chain via gateway."""
        if hasattr(self._gateway, "options_data"):
            return self._gateway.options_data.option_chain(
                underlying=underlying, exchange=exchange, expiry=expiry
            )
        return self._gateway.market_data.option_chain(
            underlying=underlying, exchange=exchange, expiry=expiry
        )


class GatewayHistoricalProvider:
    """Adapts BrokerGateway to HistoricalDataProvider protocol."""

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Any]:
        """Get historical candles via gateway."""
        return self._gateway.historical_data.get_candles(
            symbol=symbol,
            exchange=exchange,
            start_time=start_time,
            end_time=end_time,
            resolution=resolution,
        )


class GatewayDepthProvider:
    """Adapts BrokerGateway to DepthProvider protocol."""

    def __init__(self, gateway: Any, max_levels: int = 5) -> None:
        self._gateway = gateway
        self._max_levels = max_levels

    def depth(self, symbol: str, exchange: str, levels: int = 5) -> Any:
        """Get market depth via gateway."""
        return self._gateway.market_data.depth(symbol, exchange)

    @property
    def max_levels(self) -> int:
        """Maximum depth levels supported."""
        return self._max_levels
