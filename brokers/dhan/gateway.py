"""BrokerGateway — thin sync facade delegating to DhanConnection ports."""

from __future__ import annotations

import contextlib
import logging
import threading
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable

import pandas as pd

from brokers.common.batch_mixin import BatchFetchMixin
from brokers.common.broker_port import CommonBrokerGateway
from brokers.common.dtos import BrokerOrderPayload
from brokers.common.gateway import BrokerCapabilities, MarketDataGateway, ObservabilityProvider
from brokers.common.common_broker_access import to_common_broker_gateway
from brokers.dhan.capabilities import dhan_capabilities
from brokers.dhan.connection import DhanConnection
from brokers.dhan.exceptions import OrderError
from brokers.dhan.segments import DEFAULT_SEGMENT, EXCHANGE_TO_SEGMENT
from domain import (
    Balance,
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
from domain.status_mapper import StatusMapperRegistry, UnmappedBrokerStatusError
from domain.exchange_segments import parse_segment
from domain.symbols import normalize_symbol
from infrastructure.observability.tracing import trace_operation

logger = logging.getLogger(__name__)


class BrokerGateway(BatchFetchMixin, MarketDataGateway, ObservabilityProvider):
    """Unified broker API. All calls delegate to connection adapters.

    Implements both MarketDataGateway (broker-agnostic contract) and
    ObservabilityProvider (canonical observability data exposure).
    """

    def __init__(self, connection: DhanConnection):
        self._conn = connection
        self._stream_lock = threading.Lock()
        # Broker-agnostic options facade — CLI/tests use ``gateway.options``.
        from brokers.common.options.gateway_facade import GatewayOptionsFacade

        self.options = GatewayOptionsFacade(
            self._conn.options,
            exchange_normalize=_dhan_normalize_exchange,
        )

    def common_broker_gateway(self) -> CommonBrokerGateway:
        """Native CommonBrokerGateway port for infrastructure bootstrap."""
        return to_common_broker_gateway(self, "dhan")

    @property
    def extended(self) -> Any:
        """Access Dhan-specific capabilities beyond MarketDataGateway ABC.

        Returns a :class:`~brokers.dhan.extended.DhanExtendedCapabilities`
        instance with broker-specific methods (super orders, forever orders,
        conditional triggers, ledger, user profile, IP management, EDIS,
        option/futures listing, order validation).
        """
        from brokers.dhan.extended import DhanExtendedCapabilities

        return DhanExtendedCapabilities(self._conn)

    # ── Order shortcuts ──

    @trace_operation("dhan_gateway.place_order")
    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> OrderResponse:
        """Place an order with explicit parameters matching MarketDataGateway ABC.

        If *correlation_id* is not provided, the current thread's active
        correlation ID (set via :func:`infrastructure.correlation.with_correlation`)
        is used.  This enables automatic end-to-end tracing from CLI
        commands through to the broker API.

        The OMS owns all pre-submit risk validation; the broker adapter
        enforces its own boundary checks independently.
        """
        correlation_id = self._resolve_correlation_id(correlation_id)

        exchange_segment = parse_segment(exchange)
        if exchange_segment is None:
            raise ValueError(f"Unknown exchange segment: {exchange!r}")

        request = self._build_order_payload(
            symbol=symbol,
            exchange=exchange,
            exchange_segment=exchange_segment,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )

        try:
            order = self._conn.orders.place_order(request)
            return self._normalize_order_response(order)
        except OrderError as exc:
            return OrderResponse.fail(str(exc))

    def _resolve_correlation_id(self, correlation_id: str | None) -> str | None:
        if correlation_id is not None:
            return correlation_id
        try:
            from infrastructure.correlation import get_current_correlation_id

            return get_current_correlation_id()
        except ImportError:
            return None

    def _build_order_payload(
        self,
        symbol: str,
        exchange: str,
        exchange_segment: str,
        side: str,
        quantity: int,
        price: Decimal,
        order_type: str,
        product_type: str,
        validity: str,
        trigger_price: Decimal,
        correlation_id: str | None,
    ) -> BrokerOrderPayload:
        return BrokerOrderPayload(
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
        )

    def _normalize_order_response(self, order: Any) -> OrderResponse:
        status_str = getattr(order.status, "value", str(order.status)).upper()
        try:
            status = StatusMapperRegistry.normalize_strict(status_str)
        except (AttributeError, UnmappedBrokerStatusError) as exc:
            logger.error(
                "unmapped_order_status",
                extra={
                    "order_id": order.order_id,
                    "raw_status": getattr(order.status, "value", str(order.status)),
                    "error": str(exc),
                },
            )
            return OrderResponse.fail(
                message=f"Unmapped order status: {getattr(order.status, 'value', str(order.status))}",
                error_code="UNMAPPED_STATUS",
            )
        return OrderResponse.ok(
            order_id=order.order_id,
            message="Order placed",
            status=status,
        )

    @trace_operation("dhan_gateway.cancel_order")
    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order with post-cancellation verification.

        After sending the cancel request, verifies the order reached the
        cancelled state. Detects race conditions where the order was filled
        between cancel send and response.

        Returns:
            OrderResponse with success=True if cancelled, or
            OrderResponse.fail with error_code="ALREADY_EXECUTED" if the
            order was already filled before cancel could complete.
        """
        response = self._conn.orders.cancel_order(order_id)
        if response.success:
            order = self.get_order(order_id)
            if order and order.status in (OrderStatus.FILLED,):
                return OrderResponse.fail(
                    message=f"Order {order_id} was already filled before cancel completed",
                    status=OrderStatus.FILLED,
                )
        return response

    def get_order(self, order_id: str) -> Order | None:
        """Query a single order by ID via direct lookup.

        Uses the OrdersAdapter.get_order() method which calls
        GET /orders/{order_id} directly, avoiding a full orderbook
        fetch. This halves API calls in cancel_order() verification.
        """
        try:
            order = self._conn.orders.get_order(order_id)
            if order is None or not order.order_id:
                return None
            return order
        except Exception as exc:
            logger.warning(
                "get_order_failed",
                extra={"order_id": order_id, "error": str(exc)},
            )
            return None

    @trace_operation("dhan_gateway.modify_order")
    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        try:
            order = self._conn.orders.modify_order(order_id, **changes)
            return OrderResponse.ok(
                order_id=order.order_id, message="Order modified", status=order.status
            )
        except Exception as exc:
            return OrderResponse.fail(str(exc))

    def get_orderbook(self) -> list[Order]:
        return self._conn.orders.get_orderbook()

    def get_trade_book(self) -> list[Trade]:
        return self._conn.orders.get_trade_book()

    # ── Lifecycle ──

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        self._conn.load_instruments(source=source, use_cache=use_cache)

    def close(self) -> None:
        self._conn.close()

    # ── Market Data (ABC-aligned) ─────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self._conn.market_data.get_ltp(symbol, exchange)

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        return self._conn.market_data.get_quote(symbol, exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        return self._conn.market_data.get_depth(symbol, exchange)

    def _complete_depth_snapshot(
        self,
        ws_depth: MarketDepth | None,
        symbol: str,
        exchange: str,
    ) -> MarketDepth:
        """Merge WebSocket depth with REST fallback for any missing side."""
        needs_rest = ws_depth is None or not ws_depth.bids or not ws_depth.asks
        rest: MarketDepth | None = None
        if needs_rest:
            rest = self._conn.market_data.get_depth(symbol, exchange)

        if ws_depth is None:
            return rest  # type: ignore[return-value]

        bids = ws_depth.bids if ws_depth.bids else (rest.bids if rest else [])
        asks = ws_depth.asks if ws_depth.asks else (rest.asks if rest else [])

        return MarketDepth(
            symbol=symbol,
            bids=list(bids),
            asks=list(asks),
            depth_type=ws_depth.depth_type,
            timestamp=ws_depth.timestamp or (rest.timestamp if rest else None),
        )

    def _validate_nse_exchange(self, exchange: str, depth_type: str) -> None:
        allowed = ("NSE", "NSE_EQ", "NFO", "NSE_FNO", "IDX_I")
        if exchange not in allowed:
            raise ValueError(
                f"Depth {depth_type} only supported for NSE segments, got: {exchange}"
            )

    def _resolve_depth_instrument(
        self, symbol: str, exchange: str
    ) -> tuple[str, str, int]:
        inst = self._conn.instruments.resolve(symbol, exchange)
        segment = EXCHANGE_TO_SEGMENT.get(inst.exchange.value, DEFAULT_SEGMENT)
        sid_str = inst.security_id
        return segment, sid_str, int(sid_str)

    def _ensure_depth_feed(
        self,
        feed_attr: str,
        create_fn: Any,
        instrument: tuple[str, str],
        sid_str: str,
        on_depth: Any | None,
        max_subscriptions: int | None = None,
    ) -> Any:
        feed = getattr(self._conn, feed_attr)
        
        # Special handling for depth_200_feed to use connection pool
        if feed_attr == "depth_200_feed":
            pool = getattr(self._conn, "depth_200_pool", None)
            from brokers.dhan.depth_200 import Depth200ConnectionPool
            if isinstance(pool, Depth200ConnectionPool):
                # Use connection pool for multiple instruments
                feed = pool.get_feed(instrument)
                if on_depth is not None:
                    feed.on_depth(on_depth)
                if not feed.is_running:
                    feed.start()
                return feed
            else:
                # Fallback to old behavior if pool not available
                pass
        
        if feed is None:
            feed = create_fn(
                access_token=self._conn.access_token,
                instrument=instrument,
            )
        else:
            existing = None
            if max_subscriptions == 1 and feed.subscriptions:
                existing = feed.subscriptions[0][1]
            elif feed.subscriptions:
                existing = next(
                    (s[1] for s in feed.subscriptions if s[1] == sid_str),
                    None,
                )
            if existing is not None and existing != sid_str:
                raise ValueError(
                    f"Depth feed already subscribed to security_id {existing}. "
                    f"Create a new gateway connection to stream a different instrument."
                )
            if existing is None and (
                max_subscriptions is None
                or not any(s[1] == sid_str for s in feed.subscriptions)
            ):
                feed.subscribe([instrument])

        if on_depth is not None:
            feed.on_depth(on_depth)

        if not feed.is_running:
            feed.start()

        return feed

    def depth_20(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_depth: Any | None = None,
    ) -> MarketDepth:
        """Subscribe to 20-level market depth for *symbol* via WebSocket.

        On the first call the feed is created, the instrument subscribed, and
        the connection started.  Subsequent calls for the same feed reuse the
        existing WebSocket and subscription.

        The method returns the most-recently cached
        :class:`~brokers.common.core.domain.MarketDepth` (up to 20 levels on
        each side).  If no packet has been received yet it falls back to the
        5-level REST snapshot so callers always get *something*.
        """
        self._validate_nse_exchange(exchange, "20")
        segment, sid_str, sid_int = self._resolve_depth_instrument(symbol, exchange)

        feed = self._ensure_depth_feed(
            "depth_20_feed",
            self._conn.create_depth_20_feed,
            (segment, sid_str),
            sid_str,
            on_depth,
            max_subscriptions=None,
        )
        feed.register_symbol(sid_int, symbol)

        cached = feed.latest_depth(sid_int)
        result = self._complete_depth_snapshot(cached, symbol, exchange)
        if cached is not None:
            logger.debug(
                "depth_20_from_websocket",
                extra={
                    "symbol": symbol,
                    "exchange": exchange,
                    "depth_type": result.depth_type,
                    "bid_levels": len(result.bids),
                    "ask_levels": len(result.asks),
                    "rest_merged": bool(cached and (not cached.bids or not cached.asks)),
                },
            )
            return result

        logger.debug(
            "depth_20_fallback_to_rest",
            extra={
                "symbol": symbol,
                "exchange": exchange,
                "reason": "no websocket data received yet",
            },
        )
        return result

    def depth_200(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_depth: Any | None = None,
    ) -> MarketDepth:
        """Subscribe to 200-level market depth for *symbol* via WebSocket.

        IMPORTANT: Dhan allows only **one** instrument per depth-200 connection.
        Calling this method with a different symbol after the feed is already running
        raises :class:`ValueError`.
        
        For multiple instruments, use the connection pool pattern:
            from brokers.dhan.depth_200 import Depth200ConnectionPool
            
            pool = Depth200ConnectionPool(
                client_id=self._conn.client_id,
                access_token=self._conn.access_token,
            )
            feed1 = pool.get_feed((segment1, security_id1))
            feed2 = pool.get_feed((segment2, security_id2))
        """
        self._validate_nse_exchange(exchange, "200")
        segment, sid_str, _ = self._resolve_depth_instrument(symbol, exchange)

        feed = self._ensure_depth_feed(
            "depth_200_feed",
            self._conn.create_depth_200_feed,
            (segment, sid_str),
            sid_str,
            on_depth,
            max_subscriptions=1,
        )
        feed.register_symbol(int(sid_str), symbol)

        cached = feed.latest_depth()
        return self._complete_depth_snapshot(cached, symbol, exchange)

    def history(
        self,
        symbol: str,
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        from brokers.dhan.exceptions import InstrumentNotFoundError
        to_d = date.today()
        from_d = to_d - timedelta(days=lookback_days)
        to_str = to_date or str(to_d)
        from_str = from_date or str(from_d)
        timeframe_str = timeframe.upper() if timeframe else "1D"
        
        try:
            return self._conn.historical.get_historical(symbol, exchange, from_str, to_str, timeframe_str)
        except InstrumentNotFoundError:
            logger.warning("history: instrument not found: %s/%s", symbol, exchange)
            return pd.DataFrame()

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        """Get option chain. Delegates MCX-specific expiry lookup to extended."""
        return OptionChain.from_dict(self.extended.get_option_chain(underlying, exchange, expiry))

    def future_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
    ) -> FutureChain:
        from config.indices import INDEX_TO_FNO_EXCHANGE

        # Index futures use the mapped exchange; stock futures always trade on NFO.
        # If a caller passes exchange="NSE" for a stock like RELIANCE, remap to NFO.
        dhan_exchange = INDEX_TO_FNO_EXCHANGE.get(underlying.upper(), None)
        if dhan_exchange is None:
            # Not an index — it's a stock. Stock F&O always trades on NFO.
            dhan_exchange = "NFO" if exchange.upper() in ("NSE", "BSE") else exchange
        contracts = self._conn.futures.get_contracts(underlying, dhan_exchange)
        expiries = self._conn.futures.get_expiries(underlying, dhan_exchange)
        chain = []
        for c in contracts:
            chain.append(
                {
                    "expiry": c.get("expiry", ""),
                    "symbol": c.get("symbol", ""),
                    "lot_size": c.get("lot_size", 1),
                    "underlying": c.get("underlying", underlying),
                }
            )
        return FutureChain.from_dict(
            {
                "underlying": underlying,
                "exchange": dhan_exchange,
                "expiries": expiries,
                "contracts": chain,
            }
        )

    def get_balance(self) -> Balance:
        """Return current account balance (fund limits).

        Delegates to the portfolio adapter's ``get_balance()`` which
        calls ``GET /fundlimit`` on the Dhan API.
        """
        return self._conn.portfolio.get_balance()

    def funds(self) -> Balance:
        """Alias for :meth:`get_balance` — backward-compatible contract name."""
        return self.get_balance()

    def positions(self) -> list[Position]:
        return self._conn.portfolio.get_positions()

    def holdings(self) -> list[Holding]:
        return self._conn.portfolio.get_holdings()

    def trades(self) -> list[Trade]:
        return self.get_trade_book()

    def describe(self) -> dict:
        instruments = self._conn.instruments
        return {
            "broker": "Dhan",
            "instruments_loaded": instruments._loaded,
            "instrument_count": instruments.stats().get("total", 0),
            "market_data": "available",
            "historical": "available",
            "options": "available",
            "futures": "available",
            "streaming": "available",
        }

    def capabilities(self) -> BrokerCapabilities:
        """Return Dhan broker capability matrix."""
        return dhan_capabilities()

    def search(self, query: str) -> list[dict]:
        results = []
        q = normalize_symbol(query)
        for inst in self._conn.instruments.all_instruments():
            if q in inst.symbol.upper() or q in (inst.canonical_symbol or "").upper():
                results.append(
                    {
                        "symbol": inst.symbol,
                        "exchange": inst.exchange.value,
                        "type": inst.instrument_type.value,
                        "security_id": inst.security_id,
                        "name": inst.canonical_symbol,
                    }
                )
                if len(results) >= 20:
                    break
        return results

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        """Subscribe to a live tick stream for *symbol* on *exchange*.

        Delegates to :class:`SubscriptionEngine` — the single source of truth
        for instrument subscriptions and callback multiplexing.
        """
        with self._stream_lock:
            return self._conn.subscription_engine.subscribe_market(
                symbol, exchange, mode, on_tick
            )

    def unstream(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_tick: Any | None = None,
    ) -> None:
        """Unsubscribe from a live tick stream."""
        with self._stream_lock:
            self._conn.subscription_engine.unsubscribe_market(symbol, exchange, on_tick)

    def stream_depth(
        self,
        symbol: str,
        exchange: str = "NSE",
        depth_type: str = "DEPTH_5",  # DEPTH_5, DEPTH_20, DEPTH_30, DEPTH_200
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Any:
        """Map generic depth stream requests to Dhan's native 20-level and 200-level streams."""
        if depth_type in ("DEPTH_5", "DEPTH_20"):
            return self.depth_20(symbol, exchange=exchange, on_depth=on_depth)
        elif depth_type == "DEPTH_200":
            return self.depth_200(symbol, exchange=exchange, on_depth=on_depth)
        else:
            raise ValueError(f"Dhan does not support depth type: {depth_type}")

    def stream_order(self, on_order: Any | None = None) -> Any:
        """Subscribe to account-wide order updates via the shared order stream."""
        with self._stream_lock:
            return self._conn.subscription_engine.subscribe_order(on_order)

    def unstream_order(self, on_order: Any | None = None) -> None:
        """Remove an order-update callback from the shared order stream."""
        with self._stream_lock:
            self._conn.subscription_engine.unsubscribe_order(on_order)

    # ── Parallel Data Fetching ──────────────────────────────────────

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Fetch LTP for multiple symbols using native batch API (up to 1000)."""
        return self._conn.market_data.get_batch_ltp(symbols, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        """Fetch quotes for multiple symbols using native batch API (up to 1000)."""
        return self._conn.market_data.get_batch_quote(symbols, exchange)

    # history_batch inherited from BatchFetchMixin (parallel single-item history calls)

    # -----------------------------------------------------------------------
    # ObservabilityProvider Implementation
    # -----------------------------------------------------------------------

    def get_connection_status(self) -> dict[str, bool]:
        """Return connection status for Dhan WebSocket streams.

        Implements ObservabilityProvider protocol to expose connection
        status without exposing private attributes to CLI layer.
        """
        status: dict[str, bool | str | float | None] = {}

        market_feed = getattr(self._conn, "market_feed", None)
        if market_feed is not None:
            status["market_feed"] = market_feed.is_connected
            with contextlib.suppress(Exception):
                health = market_feed.health()
                metrics = health.metrics or {}
                status["market_feed_stale"] = bool(metrics.get("is_stale", False))
                status["connection_lock_acquired"] = bool(
                    metrics.get("connection_lock_acquired", False)
                )
                status["connection_blocked_by_lock"] = bool(
                    metrics.get("connection_blocked_by_lock", False)
                )
                status["next_connect_allowed_at"] = metrics.get("next_connect_allowed_at")

        order_stream = getattr(self._conn, "order_stream", None)
        if order_stream is not None:
            status["order_stream"] = order_stream.is_connected

        for feed_attr, status_key in (
            ("depth_20_feed", "depth_20"),
            ("depth_200_feed", "depth_200"),
        ):
            feed = getattr(self._conn, feed_attr, None)
            if feed is not None:
                status[status_key] = self._is_feed_connected(feed)

        engine = getattr(self._conn, "subscription_engine", None)
        if engine is not None:
            try:
                count = engine.subscription_count()
                status["has_active_subscriptions"] = int(count) > 0
            except (TypeError, ValueError):
                status["has_active_subscriptions"] = False

        return status

    def _is_feed_connected(self, feed: Any) -> bool:
        connected = getattr(feed, "is_connected", None)
        if callable(connected):
            return bool(connected())
        return bool(getattr(feed, "_is_connected", False))

    def get_circuit_breaker_states(self) -> dict[str, int]:
        """Return Dhan client circuit breaker states.

        Maps CircuitState enum to int: 0=CLOSED, 1=OPEN, 2=HALF_OPEN.
        Implements ObservabilityProvider protocol.

        Delegates to the connection's public ``circuit_breaker_states``
        property so the gateway never touches private ``_client`` attributes.
        """
        return self._conn.circuit_breaker_states

    def get_token_refresh_metrics(self) -> dict[str, int]:
        """Return token refresh metrics from Dhan connection.

        Implements ObservabilityProvider protocol.

        Delegates to the connection's public ``token_refresh_metrics``
        property so the gateway never touches private ``_token_scheduler``.
        """
        return self._conn.token_refresh_metrics


def _dhan_normalize_exchange(symbol: str, exchange: str) -> str:
    """Translate a generic exchange string into the Dhan-canonical form.

    Dhan option-chain calls accept ``"INDEX"`` (per integration tests) and
    ``"NSE"`` / ``"BSE"``. The integration suite uses ``"INDEX"`` for index
    underlyings (NIFTY, BANKNIFTY); we keep that convention.
    """
    from config.indices import dhan_index_exchange, is_index

    if is_index(symbol):
        return dhan_index_exchange(symbol) or exchange
    return exchange
