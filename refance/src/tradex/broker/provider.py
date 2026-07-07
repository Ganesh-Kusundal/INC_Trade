"""Provider SPI — the abstract interface every broker must implement.

This is the most important file in the SDK.
Every broker-specific implementation derives from these interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional

from tradex.core.health import HealthReport
from tradex.domain.account import AccountProfile, FundLimits
from tradex.domain.enums import OrderType, ProductType, Side, Validity
from tradex.domain.execution import Order, Trade
from tradex.domain.mapping import InstrumentMapper
from tradex.domain.market_data import (
    OHLCV,
    MarketDepth,
    OptionChain,
    Quote,
)
from tradex.domain.portfolio import Holding, Position


class AuthProvider(ABC):
    """Authentication provider interface.

    Defines the contract for broker authentication. Every broker
    provider must implement this interface to handle login,
    token management, and session lifecycle.

    Implementations should handle:
    - Initial authentication with credentials
    - Token refresh before expiry
    - Session state tracking
    - Profile fetching
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish an authenticated session with the broker.

        Validates credentials, creates an access token, and
        transitions the session to CONNECTED state.

        Raises:
            AuthenticationError: If credentials are invalid.
            NetworkError: If the broker is unreachable.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down the authenticated session.

        Releases tokens and transitions to DISCONNECTED state.
        Safe to call multiple times.
        """

    @abstractmethod
    async def refresh_token(self) -> None:
        """Refresh the access token before expiry.

        Typically called automatically by the auth manager.
        Implementations should update the stored token.

        Raises:
            SessionExpiredError: If the refresh token itself is expired.
        """

    @abstractmethod
    async def is_authenticated(self) -> bool:
        """Check if the session is currently authenticated.

        Returns:
            True if a valid, non-expired token exists.
        """

    @abstractmethod
    async def get_profile(self) -> AccountProfile:
        """Fetch the broker account profile.

        Returns:
            AccountProfile with client details, active segments,
            and feature flags (DDPI, MTF, data plan).

        Raises:
            AuthenticationError: If not authenticated.
        """


class ExecutionProvider(ABC):
    """Order execution provider interface.

    Defines the contract for order management. Implementations
    handle order placement, modification, cancellation, and
    retrieval of orders and trades.
    """

    @abstractmethod
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
        """Place a new order with the broker.

        Args:
            security_id: Broker-assigned security ID.
            exchange_segment: Exchange segment (e.g., "NSE_EQ").
            side: BUY or SELL.
            quantity: Number of shares or lots.
            order_type: LIMIT, MARKET, STOP_LOSS, or STOP_LOSS_MARKET.
            product_type: CNC, INTRADAY, MARGIN, or MTF.
            price: Limit price. Required for LIMIT orders.
            trigger_price: Trigger price for SL/SLM orders.
            disclosed_quantity: Quantity to show in order book.
            after_market_order: Whether this is an AMO.
            validity: DAY (default) or IOC.
            tag: User-defined correlation ID.

        Returns:
            Order with broker-assigned order_id.

        Raises:
            ValidationError: If order parameters are invalid.
            OrderError: If broker rejects the order.
            RateLimitError: If rate limit is exceeded.
        """

    @abstractmethod
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
        """Modify an existing pending or open order.

        Args:
            order_id: The order to modify.
            order_type: New order type.
            quantity: New quantity.
            price: New limit price.
            trigger_price: New trigger price.
            disclosed_quantity: New disclosed quantity.
            validity: New validity.

        Returns:
            Updated Order object.

        Raises:
            OrderError: If the order cannot be modified.
            ValidationError: If new parameters are invalid.
        """

    @abstractmethod
    async def cancel_order(self, order_id: str) -> None:
        """Cancel an active order.

        Args:
            order_id: The broker-assigned order ID to cancel.

        Raises:
            OrderError: If cancel is rejected by the broker.
        """

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        """Get order details by ID.

        Args:
            order_id: The broker-assigned order ID.

        Returns:
            Order with current status and fill details.

        Raises:
            OrderError: If the order ID is not found.
        """

    @abstractmethod
    async def get_orders(self) -> list[Order]:
        """Get all orders for the current session.

        Returns:
            List of all orders (pending, active, filled, cancelled).
        """

    @abstractmethod
    async def get_trades(self, order_id: Optional[str] = None) -> list[Trade]:
        """Get executed trades, optionally filtered by order ID.

        Args:
            order_id: If provided, return only trades for this order.

        Returns:
            List of Trade objects.
        """

    @abstractmethod
    async def get_trade_history(self, start_date: str, end_date: str, page: int = 0) -> list[Trade]:
        """Get trade history for a date range.

        Args:
            start_date: Start date in ISO format (YYYY-MM-DD).
            end_date: End date in ISO format (YYYY-MM-DD).
            page: Page number for pagination.

        Returns:
            List of Trade objects in the date range.
        """


class MarketDataProvider(ABC):
    """Market data provider interface.

    Defines the contract for market data retrieval. Implementations
    handle quotes, historical data, option chains, and depth.
    """

    @abstractmethod
    async def get_quote(self, security_id: str, exchange: str) -> Quote:
        """Get a real-time quote snapshot.

        Args:
            security_id: Broker-assigned security ID.
            exchange: Exchange segment string.

        Returns:
            Quote with full market data.
        """

    @abstractmethod
    async def get_quotes(self, securities: dict[str, list[str]]) -> dict[str, dict[str, Quote]]:
        """Get quotes for multiple instruments in a single call.

        Args:
            securities: {exchange_segment: [security_id, ...]}.

        Returns:
            Nested dict: {exchange: {security_id: Quote}}.
        """

    @abstractmethod
    async def get_ohlcv(
        self,
        security_id: str,
        exchange: str,
        instrument_type: str,
        start_date: str,
        end_date: str,
        expiry_code: int = 0,
        include_oi: bool = False,
    ) -> list[OHLCV]:
        """Get historical daily OHLCV data.

        Args:
            security_id: Broker security ID.
            exchange: Exchange segment string.
            instrument_type: Instrument type string (EQUITY, FUTIDX, etc.).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            expiry_code: Expiry code for derivatives (0=nearest).
            include_oi: Whether to include open interest.

        Returns:
            List of OHLCV candles sorted by timestamp.
        """

    @abstractmethod
    async def get_minute_data(
        self,
        security_id: str,
        exchange: str,
        instrument_type: str,
        start_date: str,
        end_date: str,
        interval: int = 1,
        include_oi: bool = False,
    ) -> list[OHLCV]:
        """Get intraday minute-level OHLCV data.

        Args:
            security_id: Broker security ID.
            exchange: Exchange segment string.
            instrument_type: Instrument type string.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            interval: Candle interval in minutes (1, 5, 15, 30).
            include_oi: Whether to include open interest.

        Returns:
            List of OHLCV candles.
        """

    @abstractmethod
    async def get_option_chain(
        self,
        underlying_security_id: str,
        exchange: str,
        expiry: str,
    ) -> OptionChain:
        """Get the full option chain for an underlying.

        Args:
            underlying_security_id: Security ID of the underlying.
            exchange: Exchange segment string.
            expiry: Expiry date in ISO format.

        Returns:
            OptionChain with all strikes and quotes.
        """

    @abstractmethod
    async def get_expiry_list(self, underlying_security_id: str, exchange: str) -> list[str]:
        """Get available expiry dates for an underlying.

        Args:
            underlying_security_id: Security ID of the underlying.
            exchange: Exchange segment string.

        Returns:
            List of expiry date strings (YYYY-MM-DD), sorted nearest first.
        """

    @abstractmethod
    async def get_depth(self, security_id: str, exchange: str) -> MarketDepth:
        """Get market depth (order book) for an instrument.

        Args:
            security_id: Broker security ID.
            exchange: Exchange segment string.

        Returns:
            MarketDepth with bid/ask levels.
        """


class PortfolioProvider(ABC):
    """Portfolio provider interface.

    Defines the contract for portfolio management. Implementations
    handle holdings, positions, fund limits, and margin calculation.
    """

    @abstractmethod
    async def get_holdings(self) -> list[Holding]:
        """Get portfolio holdings (demat delivery positions).

        Returns:
            List of Holding objects.
        """

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get current intraday and margin positions.

        Returns:
            List of Position objects (open and closed).
        """

    @abstractmethod
    async def get_fund_limits(self) -> FundLimits:
        """Get fund limits and available margin.

        Returns:
            FundLimits with balance breakdown.
        """

    @abstractmethod
    async def calculate_margin(
        self,
        security_id: str,
        exchange: str,
        side: Side,
        quantity: int,
        product_type: ProductType,
        price: float,
        trigger_price: float = 0,
    ) -> dict[str, Any]:
        """Calculate margin required for a potential order.

        Args:
            security_id: Broker security ID.
            exchange: Exchange segment string.
            side: BUY or SELL.
            quantity: Number of shares or lots.
            product_type: CNC, INTRADAY, MARGIN, or MTF.
            price: Order price.
            trigger_price: Trigger price for SL orders.

        Returns:
            Dict with 'sufficient', 'total_margin', 'available_balance'.
        """


