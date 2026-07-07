"""BrokerPlatform — the public API entry point.

Users interact with the SDK exclusively through this class.
It provides a clean, broker-agnostic interface to all functionality.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, AsyncIterator, Optional

from tradex.broker.provider import BrokerProvider
from tradex.core.events import DomainEvent, EventBus
from tradex.core.health import HealthReport
from tradex.core.logging_config import get_logger, setup_logging
from tradex.domain.account import FundLimits
from tradex.domain.enums import (
    Exchange,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from tradex.domain.execution import ForeverOrder, Order, SuperOrder, Trade
from tradex.domain.instruments import Instrument
from tradex.domain.market_data import (
    OHLCV,
    MarketDepth,
    OptionChain,
    Quote,
)
from tradex.domain.portfolio import Holding, Position

logger = get_logger("platform")


class BrokerPlatform:
    """The unified trading platform interface.

    This is the ONLY class users need to interact with.
    It delegates to the appropriate broker provider internally.

    The BrokerPlatform provides a clean, broker-agnostic facade over
    the broker-specific Provider SPI. All user interactions — from
    instrument resolution to order placement to portfolio queries —
    flow through this single entry point.

    Attributes:
        _provider: The underlying broker provider (e.g., DhanProvider).
        _connected: Whether the platform is currently connected.
        _event_bus: Internal event bus for domain events.

    Usage:
        provider = DhanProvider(client_id="...", access_token="...")
        platform = BrokerPlatform(provider)
        await platform.connect()

        # Everything else goes through platform
        quote = await platform.get_quote("RELIANCE")
        order = await platform.place_order(...)

        await platform.disconnect()

    Raises:
        ConfigurationError: If provider credentials are missing.
        AuthenticationError: If authentication fails on connect.
    """

    def __init__(
        self,
        provider: BrokerProvider,
        log_level: str = "INFO",
    ) -> None:
        """Initialize the trading platform.

        Args:
            provider: A broker provider instance (e.g., DhanProvider).
                Must implement the BrokerProvider SPI interface.
            log_level: Logging verbosity. Common values: "DEBUG",
                "INFO", "WARNING", "ERROR". Defaults to "INFO".

        Raises:
            ConfigurationError: If the provider is not properly configured.
        """
        self._provider = provider
        self._connected = False
        self._event_bus = EventBus()

        # Setup logging
        setup_logging(level=log_level, provider=provider.name)

        logger.info("platform_created", provider=provider.name)

    # --- Lifecycle ---

    async def connect(self) -> None:
        """Connect to the broker and authenticate.

        Establishes the connection, validates credentials, and
        initializes the session. Must be called before any other
        platform operations.

        Raises:
            AuthenticationError: If credentials are invalid or expired.
            NetworkError: If the broker is unreachable.
            ConfigurationError: If required config is missing.
        """
        await self._provider.connect()
        self._connected = True

        # Forward provider events to platform event bus
        if hasattr(self._provider, "event_bus"):
            self._provider.event_bus.add_forwarding(self._event_bus)

        logger.info("platform_connected", provider=self._provider.name)

    async def disconnect(self) -> None:
        """Disconnect from the broker.

        Tears down the authenticated session, closes streaming
        connections, and releases resources. Always call this
        when done to avoid resource leaks.

        This method is safe to call multiple times.
        """
        await self._provider.disconnect()
        self._connected = False
        logger.info("platform_disconnected", provider=self._provider.name)

    async def health(self) -> HealthReport:
        """Get health status of all platform components.

        Returns a HealthReport containing the status of auth,
        session, mapper, and other subsystems. Useful for
        monitoring and debugging connectivity issues.

        Returns:
            HealthReport with per-component status and messages.
        """
        return await self._provider.health()

    @property
    def is_connected(self) -> bool:
        """Whether the platform is currently connected to the broker.

        Returns:
            True if connected and authenticated, False otherwise.
        """
        return self._connected

    @property
    def provider_name(self) -> str:
        """Name of the underlying broker provider.

        Returns:
            Broker name string (e.g., "dhan", "upstox").
        """
        return self._provider.name

    @property
    def event_bus(self) -> EventBus:
        """Access the event bus for subscribing to domain events.

        Use this to subscribe to order updates, trade executions,
        or other domain events emitted by the platform.

        Returns:
            The platform's EventBus instance.
        """
        return self._event_bus

    # --- Instrument Resolution ---

    async def resolve_instrument(
        self,
        symbol: str,
        exchange: Exchange = Exchange.NSE,
    ) -> Optional[Instrument]:
        """Resolve a trading symbol to an Instrument object.

        Looks up the symbol in the broker's security master and
        returns a fully populated Instrument with security ID,
        lot size, tick size, and exchange segment.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE", "TCS", "NIFTY").
                Case-insensitive.
            exchange: Target exchange. Defaults to Exchange.NSE.
                Use Exchange.BSE for BSE-listed instruments.

        Returns:
            An Instrument object if found, or None if the symbol
            could not be resolved.

        Raises:
            NetworkError: If the security master cannot be fetched.
        """
        mapping = await self._provider.mapper.resolve_by_symbol(symbol, exchange)
        if mapping:
            return Instrument(
                security_id=mapping.broker_security_id,
                trading_symbol=mapping.canonical_symbol,
                display_symbol=mapping.extra.get("custom_symbol", symbol),
                exchange=mapping.canonical_exchange,
                instrument_type=mapping.instrument_type,
                lot_size=mapping.lot_size,
                tick_size=Decimal(str(mapping.tick_size)),
            )
        return None

    async def search_instruments(
        self,
        symbol: str,
        exchange: Exchange = Exchange.NSE,
    ) -> list[Instrument]:
        """Search for instruments matching a symbol pattern.

        Returns all instruments whose symbol or display name
        contains the search string. Useful for autocomplete
        or fuzzy lookup.

        Args:
            symbol: Partial or full symbol to search for.
            exchange: Exchange to search in. Defaults to Exchange.NSE.

        Returns:
            List of matching Instrument objects. May be empty if
            no matches are found.
        """
        results = await self._provider.mapper.search(symbol, exchange)
        return [
            Instrument(
                security_id=m.broker_security_id,
                trading_symbol=m.canonical_symbol,
                exchange=m.canonical_exchange,
                instrument_type=m.instrument_type,
                lot_size=m.lot_size,
            )
            for m in results
        ]

    # --- Execution ---

    async def place_order(
        self,
        instrument: Instrument,
        side: Side,
        order_type: OrderType,
        product_type: ProductType,
        quantity: int,
        price: float = 0.0,
        trigger_price: float = 0.0,
        disclosed_quantity: int = 0,
        after_market_order: bool = False,
        validity: Validity = Validity.DAY,
        tag: str = "",
    ) -> Order:
        """Place an order.

        Args:
            instrument: The instrument to trade.
            side: BUY or SELL.
            order_type: LIMIT, MARKET, STOP_LOSS, STOP_LOSS_MARKET.
            product_type: CNC, INTRADAY, MARGIN, MTF.
            quantity: Number of shares/lots.
            price: Limit price (required for LIMIT orders).
            trigger_price: Trigger price (required for SL/SLM orders).
            disclosed_quantity: Disclosed quantity.
            after_market_order: Whether this is an AMO.
            validity: DAY or IOC.
            tag: User-defined correlation ID.

        Returns:
            Order object with broker-assigned order ID.
        """
        logger.info(
            "placing_order",
            symbol=instrument.trading_symbol,
            side=side.value,
            type=order_type.value,
            quantity=quantity,
            price=price,
        )

        return await self._provider.execution.place_order(
            security_id=instrument.security_id,
            exchange_segment=instrument.exchange_segment.value,
            side=side,
            quantity=quantity,
            order_type=order_type,
            product_type=product_type,
            price=price,
            trigger_price=trigger_price,
            disclosed_quantity=disclosed_quantity,
            after_market_order=after_market_order,
            validity=validity,
            tag=tag,
        )

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

        Only orders in active states (PENDING, PLACED, OPEN,
        PART_TRADED, TRIGGER_PENDING) can be modified. Terminal
        orders (TRADED, CANCELLED, REJECTED) cannot be modified.

        Args:
            order_id: The broker-assigned order ID to modify.
            order_type: New order type (LIMIT, MARKET, STOP_LOSS,
                STOP_LOSS_MARKET).
            quantity: New quantity in shares or lots.
            price: New limit price. Required for LIMIT orders.
            trigger_price: New trigger price for SL/SLM orders.
            disclosed_quantity: New disclosed quantity.
            validity: New validity (DAY or IOC).

        Returns:
            Updated Order object with the modification.

        Raises:
            OrderError: If the order cannot be modified (e.g., already
                filled or cancelled).
            ValidationError: If the new parameters are invalid.
        """
        return await self._provider.execution.modify_order(
            order_id=order_id,
            order_type=order_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            disclosed_quantity=disclosed_quantity,
            validity=validity,
        )

    async def cancel_order(self, order_id: str) -> None:
        """Cancel an active order.

        Sends a cancel request to the broker. Only active orders
        can be cancelled; terminal orders are silently ignored.

        Args:
            order_id: The broker-assigned order ID to cancel.

        Raises:
            OrderError: If the cancel request is rejected by the broker.
        """
        await self._provider.execution.cancel_order(order_id)

    async def get_order(self, order_id: str) -> Order:
        """Get order details by ID.

        Fetches the current state of an order from the broker,
        including fill status, average price, and any rejection
        reason.

        Args:
            order_id: The broker-assigned order ID.

        Returns:
            Order object with current status and fill details.

        Raises:
            OrderError: If the order ID is not found.
        """
        return await self._provider.execution.get_order(order_id)

    async def get_orders(self) -> list[Order]:
        """Get all orders for the current session.

        Returns a list of all orders placed during the current
        trading session, including pending, active, filled,
        cancelled, and rejected orders.

        Returns:
            List of Order objects. May be empty if no orders
            have been placed.
        """
        return await self._provider.execution.get_orders()

    async def get_trades(self, order_id: Optional[str] = None) -> list[Trade]:
        """Get executed trades, optionally filtered by order ID.

        Retrieves trade (fill) records from the broker. Each trade
        represents a partial or complete execution of an order.

        Args:
            order_id: If provided, return only trades for this order.
                If None, return all trades for the session.

        Returns:
            List of Trade objects with execution details.
        """
        return await self._provider.execution.get_trades(order_id)

    # --- Market Data ---

    async def get_quote(self, instrument: Instrument) -> Quote:
        """Get a real-time quote snapshot for an instrument.

        Returns the latest quote including last price, OHLC, volume,
        bid/ask, and circuit limits. Quote APIs are rate-limited
        to 1 request per second.

        Args:
            instrument: The instrument to get a quote for. Use
                `resolve_instrument()` to convert a symbol.

        Returns:
            Quote object with full market data.

        Raises:
            RateLimitError: If called more than once per second.
            DataError: If market data is unavailable.
        """
        return await self._provider.market_data.get_quote(
            instrument.security_id, instrument.exchange_segment.value
        )

    async def get_quotes(self, instruments: list[Instrument]) -> dict[str, dict[str, Quote]]:
        """Get real-time quotes for multiple instruments in a single call.

        More efficient than calling get_quote() in a loop, as it
        batches the request. Returns a nested dict keyed by
        exchange segment and security ID.

        Args:
            instruments: List of instruments to quote.

        Returns:
            Nested dict: {exchange_segment: {security_id: Quote}}.
        """
        securities: dict[str, list[str]] = {}
        for inst in instruments:
            seg = inst.exchange_segment.value
            if seg not in securities:
                securities[seg] = []
            securities[seg].append(inst.security_id)
        return await self._provider.market_data.get_quotes(securities)

    async def get_history(
        self,
        instrument: Instrument,
        start_date: str,
        end_date: str,
        expiry_code: int = 0,
        include_oi: bool = False,
    ) -> list[OHLCV]:
        """Get historical daily OHLCV data.

        Fetches daily candle data for the given instrument and
        date range. Useful for backtesting, charting, and analysis.

        Args:
            instrument: The instrument to fetch history for.
            start_date: Start date in ISO format (YYYY-MM-DD).
            end_date: End date in ISO format (YYYY-MM-DD).
            expiry_code: Expiry code for derivatives (0 for nearest,
                1 for next, 2 for far). Default 0.
            include_oi: Whether to include open interest data.
                Requires F&O segment. Default False.

        Returns:
            List of OHLCV candles sorted by timestamp ascending.
            May be empty if no data exists for the range.

        Raises:
            DataError: If the date range is invalid or data is
                unavailable.
        """
        return await self._provider.market_data.get_ohlcv(
            security_id=instrument.security_id,
            exchange=instrument.exchange_segment.value,
            instrument_type=instrument.instrument_type.value,
            start_date=start_date,
            end_date=end_date,
            expiry_code=expiry_code,
            include_oi=include_oi,
        )

    async def get_minute_history(
        self,
        instrument: Instrument,
        start_date: str,
        end_date: str,
        interval: int = 1,
        include_oi: bool = False,
    ) -> list[OHLCV]:
        """Get intraday minute-level OHLCV data.

        Fetches minute candles for intraday analysis. Supports
        custom intervals (1, 5, 15, 30 minutes).

        Args:
            instrument: The instrument to fetch data for.
            start_date: Start date in ISO format (YYYY-MM-DD).
            end_date: End date in ISO format (YYYY-MM-DD).
            interval: Candle interval in minutes (1, 5, 15, 30).
                Default 1.
            include_oi: Whether to include open interest data.
                Default False.

        Returns:
            List of OHLCV candles sorted by timestamp ascending.

        Raises:
            DataError: If the interval is not supported or data
                is unavailable.
        """
        return await self._provider.market_data.get_minute_data(
            security_id=instrument.security_id,
            exchange=instrument.exchange_segment.value,
            instrument_type=instrument.instrument_type.value,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            include_oi=include_oi,
        )

    async def get_option_chain(
        self,
        underlying: Instrument,
        expiry: str,
    ) -> OptionChain:
        """Get the full option chain for an underlying.

        Returns all strikes with CE/PE quotes, including LTP,
        OI, IV, and Greeks where available. Use find_atm() on
        the returned chain to locate the ATM strike.

        Args:
            underlying: The underlying instrument (e.g., NIFTY,
                BANKNIFTY). Use BUILTIN_INSTRUMENTS for indices.
            expiry: Expiry date in ISO format (YYYY-MM-DD).
                Use get_expiry_list() to find available dates.

        Returns:
            OptionChain with all strikes and quotes.

        Raises:
            DataError: If the expiry is invalid or chain data
                is unavailable.
        """
        return await self._provider.market_data.get_option_chain(
            underlying_security_id=underlying.security_id,
            exchange=underlying.exchange_segment.value,
            expiry=expiry,
        )

    async def get_expiry_list(self, underlying: Instrument) -> list[str]:
        """Get available expiry dates for an underlying.

        Returns a list of expiry dates in ISO format (YYYY-MM-DD)
        for the given underlying. Use these dates when calling
        get_option_chain().

        Args:
            underlying: The underlying instrument.

        Returns:
            List of expiry date strings, sorted nearest to farthest.
            May be empty if the underlying has no derivatives.
        """
        return await self._provider.market_data.get_expiry_list(
            underlying.security_id, underlying.exchange_segment.value
        )

    async def get_depth(self, instrument: Instrument) -> MarketDepth:
        """Get market depth (order book) for an instrument.

        Returns bid/ask levels with prices, quantities, and order
        counts. Dhan supports up to 20 levels (standard) or 200
        levels (premium data plan).

        Args:
            instrument: The instrument to get depth for.

        Returns:
            MarketDepth with list of DepthLevel entries.
        """
        return await self._provider.market_data.get_depth(
            instrument.security_id, instrument.exchange_segment.value
        )

    # --- Portfolio ---

    async def get_holdings(self) -> list[Holding]:
        """Get portfolio holdings (demat delivery positions).

        Returns all delivery holdings in the demat account,
        including quantity, average cost, and ISIN details.
        Only CNC (delivery) positions appear here.

        Returns:
            List of Holding objects. May be empty if no holdings.
        """
        return await self._provider.portfolio.get_holdings()

    async def get_positions(self) -> list[Position]:
        """Get current intraday and margin positions.

        Returns all open and closed positions for the current
        session, including P&L, average prices, and net quantities.
        For delivery holdings, use get_holdings() instead.

        Returns:
            List of Position objects.
        """
        return await self._provider.portfolio.get_positions()

    async def get_fund_limits(self) -> FundLimits:
        """Get fund limits and available margin.

        Returns the current account balance, utilized margin,
        collateral, and net available funds for trading.

        Returns:
            FundLimits with all balance breakdown fields.
        """
        return await self._provider.portfolio.get_fund_limits()

    async def calculate_margin(
        self,
        instrument: Instrument,
        side: Side,
        quantity: int,
        product_type: ProductType,
        price: float,
        trigger_price: float = 0,
    ) -> dict[str, Any]:
        """Calculate margin required for a potential order.

        Performs a pre-trade margin check without placing an order.
        Useful for validating whether sufficient margin exists
        before submitting an order.

        Args:
            instrument: The instrument to trade.
            side: Order side (BUY or SELL).
            quantity: Number of shares or lots.
            product_type: Margin treatment (CNC, INTRADAY, MARGIN, MTF).
            price: Order price.
            trigger_price: Trigger price for SL orders.

        Returns:
            Dict with margin details including 'sufficient' (bool),
            'total_margin', and 'available_balance'.
        """
        return await self._provider.portfolio.calculate_margin(
            security_id=instrument.security_id,
            exchange=instrument.exchange_segment.value,
            side=side,
            quantity=quantity,
            product_type=product_type,
            price=price,
            trigger_price=trigger_price,
        )

    # --- Super Orders ---

    async def place_super_order(
        self,
        instrument: Instrument,
        side: Side,
        order_type: OrderType,
        product_type: ProductType,
        quantity: int,
        price: float,
        target_price: float,
        stop_loss_price: float,
        trailing_jump: float = 0.0,
        tag: str = "",
    ) -> SuperOrder:
        """Place a super (bracket) order with target and stop-loss.

        A super order automatically places target and stop-loss legs
        after the entry order is filled.

        Args:
            instrument: The instrument to trade.
            side: BUY or SELL.
            order_type: LIMIT, MARKET, etc.
            product_type: CNC, INTRADAY, MARGIN.
            quantity: Number of shares/lots.
            price: Entry price.
            target_price: Target profit price.
            stop_loss_price: Stop-loss price.
            trailing_jump: Trailing stop jump amount.
            tag: User-defined correlation ID.

        Returns:
            SuperOrder with entry, target, and stop-loss legs.
        """
        logger.info(
            "placing_super_order",
            symbol=instrument.trading_symbol,
            side=side.value,
            quantity=quantity,
            target=target_price,
            stop_loss=stop_loss_price,
        )

        return await self._provider.execution.place_super_order(
            security_id=instrument.security_id,
            exchange_segment=instrument.exchange_segment.value,
            side=side,
            quantity=quantity,
            order_type=order_type,
            product_type=product_type,
            price=price,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            trailing_jump=trailing_jump,
            tag=tag,
        )

    async def cancel_super_order(self, order_id: str, order_leg: str) -> None:
        """Cancel a super order or a specific leg.

        Args:
            order_id: The super order ID.
            order_leg: Leg to cancel (ENTRY_LEG, TARGET_LEG, STOP_LOSS_LEG).
        """
        await self._provider.execution.cancel_super_order(order_id, order_leg)

    # --- Forever Orders ---

    async def place_forever_order(
        self,
        instrument: Instrument,
        side: Side,
        product_type: ProductType,
        order_type: OrderType,
        quantity: int,
        price: float,
        trigger_price: float,
        order_flag: str = "SINGLE",
        price1: float = 0.0,
        trigger_price1: float = 0.0,
        quantity1: int = 0,
        tag: str = "",
    ) -> ForeverOrder:
        """Place a forever (GTC) trigger order.

        A forever order stays active until triggered or cancelled,
        unlike regular orders which expire at end of day.

        Args:
            instrument: The instrument to trade.
            side: BUY or SELL.
            product_type: CNC, INTRADAY.
            order_type: LIMIT, MARKET, STOP_LOSS, STOP_LOSS_MARKET.
            quantity: Number of shares/lots.
            price: Order price.
            trigger_price: Trigger price.
            order_flag: SINGLE or OCO.
            price1: Second-leg price (for OCO).
            trigger_price1: Second-leg trigger price (for OCO).
            quantity1: Second-leg quantity (for OCO).
            tag: User-defined correlation ID.

        Returns:
            ForeverOrder object.
        """
        logger.info(
            "placing_forever_order",
            symbol=instrument.trading_symbol,
            side=side.value,
            quantity=quantity,
        )

        return await self._provider.execution.place_forever(
            security_id=instrument.security_id,
            exchange_segment=instrument.exchange_segment.value,
            side=side,
            product_type=product_type,
            order_type=order_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            order_flag=order_flag,
            price1=price1,
            trigger_price1=trigger_price1,
            quantity1=quantity1,
            tag=tag,
        )

    # --- Kill Switch ---

    async def kill_switch(self, status: str = "ON") -> dict[str, Any]:
        """Toggle the kill switch to unwind all open positions.

        WARNING: This is a destructive action that will unwind all
        open positions. Always confirm with the user before activating.

        Args:
            status: "ON" to activate (unwind positions),
                     "OFF" to deactivate.

        Returns:
            Kill switch response data.
        """
        logger.warning("kill_switch_toggled", status=status)
        return await self._provider.execution.kill_switch(status=status)

    # --- eDIS ---

    async def generate_tpin(self) -> dict[str, Any]:
        """Generate TPIN for eDIS authorization.

        Required before selling delivery (CNC) holdings.
        After generating, the user must authorize via the CDSL portal.

        Returns:
            Response data containing the TPIN.
        """
        return await self._provider.portfolio.generate_tpin()

    async def edis_inquiry(self, isin: str) -> dict[str, Any]:
        """Check eDIS authorization status for an ISIN.

        Args:
            isin: The ISIN to check. Pass "ALL" for a broad check.

        Returns:
            Authorization status with fields like status, aprvdQty.
        """
        return await self._provider.portfolio.edis_inquiry(isin)

    # --- Streaming ---

    async def stream_quotes(
        self,
        instruments: list[Instrument],
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream live quotes for instruments via WebSocket.

        Automatically connects to the streaming WebSocket if not
        already connected, subscribes to ticker data for each
        instrument, and yields raw tick dictionaries as they
        arrive.

        Args:
            instruments: List of instruments to stream. Each
                instrument must be resolved first.

        Yields:
            Raw tick dictionaries from the broker's WebSocket.
            Fields vary by broker but typically include security_id,
            last_price, volume, and timestamp.

        Raises:
            StreamError: If the WebSocket connection fails.
        """
        if not self._provider.streaming.is_connected:
            await self._provider.streaming.connect()

        sub = [
            (inst.exchange_segment.value, inst.security_id, 15)  # Ticker
            for inst in instruments
        ]
        await self._provider.streaming.subscribe(sub)

        async for tick in self._provider.streaming.ticks():
            yield tick

    # --- Capabilities & Extensions ---

    @property
    def capabilities(self) -> list[str]:
        """List all supported broker capabilities.

        Capabilities are broker-specific features like super orders,
        forever orders, 200-level depth, etc. Check capabilities
        before using advanced features.

        Returns:
            List of capability name strings.
        """
        return self._provider.capabilities.names

    def has_capability(self, name: str) -> bool:
        """Check if a specific capability is supported by the broker.

        Args:
            name: Capability name (e.g., "super_orders", "depth_200").

        Returns:
            True if the capability is available, False otherwise.
        """
        return self._provider.capabilities.has(name)

    async def execute_extension(self, name: str, **kwargs: Any) -> Any:
        """Execute a broker extension by name.

        Extensions are broker-specific features exposed through
        a generic interface. Use capabilities to check if an
        extension is available before calling it.

        Args:
            name: Extension name (e.g., "super_orders", "kill_switch").
            **kwargs: Extension-specific parameters.

        Returns:
            Extension-specific return value.

        Raises:
            BrokerError: If the extension is not supported or fails.
        """
        return await self._provider.extensions.execute(name, **kwargs)

    # --- Events ---

    def on(self, event_type: type) -> Any:
        """Decorator to subscribe to domain events.

        Use this as a decorator to register handlers for specific
        event types like OrderUpdate, TradeUpdate, etc.

        Args:
            event_type: The domain event class to subscribe to.

        Returns:
            A decorator that registers the handler.

        Example:
            @platform.on(OrderUpdate)
            async def handle_order(event: OrderUpdate):
                print(f"Order {event.order_id} updated")
        """
        return self._event_bus.on(event_type)

    def subscribe_event(self, event_type: type, handler: Any) -> None:
        """Subscribe to an event type with a callback handler.

        Registers a handler function to be called when events of
        the specified type are published.

        Args:
            event_type: The domain event class to subscribe to.
            handler: An async callable that accepts the event.
        """
        self._event_bus.subscribe(event_type, handler)

    async def publish_event(self, event: DomainEvent) -> None:
        """Publish a domain event to all subscribers.

        Publishes an event to the internal event bus, triggering
        all registered handlers for the event's type.

        Args:
            event: The domain event instance to publish.
        """
        await self._event_bus.publish(event)
