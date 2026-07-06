"""DhanAdapter — directly composes Dhan sub-adapters without DhanGateway.

This adapter implements all provider protocols (InstrumentDataProvider,
DepthProvider, HistoricalDataProvider, StreamingDataProvider, OrderProvider)
by composing the existing sub-adapters directly. It does NOT import
DhanGateway, breaking the gateway indirection layer.

Usage::

    adapter = DhanAdapter(client_id="123", access_token="abc")
    adapter.connect()

    # Use as provider with BrokerSession
    session = BrokerSession(adapter)
    await session.connect()

    rel = session.equity("RELIANCE")
    query = session.query(rel)
    print(query.ltp())
    print(query.depth(200))
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from brokers_core.domain.entities import Candle, MarketDepth, OptionChain, Quote
from brokers_core.domain.enums import BrokerID, OrderType, ProductType, Side, Validity

from brokers_core.adapters.base import ConnectedGuard
from brokers_core.adapters.dhan.auth import DhanAuth
from brokers_core.domain.constants.broker_ids import DHAN_ID
from brokers_core.adapters.dhan.config import ENDPOINTS
from brokers_core.adapters.dhan.connection_manager import DhanConnectionManager
from brokers_core.adapters.dhan.depth20 import DhanDepth20Stream
from brokers_core.adapters.dhan.depth200 import DhanDepth200Stream
from brokers_core.adapters.dhan.historical import DhanHistorical
from brokers_core.adapters.dhan.http_client import create_dhan_http_client
from brokers_core.adapters.dhan.identity import DhanInstrumentResolver
from brokers_core.adapters.dhan.market_data import DhanMarketData
from brokers_core.adapters.dhan.options import DhanOptions
from brokers_core.adapters.dhan.orders import DhanOrders
from brokers_core.adapters.dhan.streaming import DhanStreaming

if TYPE_CHECKING:
    from collections.abc import Callable

    from brokers_core.ports.event_publisher import EventPublisherPort
    from brokers_core.ports.risk_manager import RiskManagerPort
    from brokers_core.ports.token_store import TokenStorePort

logger = logging.getLogger(__name__)


class DhanAdapter(ConnectedGuard):
    """Dhan broker adapter — implements provider protocols directly.

    Composes Dhan sub-adapters without using the DhanGateway facade.

    Args:
        client_id: Dhan client ID.
        access_token: Pre-configured access token (skips TOTP if provided).
        pin: Trading PIN for TOTP login.
        totp_secret: TOTP secret for token generation.
        allow_live_orders: Enable live order placement (kill switch).
        env_path: Path to .env file for token persistence.
        token_state_dir: Directory for JSON token state persistence.
        auto_refresh: Enable background token refresh scheduler.
        refresh_interval_seconds: How often to check token validity.
        refresh_buffer_seconds: Refresh if token expires within this window.
        event_bus: Optional event bus for domain events.
        risk_manager: Optional risk manager for order validation.
        token_store: Optional externally-provided token store.

    Capabilities:
        - Market data: LTP, quote, batch quotes
        - Depth: 20-level (50 instr/conn), 200-level (1 instr/conn)
        - Historical: OHLCV candles
        - Streaming: WebSocket real-time ticks
        - Orders: Place, modify, cancel
        - Max depth levels: 200
    """

    broker_id: str = DHAN_ID

    def __init__(
        self,
        client_id: str | None = None,
        access_token: str | None = None,
        pin: str | None = None,
        totp_secret: str | None = None,
        allow_live_orders: bool = False,
        env_path: str | Path | None = None,
        token_state_dir: str | Path | None = None,
        auto_refresh: bool = True,
        refresh_interval_seconds: int = 60,
        refresh_buffer_seconds: float = 300.0,
        event_bus: EventPublisherPort | None = None,
        risk_manager: RiskManagerPort | None = None,
        token_store: TokenStorePort | None = None,
    ) -> None:
        self._client_id = client_id
        self._access_token = access_token
        self._pin = pin
        self._totp_secret = totp_secret
        self._allow_live_orders = allow_live_orders
        self._env_path = Path(env_path) if env_path else None
        self._token_state_dir = Path(token_state_dir) if token_state_dir else None
        self._auto_refresh = auto_refresh
        self._refresh_interval_seconds = refresh_interval_seconds
        self._refresh_buffer_seconds = refresh_buffer_seconds
        self._event_bus = event_bus
        self._risk_manager = risk_manager
        self._token_store = token_store

        # Lazy-initialized sub-adapters
        self._auth: DhanAuth | None = None
        self._resolver: DhanInstrumentResolver | None = None
        self._http_client: Any = None
        self._market_data: DhanMarketData | None = None
        self._orders: DhanOrders | None = None
        self._options: DhanOptions | None = None
        self._historical: DhanHistorical | None = None
        self._streaming: DhanStreaming | None = None
        self._depth20_stream: DhanDepth20Stream | None = None
        self._depth200_stream: DhanDepth200Stream | None = None
        self._conn_mgr: DhanConnectionManager | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Authenticate, create HTTP client, and initialize all sub-adapters.

        Steps:
        1. Create DhanAuth for token management (handles TOTP or static token)
        2. Create HTTP client with token refresh support
        3. Create DhanInstrumentResolver (loads master CSV)
        4. Create DhanConnectionManager for token lifecycle
        5. Create market data, orders, historical sub-adapters
        6. Create streaming adapter
        """
        # Step 1: Auth — DhanAuth.__init__() handles token acquisition
        self._auth = DhanAuth(
            access_token=self._access_token,
            client_id=self._client_id,
            pin=self._pin,
            totp_secret=self._totp_secret,
            token_store=self._token_store,
        )
        if not self._auth.is_authenticated():
            raise RuntimeError(
                "DhanAuth could not acquire a token. Provide access_token, "
                "or pin+totp_secret for TOTP generation."
            )

        access_token: str = self._auth.get_token() or ""

        # Step 2: Instrument resolver (loads master CSV)
        self._resolver = DhanInstrumentResolver()
        self._resolver.load()

        # Step 3: HTTP client with token refresh support
        self._http_client = create_dhan_http_client(
            client_id=self._client_id or "",
            access_token=access_token,
        )

        # Step 4: Connection manager for token lifecycle
        self._conn_mgr = DhanConnectionManager(
            auth=self._auth,
            client_id=self._client_id or "",
            pin=self._pin,
            totp_secret=self._totp_secret,
            token_store=self._token_store,
            env_path=self._env_path,
            token_state_dir=self._token_state_dir,
            auto_refresh=self._auto_refresh,
            refresh_interval_seconds=self._refresh_interval_seconds,
            refresh_buffer_seconds=self._refresh_buffer_seconds,
        )

        # Step 5: Sub-adapters for market data, orders, historical
        self._market_data = DhanMarketData(
            client=self._http_client,
            resolver=self._resolver,
        )

        self._orders = DhanOrders(
            client=self._http_client,
            resolver=self._resolver,
            event_bus=self._event_bus,
            risk_manager=self._risk_manager,
        )

        self._historical = DhanHistorical(
            client=self._http_client,
            resolver=self._resolver,
        )

        # Step 6: Streaming adapter (lazy — starts on first subscribe)
        self._options = DhanOptions(
            client=self._http_client,
            resolver=self._resolver,
        )

        self._streaming = DhanStreaming(
            access_token=access_token,
            client_id=self._client_id or "",
            resolver=self._resolver,
        )

        self._connected = True
        logger.info(
            "DhanAdapter connected (client_id=%s, max_depth=200)",
            self._client_id,
        )

    def disconnect(self) -> None:
        """Close streaming, depth feeds, and HTTP client."""
        if self._streaming is not None:
            try:
                self._streaming.stop()
            except Exception:
                pass
        if self._depth20_stream is not None:
            try:
                self._depth20_stream.stop()
            except Exception:
                pass
        if self._depth200_stream is not None:
            try:
                self._depth200_stream.stop()
            except Exception:
                pass
        if self._conn_mgr is not None:
            try:
                self._conn_mgr.close()
            except Exception:
                pass
        if self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass
        self._connected = False
        self._market_data = None
        self._orders = None
        self._options = None
        self._historical = None
        self._streaming = None
        self._depth20_stream = None
        self._depth200_stream = None
        self._auth = None
        self._resolver = None
        self._http_client = None
        self._conn_mgr = None
        logger.info("DhanAdapter disconnected (client_id=%s)", self._client_id)



    # ── InstrumentDataProvider ────────────────────────────────────────────

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        self._require_connected()
        return self._market_data.quote(symbol, exchange)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        self._require_connected()
        return self._market_data.ltp(symbol, exchange)

    def depth(self, symbol: str, exchange: str = "NSE", levels: int = 5) -> MarketDepth:
        """Get market depth with requested levels.

        Delegates to ``DhanMarketData.depth()`` which returns 5-level
        snapshot depth. For 20 or 200-level streaming depth, use
        ``depth20()`` or ``depth200()`` directly or apply
        ``Depth20Decorator``/``Depth200Decorator``.
        """
        self._require_connected()
        return self._market_data.depth(symbol, exchange)

    def quote_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
    ) -> dict[str, Quote]:
        self._require_connected()
        return self._market_data.quote_batch(symbols, exchange)

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        """Fetch full option chain via Dhan API."""
        self._require_connected()
        if expiry is None:
            expiries = self._options.get_expiries(underlying, exchange)
            if not expiries:
                return OptionChain(
                    underlying=underlying,
                    expiry="",
                    spot=Decimal("0"),
                    strikes=(),
                )
            expiry = expiries[0]
        return self._options.get_option_chain(underlying, exchange, expiry)

    # ── DepthProvider ─────────────────────────────────────────────────────

    @property
    def max_levels(self) -> int:
        return 200

    # ── HistoricalDataProvider ────────────────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        resolution: str,
    ) -> list[Candle]:
        self._require_connected()
        return self._historical.get_historical_candles(
            symbol=symbol,
            exchange=exchange,
            start_time=start,
            end_time=end,
            resolution=resolution,
        )

    # ── StreamingDataProvider ─────────────────────────────────────────────

    def subscribe(self, instrument: Any, callback: Callable[..., Any]) -> Any:
        self._require_connected()

        # Extract symbol/exchange from instrument
        symbol: str | None = getattr(instrument, "symbol", None)
        exchange: str | None = getattr(instrument, "exchange", None)
        if symbol is None or exchange is None:
            raise ValueError(f"Instrument must have symbol and exchange: {instrument}")

        # Start streaming if not already running
        if not self._streaming.is_connected:
            self._streaming.start()

        # Register callback — DhanStreaming uses on_tick for all ticks
        original_on_tick = self._streaming.on_tick

        def _tick_handler(tick: Any) -> None:
            if original_on_tick is not None:
                original_on_tick(tick)
            callback(tick)

        self._streaming.on_tick = _tick_handler
        self._streaming.subscribe(symbol, exchange)

        # Return a handle for unsubscription
        return _StreamHandle(self._streaming, symbol, exchange)

    def unsubscribe(self, instrument: Any) -> None:
        self._require_connected()
        symbol: str | None = getattr(instrument, "symbol", None)
        exchange: str | None = getattr(instrument, "exchange", None)
        if symbol is not None and exchange is not None:
            self._streaming.unsubscribe(symbol, exchange)

    # ── OrderProvider ─────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any:
        self.require_connected()
        ot = order_type or OrderType.MARKET
        return self._orders.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            order_type=ot,
            price=price,
            trigger_price=trigger_price,
            product_type=kwargs.get("product_type", ProductType.INTRADAY),
            validity=kwargs.get("validity", Validity.DAY),
        )

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> Any:
        self._require_connected()
        return self._orders.modify_order(
            order_id=order_id,
            quantity=quantity,
            price=price,
        )

    def cancel_order(self, order_id: str) -> Any:
        self._require_connected()
        return self._orders.cancel_order(order_id)

    def instrument(self, symbol: str, exchange: str, **kwargs: Any) -> Any:
        """Create an Instrument with this adapter injected as provider."""
        from brokers_core.market.factory import InstrumentFactory

        if "apply_depth" not in kwargs:
            kwargs["apply_depth"] = 200
        return InstrumentFactory.create(
            symbol=symbol,
            exchange=exchange,
            provider=self,
            depth_provider=self,
            historical_provider=self,
            streaming_provider=self,
            order_provider=self,
            **kwargs,
        )

    # ── Depth Extension Methods ───────────────────────────────────────────

    def get_depth20(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Get 20-level streaming depth.

        Creates a ``DhanDepth20Stream`` if not already active.
        Max 50 instruments per connection.
        """
        self._require_connected()
        if self._depth20_stream is None:
            token = self._get_token()
            self._depth20_stream = DhanDepth20Stream(
                access_token=token,
                client_id=self._client_id or "",
                resolver=self._resolver,
                event_bus=self._event_bus,
            )
        self._depth20_stream.subscribe(symbol, exchange)
        # Return the latest depth snapshot
        return self._market_data.depth(symbol, exchange)

    def get_depth200(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Get 200-level streaming depth.

        Creates a ``DhanDepth200Stream`` if not already active.
        CRITICAL: Only 1 instrument per connection.
        """
        self._require_connected()
        if self._depth200_stream is None:
            token = self._get_token()
            self._depth200_stream = DhanDepth200Stream(
                access_token=token,
                client_id=self._client_id or "",
                resolver=self._resolver,
                instrument=(symbol, exchange),
                event_bus=self._event_bus,
            )
        self._depth200_stream.subscribe(symbol, exchange)
        return self._market_data.depth(symbol, exchange)

    # ── Internals ─────────────────────────────────────────────────────────

    def _require_connected(self) -> None:
        self.require_connected()
        if self._market_data is None:
            raise RuntimeError("DhanAdapter not connected. Call adapter.connect() first.")

    def _get_token(self) -> str:
        """Get current access token from auth."""
        if self._auth is None:
            return self._access_token or ""
        return self._auth.get_token() or ""

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"DhanAdapter(client_id={self._client_id}, status={status})"


class _StreamHandle:
    """Simple subscription handle returned by ``subscribe()``.

    Calling ``unsubscribe()`` on this handle removes the callback from
    the streaming adapter.
    """

    def __init__(
        self,
        streaming: DhanStreaming,
        symbol: str,
        exchange: str,
    ) -> None:
        self._streaming = streaming
        self._symbol = symbol
        self._exchange = exchange
        self._active = True

    def unsubscribe(self) -> None:
        if self._active:
            self._streaming.unsubscribe(self._symbol, self._exchange)
            self._active = False

    @property
    def is_active(self) -> bool:
        return self._active
