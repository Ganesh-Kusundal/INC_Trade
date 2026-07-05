"""Broker facade — primary entry point enforcing service layer usage.

Usage::

    from brokers import create_broker

    broker = create_broker("dhan", access_token="...", client_id="...")
    resp = broker.place_order("RELIANCE", "NSE", Side.BUY, 10)
    quote = broker.get_quote("RELIANCE")
    positions = broker.get_positions()
"""

from __future__ import annotations

import logging
import warnings
from datetime import datetime
from decimal import Decimal
from typing import Any

from inc_trade.domain import (
    Balance,
    Candle,
    Holding,
    InstrumentInfo,
    MarketDepth,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)
from inc_trade.domain.enums import BrokerID, OrderType, ProductType, Side, Validity
from inc_trade.ports.broker import BrokerGateway
from inc_trade.ports.extension_registry import ExtensionRegistryPort
from inc_trade.services.historical_service import HistoricalService
from inc_trade.services.instrument_service import InstrumentService
from inc_trade.services.market_data_service import MarketDataService
from inc_trade.services.options_service import OptionsService
from inc_trade.services.order_service import OrderService
from inc_trade.services.portfolio_service import PortfolioService
from inc_trade.utils.idempotency_cache import TypedIdempotencyCache

logger = logging.getLogger(__name__)