class StreamingProvider(ABC):
    """Streaming data provider interface.

    Defines the contract for real-time WebSocket data streaming.
    Implementations handle connection, subscription, and tick
    data delivery.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the streaming WebSocket.

        Establishes a persistent WebSocket connection for
        real-time market data.

        Raises:
            StreamError: If connection fails.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the streaming WebSocket.

        Closes the WebSocket and releases resources. Safe to
        call multiple times.
        """

    @abstractmethod
    async def subscribe(self, instruments: list[tuple[str, str, int]]) -> None:
        """Subscribe to real-time data for instruments.

        Args:
            instruments: List of (exchange, security_id, subscription_type)
                tuples. Subscription types: 15 (Ticker), 17 (Quote),
                19 (Depth), 21 (Full).
        """

    @abstractmethod
    async def unsubscribe(self, instruments: list[tuple[str, str, int]]) -> None:
        """Unsubscribe from real-time data for instruments.

        Args:
            instruments: List of (exchange, security_id, subscription_type)
                tuples to unsubscribe from.
        """

    @abstractmethod
    async def ticks(self) -> AsyncIterator[dict[str, Any]]:
        """Async iterator yielding raw tick data.

        Yields:
            Raw tick dictionaries from the broker's WebSocket.
        """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the WebSocket is currently connected.

        Returns:
            True if the streaming connection is active.
        """


class BrokerProvider(ABC):
    """Main broker provider interface.

    Every broker implementation must implement this interface.
    It composes the sub-providers and manages the overall lifecycle.

    Attributes:
        name: Broker name identifier.
        auth: Authentication provider.
        execution: Order execution provider.
        market_data: Market data provider.
        portfolio: Portfolio provider.
        streaming: Streaming data provider.
        mapper: Instrument mapper.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Broker name (e.g., 'dhan', 'upstox', 'zerodha').

        Returns:
            Unique broker identifier string.
        """

    @abstractmethod
    async def connect(self) -> None:
        """Initialize the broker connection and authenticate.

        Sets up all sub-providers, establishes the session,
        and loads the security master.

        Raises:
            AuthenticationError: If credentials are invalid.
            ConfigurationError: If required config is missing.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up all connections and release resources.

        Closes streaming connections, revokes tokens, and
        transitions all sub-providers to disconnected state.
        """

    @abstractmethod
    async def health(self) -> HealthReport:
        """Get health status of all platform components.

        Returns:
            HealthReport with per-component status.
        """

    @property
    @abstractmethod
    def auth(self) -> AuthProvider:
        """Authentication provider for session management."""

    @property
    @abstractmethod
    def execution(self) -> ExecutionProvider:
        """Order execution provider for trading operations."""

    @property
    @abstractmethod
    def market_data(self) -> MarketDataProvider:
        """Market data provider for quotes and history."""

    @property
    @abstractmethod
    def portfolio(self) -> PortfolioProvider:
        """Portfolio provider for holdings and positions."""

    @property
    @abstractmethod
    def streaming(self) -> StreamingProvider:
        """Streaming data provider for real-time feeds."""

    @property
    @abstractmethod
    def mapper(self) -> InstrumentMapper:
        """Instrument mapper for symbol resolution."""

    @abstractmethod
    async def get_capabilities(self) -> list[str]:
        """List supported broker capabilities.

        Returns:
            List of capability name strings (e.g., 'super_orders',
            'depth_200', 'slice_orders').
        """
