"""UpstoxBrokerGateway — thin sync facade delegating to UpstoxBroker adapters.

This class acts as a facade, delegating all operations to specialized adapters:
- MarketDataAdapter: HTTP market data (LTP, Quote, Depth)
- HistoricalAdapter: Historical candle fetching
- StreamManagerAdapter: WebSocket stream management
- PortfolioAdapter: Portfolio, positions, holdings, funds
- OrderCommandAdapter: Order placement, cancellation, modification (via broker.order_command)

Thread Safety:
    All adapters are thread-safe. The facade itself is stateless except for
    delegating to the StreamManagerAdapter which manages subscription state.

Note:
    OrderAdapter was removed as a hollow shim. Gateway now directly calls
    broker.order_command for all order operations.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from brokers.common.batch_mixin import BatchFetchMixin
from brokers.common.broker_port import (
    BrokerHealthSnapshot,
    BrokerStreamHandle,
    BrokerStreamPlan,
    CommonBrokerGateway,
    HistoricalBarRequest,
    QuotaToken,
)
from brokers.common.correlation import resolve_correlation_id
from brokers.common.services.futures import build_future_chain
from brokers.common.identity import BrokerId
from brokers.common.defaults import (
    DEFAULT_DEPTH_TYPE,
    DEFAULT_DERIVATIVES_EXCHANGE,
    DEFAULT_EXCHANGE,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_ORDER_TYPE,
    DEFAULT_PRODUCT_TYPE,
    DEFAULT_SIDE,
    DEFAULT_STREAM_MODE,
    DEFAULT_TIMEFRAME,
    DEFAULT_VALIDITY,
)
from brokers.common.capabilities import CapabilityDescriptor
from brokers.common.gateway import BrokerCapabilities, MarketDataGateway, ObservabilityProvider
from brokers.common.responses import OrderResponseFactory as R
from brokers.upstox.adapters import (
    HistoricalAdapter,
    PortfolioAdapter,
    StreamManagerAdapter,
)
from brokers.upstox.broker import UpstoxBroker
from brokers.upstox.capabilities import upstox_capabilities
from brokers.upstox.extended import UpstoxExtendedCapabilities
from brokers.upstox.mappers.domain_mapper import PROVIDER_IS_AMO
from brokers.upstox.market_data.market_data_adapter import (
    UpstoxMarketDataAdapter as MarketDataAdapter,
)
from domain import (
    Balance,
    DepthLevel,
    ExchangeSegment,
    FutureChain,
    Holding,
    MarketDepth,
    OptionChain,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Side,
    Trade,
    Validity,
)
from brokers.common.adapters.historical_mapper import dataframe_to_historical_bars
from domain.historical import HistoricalBar, InstrumentRef
from domain.requests import ModifyOrderRequest, OrderRequest

logger = logging.getLogger(__name__)


class UpstoxBrokerGateway(BatchFetchMixin, MarketDataGateway, ObservabilityProvider):
    """Unified Upstox broker API. All calls delegate to UpstoxBroker adapters.

    This facade provides a clean public API while internally delegating to
    specialized adapter classes for each responsibility area.

    Thread Safety:
        All delegated operations are thread-safe. Stream management uses
        internal locking in StreamManagerAdapter.

    Example::

        gateway = UpstoxBrokerGateway(broker)
        gateway.load_instruments()
        ltp = gateway.ltp("RELIANCE", "NSE")
        response = gateway.place_order("RELIANCE", "NSE", "BUY", 1)
    """

    def __init__(self, broker: UpstoxBroker):
        """Initialize gateway with broker facade and create adapters.

        Args:
            broker: UpstoxBroker instance with all underlying adapters initialized
        """
        self._broker = broker
        self._gateway_lock = threading.Lock()

        # Initialize specialized adapters
        self._market_data = MarketDataAdapter(
            broker.market_data_v2, broker.market_data_v3, broker.historical_v2
        )
        self._historical = HistoricalAdapter(broker)
        self._stream_manager = StreamManagerAdapter(broker, broker.instrument_resolver)
        self._portfolio = PortfolioAdapter(broker)
        # Direct access to order command — OrderAdapter was a hollow shim
        self._order_command = broker.order_command

        # Broker-agnostic options facade for CLI / tests.
        from brokers.common.options.gateway_facade import GatewayOptionsFacade

        # The facade adapter is only constructed when the broker exposes an
        # ``options`` attribute — tests that build a MagicMock with
        # ``spec=UpstoxBroker`` (which doesn't list ``options``) still
        # construct successfully.
        options_attr = getattr(self._broker, "options", None)
        if options_attr is not None:
            self.options = GatewayOptionsFacade(
                options_attr, exchange_normalize=_upstox_normalize_exchange
            )

    def common_broker_gateway(self) -> CommonBrokerGateway:
        """Native CommonBrokerGateway port for infrastructure bootstrap."""
        adapter = getattr(self, "_cached_common_gateway", None)
        if adapter is None:
            with self._gateway_lock:
                adapter = getattr(self, "_cached_common_gateway", None)
                if adapter is None:
                    adapter = _UpstoxCommonBrokerGateway(self)
                    self._cached_common_gateway = adapter
        return adapter

    # ── Backward compatibility properties (for tests accessing internals) ──

    @property
    def _stream_registry(self) -> dict:
        """Access stream registry from StreamManagerAdapter (backward compat)."""
        return self._stream_manager._stream_registry

    @property
    def _stream_lock(self):
        """Access stream lock from StreamManagerAdapter (backward compat)."""
        return self._stream_manager._stream_lock

    # ── Market Data (ABC-aligned) ─────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Decimal:
        """Fetch last traded price for a symbol.

        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment

        Returns:
            Last traded price as Decimal
        """
        key = self._resolve_instrument_key(symbol, exchange)
        return self._market_data.ltp(key, exchange)

    def quote(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Quote:
        """Fetch full quote with OHLCV for a symbol.

        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment

        Returns:
            Quote dataclass with OHLCV data
        """
        key = self._resolve_instrument_key(symbol, exchange)
        return self._market_data.quote(key, exchange)

    def depth(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> MarketDepth:
        """Fetch order book depth for a symbol.

        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment

        Returns:
            MarketDepth with bid/ask levels
        """
        key = self._resolve_instrument_key(symbol, exchange)
        return self._market_data.depth(key, exchange)

    def get_orderbook(self) -> list[Order]:
        """Fetch current order book.

        Returns:
            List of Order dataclasses
        """
        return self._portfolio.get_orderbook()

    def get_trade_book(self) -> list[Trade]:
        """Get today's trade book from the Upstox V2 trades-for-day endpoint.

        Returns:
            List of Trade dataclasses
        """
        return self._portfolio.get_trades()

    # ── Extended Capabilities ─────────────────────────────────────────

    @property
    def extended(self) -> Any:
        """Access Upstox-specific capabilities beyond MarketDataGateway ABC.

        Returns:
            UpstoxExtendedCapabilities instance with broker-specific methods

        Example::

            ipos = gateway.extended.get_ipos()
            pnl = gateway.extended.get_pnl("INE002A01018")
        """
        return UpstoxExtendedCapabilities(self._broker)

    @property
    def news(self) -> Any:
        """Access news adapter for fetching market/instrument news.

        Returns:
            UpstoxNewsAdapter with get_news() method

        Example::

            items = gateway.news.get_news(category="holdings")
            items = gateway.news.get_news(symbol="RELIANCE")
        """
        return self._broker.news

    # ── Lifecycle ──

    def load_instruments(self, source: str | None = None) -> None:
        """Load instrument definitions from cache or download.

        Args:
            source: Optional path to instrument file. If not provided,
                   uses cached file or downloads from Upstox.
        """
        cache_path = Path(".cache/upstox/complete.json.gz")
        if source:
            path = Path(source)
        else:
            path = self._broker.instrument_loader.download(cache_path)

        start = time.monotonic()
        defs = self._broker.instrument_loader.load(path)
        load_time = time.monotonic() - start
        logger.info(
            "instrument_load_completed",
            extra={
                "count": len(defs),
                "load_time_s": round(load_time, 2),
                "source": source or "cached",
            },
        )

        start = time.monotonic()
        self._broker.instrument_resolver.register_many(defs)
        memory_time = time.monotonic() - start
        logger.info(
            "instrument_memory_load_completed",
            extra={"count": len(defs), "memory_time_s": round(memory_time, 2)},
        )

    def close(self) -> None:
        """Disconnect from broker and cleanup resources."""
        self._broker.disconnect()

    def history(
        self,
        symbol: str | list[str],
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = DEFAULT_TIMEFRAME,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical candles (EOD or Intraday) for a symbol."""
        if isinstance(symbol, list):
            return self.history_batch(
                symbol,
                exchange=exchange,
                timeframe=timeframe,
                lookback_days=lookback_days,
            )
        to_d = date.today()
        from_d = to_d - timedelta(days=lookback_days)
        to_str = to_date or str(to_d)
        from_str = from_date or str(from_d)
        timeframe_str = timeframe.upper() if timeframe else DEFAULT_TIMEFRAME

        # Resolve timeframe to V3 interval
        unit, interval = HistoricalAdapter.resolve_timeframe(timeframe_str)

        try:
            return self._fetch_history(symbol, exchange, from_str, to_str, unit, interval)
        except Exception as exc:
            logger.warning(
                "history_fetch_failed",
                extra={"symbol": symbol, "exchange": exchange, "error": str(exc)},
            )
            return pd.DataFrame()

    def _fetch_history(
        self,
        symbol: str,
        exchange: str,
        from_date: str,
        to_date: str,
        unit: str,
        interval: str,
    ) -> pd.DataFrame:
        """Fetch historical candles for a single symbol.

        Args:
            symbol: Canonical trading symbol
            exchange: Exchange segment
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            unit: Time unit (minutes, hours, days)
            interval: Interval value

        Returns:
            DataFrame with OHLCV data
        """
        from brokers.upstox.auth.exceptions import UpstoxApiError
        try:
            key = self._resolve_instrument_key(symbol, exchange)
            return self._historical.fetch_candles(
                symbol, exchange, key, from_date, to_date, unit, interval
            )
        except UpstoxApiError as e:
            logger.warning("Upstox history API error for symbol %s: %s", symbol, e)
            return pd.DataFrame()
        except Exception as e:
            logger.warning("Failed to fetch history for symbol %s: %s", symbol, e)
            return pd.DataFrame()

    def option_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
        expiry: str | None = None,
    ) -> OptionChain:
        """Get the option chain for an underlying."""
        if expiry is None:
            expiries = self._broker.options.get_expiries(underlying, exchange)
            if not expiries:
                return OptionChain(underlying=underlying, exchange=exchange, expiry="")
            expiry = expiries[0]
        from brokers.common.options.chain_normalizer import upstox_chain_to_canonical

        if hasattr(self._broker.options, "get_option_chain_with_meta"):
            result = self._broker.options.get_option_chain_with_meta(underlying, exchange, expiry)
            if isinstance(result, tuple) and len(result) == 3:
                contracts, raw_rows, _body = result
                return upstox_chain_to_canonical(contracts, raw_rows, underlying, exchange, expiry)
        contracts = self._broker.options.get_option_chain(underlying, exchange, expiry)
        if not isinstance(contracts, list):
            return OptionChain(underlying=underlying, exchange=exchange, expiry=expiry)
        return upstox_chain_to_canonical(contracts, None, underlying, exchange, expiry)

    def future_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
    ) -> FutureChain:
        """Get the future chain for an underlying."""
        futures = getattr(self._broker, "futures", None)
        if futures is None:
            return FutureChain.from_dict(
                {"underlying": underlying, "exchange": exchange}
            )
        return build_future_chain(futures, underlying, exchange)

    def funds(self) -> Balance:
        """Fetch account fund limits.

        Returns:
            Balance dataclass with available margin
        """
        return self._portfolio.get_funds()

    def positions(self) -> list[Position]:
        """Fetch all positions.

        Returns:
            List of Position dataclasses
        """
        return self._portfolio.get_positions()

    def holdings(self) -> list[Holding]:
        """Fetch all holdings.

        Returns:
            List of Holding dataclasses
        """
        return self._portfolio.get_holdings()

    def trades(self) -> list[Trade]:
        """Fetch trade book.

        Returns:
            List of Trade dataclasses
        """
        return self.get_trade_book()

    def describe(self) -> dict:
        """Get broker description metadata.

        Returns:
            Dict with broker capabilities and status
        """
        return {
            "broker": "Upstox",
            "instruments_loaded": self._broker.instrument_resolver.is_loaded()
            if hasattr(self._broker.instrument_resolver, "is_loaded")
            else True,
            "market_data": "available",
            "historical": "available",
            "options": "available",
            "futures": "available",
            "streaming": "available",
        }

    def capabilities(self) -> BrokerCapabilities:
        """Return Upstox broker capability matrix.

        Returns:
            BrokerCapabilities with supported features
        """
        return upstox_capabilities()

    def search(self, query: str) -> list[dict]:
        """Search for instruments by query string.

        Args:
            query: Search query (symbol or name fragment)

        Returns:
            List of matching instrument dicts (max 20)
        """
        results = []
        q = query.upper().strip()
        if hasattr(self._broker.instrument_resolver, "search"):
            defs = self._broker.instrument_resolver.search(q)
            for d in defs:
                dct = d.model_dump() if hasattr(d, "model_dump") else d.dict()
                if not dct.get("symbol") and dct.get("trading_symbol"):
                    dct["symbol"] = dct["trading_symbol"]
                results.append(dct)
        return results[:20]

    def stream(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        mode: str = DEFAULT_STREAM_MODE,
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream for *symbol* on *exchange*.

        The *on_tick* callback receives a canonical :class:`brokers.common.core.domain.Quote`
        object — broker-specific ``instrument_key`` values are never exposed to
        the caller.  If the resolver does not find a definition for the incoming
        key the raw payload dict is forwarded instead so nothing is silently
        dropped.

        Thread-safe: uses ``_stream_lock`` to prevent race conditions during
        connect + subscribe. Callbacks are deduplicated via ``_stream_registry``
        so the same *on_tick* is not registered twice for the same instrument.

        Args:
            symbol:   Canonical trading symbol (e.g. ``"RELIANCE"``)
            exchange: Exchange string (e.g. ``"NSE"``)
            mode:     Subscription mode — ``"ltpc"`` | ``"full"`` | ``"option_greeks"``
            on_tick:  Callable receiving a :class:`Quote` (or raw dict on
                      resolution failure)

        Returns:
            A handle scoped to this subscription — ``stop()``/``disconnect()``
            unsubscribe only this ``(symbol, exchange, on_tick)`` triple via
            :meth:`unstream`, leaving the shared WebSocket connection and any
            other active subscriptions untouched.
        """
        self._stream_manager.subscribe(symbol, exchange, mode, on_tick)

        stream_manager = self._stream_manager

        class LtpStreamHandle:
            def __init__(self, manager: Any, sym: str, exch: str, callback: Any) -> None:
                self._manager = manager
                self._symbol = sym
                self._exchange = exch
                self._on_tick = callback

            def stop(self, timeout: float | None = None) -> None:
                self._manager.unsubscribe(self._symbol, self._exchange, self._on_tick)

            def disconnect(self) -> None:
                self.stop()

        return LtpStreamHandle(stream_manager, symbol, exchange, on_tick)

    def unstream(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        on_tick: Any | None = None,
    ) -> None:
        self._stream_manager.unsubscribe(symbol, exchange, on_tick)

    def stream_order(self, on_order: Any | None = None) -> Any:
        """Subscribe to order updates via Upstox portfolio stream.

        Returns:
            A connection service wrapper that can be stopped/started.
        """
        def portfolio_listener(event_type: str, payload: dict[str, Any]) -> None:
            if event_type == "order" and on_order is not None:
                on_order(payload)

        stream = self._broker.portfolio_stream

        from brokers.common.async_compat import connect_async_then
        if not stream.is_connected:
            def _on_connected() -> None:
                stream.add_listener(portfolio_listener)
            connect_async_then(stream.connect(), _on_connected)
        else:
            stream.add_listener(portfolio_listener)

        class OrderStreamHandle:
            def __init__(self, stream_instance, listener):
                self._stream = stream_instance
                self._listener = listener

            def stop(self, timeout=None):
                self._stream.remove_listener(self._listener)

            def disconnect(self):
                self._stream.remove_listener(self._listener)

        return OrderStreamHandle(stream, portfolio_listener)

    def stream_depth(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        depth_type: str = DEFAULT_DEPTH_TYPE,  # DEPTH_5, DEPTH_30
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Any:
        """Subscribe to Upstox L2 (D5) or L3 (D30) live WebSocket depth ticks."""
        mode = "full_d30" if depth_type == "DEPTH_30" else "full"
        inst_key = self._resolve_instrument_key(symbol, exchange)

        def raw_depth_listener(event_type: str, raw_payload: dict[str, Any]) -> None:
            if event_type == "tick" and on_depth is not None:
                payload = raw_payload.get("payload", {})
                if payload:
                    depth_obj = self._translate_tick_to_depth(payload, symbol)
                    on_depth(depth_obj)

        ws = self._broker.market_data_websocket
        ws.add_listener(raw_depth_listener)

        from brokers.common.async_compat import connect_async_then
        if not ws.is_connected:
            def _on_connected() -> None:
                ws.subscribe([inst_key], mode)
            connect_async_then(ws.connect(), _on_connected)
        else:
            ws.subscribe([inst_key], mode)

        class DepthStreamHandle:
            def __init__(self, ws_instance, listener, key, sub_mode):
                self._ws = ws_instance
                self._listener = listener
                self._key = key
                self._mode = sub_mode

            def stop(self, timeout=None):
                self._ws.remove_listener(self._listener)
                try:
                    self._ws.unsubscribe([self._key])
                except Exception as exc:
                    logger.debug(
                        "unsubscribe_ignored",
                        extra={"key": self._key, "error": str(exc)},
                    )

            def disconnect(self):
                self.stop()

        return DepthStreamHandle(ws, raw_depth_listener, inst_key, mode)

    def _translate_tick_to_depth(self, payload: dict[str, Any], symbol: str) -> MarketDepth:
        """Translate raw depth tick payload to MarketDepth domain model."""
        raw_bids = payload.get("depth", {}).get("bids", [])
        raw_asks = payload.get("depth", {}).get("asks", [])

        bids = [
            DepthLevel(
                price=Decimal(str(b.get("price", 0))),
                quantity=int(b.get("quantity", 0)),
                orders=int(b.get("orders", 0))
            )
            for b in raw_bids
        ]
        asks = [
            DepthLevel(
                price=Decimal(str(a.get("price", 0))),
                quantity=int(a.get("quantity", 0)),
                orders=int(a.get("orders", 0))
            )
            for a in raw_asks
        ]

        depth_len = max(len(bids), len(asks))
        depth_type = "DEPTH_30" if depth_len > 20 else "DEPTH_5"

        from datetime import datetime, timezone
        return MarketDepth(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
            depth_type=depth_type
        )

    # -----------------------------------------------------------------------
    # ObservabilityProvider Implementation
    # -----------------------------------------------------------------------

    def get_connection_status(self) -> dict[str, bool]:
        """Return connection status for Upstox WebSocket streams.

        Implements ObservabilityProvider protocol to expose connection
        status without exposing private attributes to CLI layer.
        """
        status: dict[str, bool] = {}

        ws = getattr(self._broker, "market_data_websocket", None)
        if ws is not None:
            try:
                status["market_data_ws"] = bool(ws.is_connected)
            except Exception:
                status["market_data_ws"] = False

        ps = getattr(self._broker, "portfolio_stream", None)
        if ps is not None:
            try:
                status["portfolio_stream"] = bool(ps.is_connected)
            except Exception:
                status["portfolio_stream"] = False

        return status

    def get_circuit_breaker_states(self) -> dict[str, int]:
        """Return Upstox client circuit breaker states.

        Delegates to the broker's circuit_breaker_states if available.
        Implements ObservabilityProvider protocol.
        """
        cb = getattr(self._broker, "circuit_breaker_states", None)
        if callable(cb):
            try:
                return cb()
            except Exception:
                pass
        elif cb is not None:
            return cb
        return {}

    def get_token_refresh_metrics(self) -> dict[str, int]:
        """Return token refresh metrics from Upstox connection.

        Implements ObservabilityProvider protocol.
        """
        token_refresh = getattr(self._broker, "token_refresh_metrics", None)
        if callable(token_refresh):
            try:
                return token_refresh()
            except Exception:
                pass
        elif token_refresh is not None:
            return token_refresh
        return {"refresh_count": 0, "error_count": 0}

    # ── MarketDataGateway required methods ──

    def place_order(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        side: str = DEFAULT_SIDE,
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str = DEFAULT_ORDER_TYPE,
        product_type: str = DEFAULT_PRODUCT_TYPE,
        validity: str = DEFAULT_VALIDITY,
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
        is_amo: bool = False,
    ) -> OrderResponse:
        """Place an order via Upstox.

        Builds a canonical :class:`OrderRequest` and delegates to the
        order-command adapter, which handles instrument resolution,
        risk checks, idempotency, and payload construction.

        If *correlation_id* is not provided, the current thread's active
        correlation ID (set via :func:`infrastructure.correlation.with_correlation`)
        is used for tracing.

        The OMS owns all pre-submit risk validation; the broker adapter
        enforces its own boundary checks independently.
        """
        # Security guard: prevent live orders if disabled or analytics-only
        if self._broker.settings.analytics_only:
            return R.analytics_blocked()
        if not self._broker.settings.allow_live_orders:
            return R.live_orders_disabled()

        correlation_id = resolve_correlation_id(correlation_id)

        exchange_segment = self._resolve_exchange_segment(exchange, symbol)
        from brokers.common.dtos import BrokerOrderPayload
        request = BrokerOrderPayload(
            symbol=symbol,
            exchange=exchange,
            exchange_segment=exchange_segment,
            transaction_type=Side(side.upper()),
            quantity=quantity,
            price=price,
            trigger_price=trigger_price if trigger_price > Decimal("0") else None,
            order_type=OrderType(order_type.upper()),
            product_type=ProductType(product_type.upper()),
            validity=Validity(validity.upper()),
            correlation_id=correlation_id,
            provider_metadata={PROVIDER_IS_AMO: is_amo},
        )

        try:
            response = self._order_command.place_order(request)
        except Exception as e:
            logger.warning(
                "order_placement_failed",
                extra={
                    "correlation_id": correlation_id,
                    "symbol": symbol,
                    "side": side,
                    "error": str(e),
                },
            )
            return R.fail(str(e))

        # Log failed responses from adapter (risk checks, validation, etc.)
        if not response.success:
            logger.warning(
                "order_placement_rejected",
                extra={
                    "correlation_id": correlation_id,
                    "symbol": symbol,
                    "side": side,
                    "error": response.message,
                },
            )
            return response

        if response.success and correlation_id:
            logger.info(
                "order_placed",
                extra={
                    "correlation_id": correlation_id,
                    "order_id": response.order_id,
                    "symbol": symbol,
                    "side": side,
                },
            )

        return response

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order with post-cancellation verification.

        H1 Critical Fix: After sending cancel request, verifies order actually
        reached cancelled state. Detects race condition where order was filled
        between cancel send and response.

        Returns:
            OrderResponse with success=True if cancelled, or
            OrderResponse.fail with error_code="ALREADY_EXECUTED" if order
            was already filled before cancel could complete.
        """
        # Safety guard: prevent live order cancellations if disabled
        if self._broker.settings.analytics_only:
            return R.analytics_blocked()
        if not self._broker.settings.allow_live_orders:
            return R.live_orders_disabled()

        # Step 1: Send cancel request
        response = self._order_command.cancel_order(order_id)

        # Step 2: Post-cancellation verification (H1 fix)
        if response.success:
            order = self.get_order(order_id)
            if order and order.status in (OrderStatus.FILLED,):
                return R.already_executed(order_id)

        return response

    def get_order(self, order_id: str) -> Order | None:
        """Query a single order by ID via direct lookup.

        Uses the UpstoxOrderQueryAdapter.get_order() method which calls
        the order details endpoint directly, avoiding a full orderbook
        fetch. This halves API calls in cancel_order() verification.

        H1 Critical Fix: Enables post-cancellation verification by allowing
        lookup of individual orders.

        Performance: O(1) single-order fetch instead of O(n) orderbook scan.

        Args:
            order_id: Broker order ID to look up

        Returns:
            Order if found, None if not in orderbook
        """
        order_query = getattr(self._broker, "order_query", None)
        if order_query is not None:
            return order_query.get_order(order_id)
        # Fallback: scan orderbook (backward compat with minimal test mocks)
        orderbook = self.get_orderbook()
        for order in orderbook:
            if order.order_id == order_id:
                return order
        return None

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        """Modify an order via Upstox V3 API."""
        # Safety guard: prevent live order modifications if disabled
        if self._broker.settings.analytics_only:
            return R.analytics_blocked()
        if not self._broker.settings.allow_live_orders:
            return R.live_orders_disabled()

        try:
            result = self._order_command.modify_order(order_id, **changes)
            if isinstance(result, dict) and result.get("status") == "success":
                return R.ok(order_id=order_id, message="Order modified")
            message = (
                result.get("message", "modify failed")
                if isinstance(result, dict)
                else "modify failed"
            )
            return R.fail(message)
        except Exception as exc:
            logger.warning(
                "modify_order_failed",
                extra={"order_id": order_id, "changes": changes, "error": str(exc)},
            )
            return R.fail(str(exc))

    # ── Backward compatibility for internal methods (used by tests) ──

    def _translate_tick_to_quote(self, raw: dict[str, Any]) -> Quote | dict[str, Any]:
        """Translate raw tick to Quote (backward compatibility for tests).

        Delegates to TickTranslatorAdapter via StreamManagerAdapter.

        Args:
            raw: Raw tick payload

        Returns:
            Quote or raw dict
        """
        return self._stream_manager._translate_tick_to_quote(raw)

    @staticmethod
    def _canonical_symbol_for_defn(
        defn: Any,
        fallback_key: str = "",
    ) -> str:
        """Derive canonical symbol from definition (backward compatibility).

        Args:
            defn: Instrument definition
            fallback_key: Fallback instrument key

        Returns:
            Canonical symbol string
        """
        from brokers.upstox.adapters.tick_translator import TickTranslatorAdapter

        return TickTranslatorAdapter._canonical_symbol_for_defn(defn, fallback_key)

    def _resolve_instrument_key(self, symbol: str, exchange: str) -> str:
        """Resolve canonical symbol to Upstox instrument_key.

        Resolution priority:
        1. Hardcoded index mapping (NIFTY, BANKNIFTY, etc.) → NSE_INDEX segment
        2. Instrument master lookup (returns ISIN for equities)
        3. Fallback: construct key from segment|symbol

        Args:
            symbol: Canonical trading symbol (e.g., "RELIANCE", "NIFTY")
            exchange: Exchange segment (e.g., "NSE", "NFO")

        Returns:
            Upstox instrument_key string (e.g., "NSE_EQ|INE002A01018")
        """
        from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
        from config.indices import index_upstox_key

        # 1. Check hardcoded index mapping first
        idx_key = index_upstox_key(symbol)
        if idx_key is not None:
            defn = self._broker.instrument_resolver.resolve(instrument_key=idx_key)
            if defn:
                return defn.instrument_key
            return idx_key

        # 2. Try instrument master lookup
        segment = UpstoxDomainMapper.segment_to_wire(exchange)
        if segment == "NSE":
            segment = "NSE_EQ"
        elif segment == "BSE":
            segment = "BSE_EQ"

        defn = self._broker.instrument_resolver.resolve(
            symbol=symbol,
            exchange_segment=segment,
        )
        if defn:
            return defn.instrument_key

        # 3. Fallback: construct key
        return f"{segment}|{symbol}"

    def _resolve_exchange_segment(self, exchange: str, symbol: str = "") -> ExchangeSegment:
        """Map user-facing exchange string to canonical ExchangeSegment.

        For recognised index symbols (NIFTY, BANKNIFTY, etc.) the segment is
        set to IDX_I regardless of the exchange string.

        Args:
            exchange: User-facing exchange string (e.g., "NSE", "NFO")
            symbol: Optional symbol for index detection

        Returns:
            Canonical ExchangeSegment enum value
        """
        from config.indices import index_upstox_key
        from domain.exchange_segments import parse_segment

        # Index symbols use a dedicated segment
        if symbol and index_upstox_key(symbol) is not None:
            return ExchangeSegment.IDX_I

        parsed = parse_segment(exchange)
        if parsed is None:
            raise ValueError(f"Unknown exchange segment: {exchange!r}")
        return parsed


# ── CommonBrokerGateway Implementation ────────────────────────────────


class _UpstoxStreamHandle:
    """Stream handle for Upstox gateway subscriptions."""

    def __init__(
        self,
        gateway: UpstoxBrokerGateway,
        feed: Any,
        instruments: list[str],
        on_tick: Any,
        *,
        stream_kind: str = "market",
    ) -> None:
        self._gateway = gateway
        self._feed = feed
        self._instruments = list(instruments)
        self._on_tick = on_tick
        self._stream_kind = stream_kind
        self._broker_id = "upstox"
        self._session_id = str(uuid.uuid4())

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def broker_id(self) -> str:
        return self._broker_id

    async def disconnect(self) -> None:
        if self._stream_kind == "order":
            if self._feed is not None:
                try:
                    await asyncio.to_thread(self._feed.stop)
                except Exception:
                    logger.debug("order_stream_stop_failed", exc_info=True)
            return

        for instrument_key in self._instruments:
            if ":" in instrument_key:
                symbol, exchange = instrument_key.split(":", 1)
            else:
                symbol, exchange = instrument_key, "NSE"
            try:
                await asyncio.to_thread(self._gateway.unstream, symbol, exchange, self._on_tick)
            except Exception:
                logger.debug(
                    "unstream_failed", exc_info=True, extra={"symbol": symbol, "exchange": exchange}
                )

    def is_connected(self) -> bool:
        if self._feed is None:
            return False
        connected = getattr(self._feed, "is_connected", None)
        if callable(connected):
            return bool(connected())
        return bool(connected)


class _UpstoxCommonBrokerGateway:
    """Upstox-specific CommonBrokerGateway.

    Wraps the sync UpstoxBrokerGateway methods as async CommonBrokerGateway
    protocol methods for use by the OMS and infrastructure layers.
    """

    def __init__(self, gateway: UpstoxBrokerGateway) -> None:
        self._gateway = gateway

    @property
    def broker_id(self) -> str:
        return "upstox"

    def list_capabilities(self) -> CapabilityDescriptor:
        return CapabilityDescriptor.build(self._gateway.capabilities(), frozenset())

    def supports(self, feature: str) -> bool:
        return self._gateway.capabilities().supports(feature)

    async def place_order(
        self, request: OrderRequest, *, quota: QuotaToken
    ) -> OrderResponse:
        return await asyncio.to_thread(
            self._gateway.place_order,
            symbol=request.symbol,
            exchange=request.exchange,
            side=request.transaction_type.value,
            quantity=request.quantity,
            price=request.price,
            order_type=request.order_type.value,
            product_type=request.product_type.value,
            validity=request.validity.value,
            trigger_price=request.trigger_price or request.price,
            correlation_id=request.correlation_id,
        )

    async def cancel_order(self, order_id: str, *, quota: QuotaToken) -> OrderResponse:
        return await asyncio.to_thread(self._gateway.cancel_order, order_id)

    async def modify_order(
        self, request: ModifyOrderRequest, *, quota: QuotaToken
    ) -> OrderResponse:
        changes: dict[str, Any] = {}
        if request.quantity is not None:
            changes["quantity"] = request.quantity
        if request.price is not None:
            changes["price"] = request.price
        if request.trigger_price is not None:
            changes["trigger_price"] = request.trigger_price
        if request.order_type is not None:
            changes["order_type"] = request.order_type.value
        if request.validity is not None:
            changes["validity"] = request.validity.value
        if request.product_type is not None:
            changes["product_type"] = request.product_type.value
        return await asyncio.to_thread(self._gateway.modify_order, request.order_id, **changes)

    async def get_positions(self, *, quota: QuotaToken) -> list[Position]:
        return await asyncio.to_thread(self._gateway.positions)

    async def get_margins(self, *, quota: QuotaToken) -> Balance:
        return await asyncio.to_thread(self._gateway.funds)

    async def get_orders(self, *, quota: QuotaToken) -> list[Order]:
        return await asyncio.to_thread(self._gateway.get_orderbook)

    async def get_trades(self, *, quota: QuotaToken) -> list[Trade]:
        return await asyncio.to_thread(self._gateway.get_trade_book)

    async def get_quote_snapshot(
        self, instrument: InstrumentRef, *, quota: QuotaToken
    ) -> Quote:
        return await asyncio.to_thread(
            self._gateway.quote, instrument.symbol, instrument.exchange
        )

    async def get_depth_snapshot(
        self, instrument: InstrumentRef, *, quota: QuotaToken
    ) -> MarketDepth:
        return await asyncio.to_thread(
            self._gateway.depth, instrument.symbol, instrument.exchange
        )

    async def get_historical_bars(
        self, request: HistoricalBarRequest, *, quota: QuotaToken
    ) -> Sequence[HistoricalBar]:
        df = await asyncio.to_thread(
            self._gateway.history,
            request.instrument.symbol,
            request.instrument.exchange,
            request.timeframe,
            90,
            request.from_date,
            request.to_date,
        )
        return dataframe_to_historical_bars(
            df, request.instrument, request.timeframe, self.broker_id, request.request_id
        )

    async def open_market_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        feed = None
        mode = next(iter(plan.modes), "LTP") if plan.modes else "LTP"

        def _on_tick(data: Any) -> None:
            if plan.on_raw_frame is None:
                return
            from brokers.common.broker_port import normalize_tick_frame

            plan.on_raw_frame(normalize_tick_frame(data))

        for instrument_key in plan.instruments:
            if ":" in instrument_key:
                symbol, exchange = instrument_key.split(":", 1)
            else:
                symbol, exchange = instrument_key, "NSE"
            feed = await asyncio.to_thread(
                self._gateway.stream, symbol, exchange, mode, _on_tick
            )

        return _UpstoxStreamHandle(
            self._gateway, feed, list(plan.instruments), _on_tick, stream_kind="market"
        )

    async def open_order_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        def _on_order(data: Any) -> None:
            if plan.on_raw_frame is None:
                return
            frame = data if isinstance(data, dict) else {"order_id": str(data)}
            plan.on_raw_frame(frame)

        feed = await asyncio.to_thread(self._gateway.stream_order, _on_order)
        return _UpstoxStreamHandle(
            self._gateway, feed, list(plan.instruments), _on_order, stream_kind="order"
        )

    async def health(self) -> BrokerHealthSnapshot:
        status = await asyncio.to_thread(self._gateway.get_connection_status)
        connected = status.get("market_data_ws", False) or status.get("portfolio_stream", False)
        reason = "" if connected else "no active stream connections"
        return BrokerHealthSnapshot(
            broker_id=self.broker_id,
            alive=connected,
            auth_valid=connected,
            reason=reason,
        )

    async def close(self) -> None:
        await asyncio.to_thread(self._gateway.close)


def _upstox_normalize_exchange(symbol: str, exchange: str) -> str:
    """Translate a generic exchange string into the Upstox segment form.

    CLI callers pass ``"INDEX"`` for index underlyings; the options adapter
    normalizes this to ``NSE_INDEX`` (or ``BSE_INDEX``) internally. The
    facade just passes through; the adapter handles segment mapping.
    """
    return exchange