class BrokerFacade:
    """Primary entry point for broker operations.

    Wraps a BrokerGateway and enforces service layer usage by delegating
    all operations through application services. This ensures consistent
    validation, idempotency, logging, and error handling.

    Args:
        gateway: A BrokerGateway implementation (e.g. DhanGateway).
        allow_live_orders: Enable live order placement (kill switch).
            Defaults to True. Set to False to block order placement/cancellation.
    """

    def __init__(
        self,
        gateway: BrokerGateway,
        allow_live_orders: bool = True,
        extension_registry: ExtensionRegistryPort | None = None,
    ):
        self._gateway = gateway
        from inc_trade.ports.extension_registry import DictExtensionRegistry

        self._registry = extension_registry or DictExtensionRegistry()
        self._order_service = OrderService(
            gateway.orders,
            idempotency_cache=TypedIdempotencyCache[OrderResponse](),
            allow_live_orders=allow_live_orders,
        )
        self._market_data_service = MarketDataService(gateway.market_data)
        self._portfolio_service = PortfolioService(gateway.portfolio)
        self._historical_service = HistoricalService(gateway.historical)
        self._instrument_service = InstrumentService(gateway.instruments)
        self._options_service = OptionsService(getattr(gateway, "options", None))

    # --- Deprecation helper ---

    def _warn_deprecated(self, method_name: str) -> None:
        warnings.warn(
            f"BrokerFacade.{method_name}() is deprecated, use BrokerSession equivalent instead",
            DeprecationWarning,
            stacklevel=3,
        )

    # --- Identity ---

    @property
    def broker_id(self) -> BrokerID:
        """Canonical broker identifier (e.g. 'dhan', 'upstox')."""
        return BrokerID(self._gateway.broker_id)

    # --- Orders ---

    def place_order(
        self,
        symbol: str = "",
        exchange: str = "",
        side: Side = Side.BUY,
        quantity: int = 0,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str = "",
        request: Any | None = None,
    ) -> OrderResponse:
        """Place an order through the service layer.

        .. deprecated::
            Use ``session.orders.place_order()`` via :class:`BrokerSession` instead.
        """
        self._warn_deprecated("place_order")
        return self._order_service.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
            request=request,
        )

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> OrderResponse:
        """Modify an existing order through the service layer.

        .. deprecated::
            Use ``session.orders.modify_order()`` via :class:`BrokerSession` instead.
        """
        self._warn_deprecated("modify_order")
        return self._order_service.modify_order(
            order_id=order_id,
            quantity=quantity,
            price=price,
            order_type=order_type,
            validity=validity,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order through the service layer.

        .. deprecated::
            Use ``session.orders.cancel_order()`` via :class:`BrokerSession` instead.
        """
        self._warn_deprecated("cancel_order")
        return self._order_service.cancel_order(order_id)

    def get_order(self, order_id: str) -> Order | None:
        """Get order details."""
        return self._order_service.get_order(order_id)

    def get_orderbook(self) -> list[Order]:
        """Get all orders."""
        return self._order_service.get_orderbook()

    def get_orders(self) -> list[Order]:
        """Alias for get_orderbook()."""
        return self.get_orderbook()

    # --- Market Data ---

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Get current quote for a symbol.

        .. deprecated::
            Use ``session.market.quote()`` via :class:`BrokerSession` instead.
        """
        self._warn_deprecated("get_quote")
        return self._market_data_service.quote(symbol, exchange)

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Alias for get_quote()."""
        return self.get_quote(symbol, exchange)

    def get_quotes(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        """Get current quotes for multiple symbols natively in bulk."""
        return self._market_data_service.quote_batch(symbols, exchange)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Get last traded price."""
        return self._market_data_service.ltp(symbol, exchange)

    # --- Historical Data ---

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Fetch historical candles through the service layer."""
        return self._historical_service.fetch_candles(
            symbol=symbol,
            exchange=exchange,
            start_time=start_time,
            end_time=end_time,
            resolution=resolution,
        )

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Get last traded prices for multiple symbols natively in bulk."""
        return self._market_data_service.ltp_batch(symbols, exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Get market depth."""
        return self._market_data_service.depth(symbol, exchange)

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str = "NSE",
        interval: str = "1d",
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[Candle]:
        """Get historical candles via the historical service."""
        from datetime import datetime

        if from_date is None or to_date is None:
            return []
        start = datetime.fromisoformat(from_date)
        end = datetime.fromisoformat(to_date)
        return self._historical_service.fetch_candles(
            symbol=symbol,
            exchange=exchange,
            start_time=start,
            end_time=end,
            resolution=interval,
        )

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> Any:
        """Get full option chain for a specific expiry via the options service."""
        return self._options_service.get_option_chain(
            underlying=underlying,
            exchange=exchange,
            expiry=expiry,
        )

    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        """Get available option expiries for an underlying via the options service."""
        return self._options_service.get_expiries(
            underlying=underlying,
            exchange=exchange,
        )

    # --- Portfolio ---

    def get_positions(self) -> list[Position]:
        """Get current positions.

        .. deprecated::
            Use ``session.portfolio.positions()`` via :class:`BrokerSession` instead.
        """
        self._warn_deprecated("get_positions")
        return self._portfolio_service.positions()

    def get_trades(self) -> list[Trade]:
        """Get trade history.

        .. deprecated::
            Use ``session.portfolio.trades()`` via :class:`BrokerSession` instead.
        """
        self._warn_deprecated("get_trades")
        return self._portfolio_service.trades()

    def get_holdings(self) -> list[Holding]:
        """Get holdings.

        .. deprecated::
            Use ``session.portfolio.holdings()`` via :class:`BrokerSession` instead.
        """
        self._warn_deprecated("get_holdings")
        return self._portfolio_service.holdings()

    def get_balance(self) -> Balance:
        """Get account balance.

        .. deprecated::
            Use ``session.portfolio.funds()`` via :class:`BrokerSession` instead.
        """
        self._warn_deprecated("get_balance")
        return self._portfolio_service.funds()

    # --- Instruments ---

    def search_instruments(self, query: str) -> list[InstrumentInfo]:
        """Search for instruments.

        .. deprecated::
            Use ``session.instruments.search()`` via :class:`BrokerSession` instead.
        """
        self._warn_deprecated("search_instruments")
        return self._instrument_service.search(query)

    def get_instrument(self, symbol: str, exchange: str = "NSE") -> InstrumentInfo:
        """Get instrument info by symbol and exchange."""
        result = self._instrument_service.resolve(symbol, exchange)
        if result is None:
            from inc_trade.domain.exceptions import InstrumentNotFoundError

            raise InstrumentNotFoundError(f"Instrument not found: {exchange}:{symbol}")
        return result

    # --- Capabilities ---

    def capabilities(self) -> Any:
        """Get broker capability matrix."""
        return self._gateway.capabilities

    @property
    def extensions(self) -> ExtensionRegistryPort:
        """Access broker-specific capabilities via the extension registry."""
        return self._registry

    @property
    def auth(self) -> Any:
        """Access the authentication service/port."""
        return self._gateway.auth

    @property
    def streaming(self) -> Any:
        """Access the streaming WebSocket service/port."""
        return self._gateway.streaming

    # --- Lifecycle ---

    def close(self) -> None:
        """Close broker connections and cleanup."""
        self._gateway.close()

    # --- Deprecated: Direct gateway access ---

    @property
    def _underlying_gateway(self) -> BrokerGateway:
        """Access the underlying gateway (deprecated).

        This is provided for backward compatibility. New code should
        use the facade methods directly.
        """
        warnings.warn(
            "_underlying_gateway is deprecated. Use facade service methods directly "
            "(e.g. broker.orders, broker.market_data, broker.portfolio).",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._gateway
