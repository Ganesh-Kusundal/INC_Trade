"""Upstox provider — implements the unified Provider protocol for Upstox.

Adapts the existing UpstoxHttpClient and UpstoxMapper to the new
:class:`Provider` protocol.

Usage::

    from brokers import Broker
    broker = Broker.upstox(access_token="tok")
    reliance = broker.instrument("RELIANCE", Exchange.NSE)
    quote = await reliance.quote()
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime, timezone as tz
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from brokers.constants import DEFAULT_TICK_SIZE

from brokers.domain.account import Account, RiskPolicyProtocol
from brokers.domain.capabilities import ProviderCapabilities
from brokers.domain.enums import AssetClass, Exchange, OptionType, OrderStatus
from brokers.domain.exceptions import ProviderError
from brokers.domain.historical import DateRange, HistoricalBar, HistoricalSeries
from brokers.domain.instrument import Instrument
from brokers.domain.option_chain import FutureChain, OptionChain, OptionContract
from brokers.domain.requests import ModifyOrderRequest, OrderRequest
from brokers.domain.values import (
    Balance,
    Holding,
    MarketDepth,
    OrderResponse,
    Position,
    Quote,
    Subscription,
    Trade,
)
from brokers.infrastructure.event_bus import EventBus
from brokers.infrastructure.http_client import HttpError
from brokers.infrastructure.streaming.stream_health import (
    MarketTickEvent,
    OrderUpdateEvent,
)
from brokers.infrastructure.streaming.subscription import InstrumentKey, StreamMode
from brokers.common.async_http import AsyncHttpMixin
from brokers.common.parsing import dec_optional as _dec
from brokers.common.resolution import ResolutionMixin
from brokers.common.stream_health_mixin import StreamHealthMixin
from brokers.provider.extensions import ExtensionAccess
from brokers.common.instrument_resolver import InstrumentNotFoundError
from brokers.upstox.client import UpstoxHttpClient
from brokers.upstox.mapper import UpstoxMapper

if TYPE_CHECKING:
    from brokers.common.instrument_resolver import InstrumentResolver
    from brokers.upstox.streaming.market_feed import UpstoxMarketFeed
    from brokers.upstox.streaming.portfolio_feed import UpstoxPortfolioStream

# ── Segment mapping ────────────────────────────────────────────────────────

from brokers.common import segments as _segments


def _segment_for(exchange: Exchange) -> str:
    return _segments.exchange_to_segment(exchange)


def _instrument_key(symbol: str, exchange: Exchange) -> str:
    """Build Upstox instrument_key from symbol + exchange."""
    segment = _segment_for(exchange)
    return f"{segment}|{symbol}"


_INTERVAL_MAP: dict[str, str] = {
    "30s": "30_second",
    "1m": "1_minute",
    "5m": "5_minute",
    "10m": "10_minute",
    "15m": "15_minute",
    "20m": "20_minute",
    "30m": "30_minute",
    "45m": "45_minute",
    "1h": "1_hour",
    "2h": "2_hour",
    "3h": "3_hour",
    "4h": "4_hour",
    "1d": "1_day",
    "2d": "2_day",
    "3d": "3_day",
    "5d": "5_day",
    "1w": "1_week",
    "1month": "1_month",
}





class UpstoxProvider(ResolutionMixin, AsyncHttpMixin, StreamHealthMixin):
    """Upstox broker provider implementing the Provider protocol.

    Each method: resolve instrument → call HTTP client → map response →
    return domain entity.
    """

    __slots__ = (
        "_account",
        "_client",
        "_connected",
        "_event_bus",
        "_extensions",
        "_feed_lock",
        "_instruments",
        "_market_feed",
        "_resolver",
        "_portfolio_stream",
        "_risk_policy",
        "_quote_callbacks",
        "_depth_callbacks",
        "_portfolio_callbacks",
        "_feed_refs",
        "_portfolio_refs",
    )

    def __init__(
        self,
        *,
        access_token: str,
        instruments: dict[str, str] | None = None,
        resolver: InstrumentResolver | None = None,
        event_bus: EventBus | None = None,
        risk_policy: RiskPolicyProtocol | None = None,
        **kwargs: Any,
    ) -> None:
        self._client = UpstoxHttpClient(access_token=access_token, **kwargs)
        self._instruments: dict[str, str] = instruments or {}
        self._resolver = resolver
        self._connected = False
        self._event_bus = event_bus or EventBus()
        self._account: Account | None = None
        self._risk_policy = risk_policy
        self._feed_lock: asyncio.Lock | None = None

        # Streaming feeds (created lazily on first subscribe, stopped in disconnect())
        self._market_feed: UpstoxMarketFeed | None = None
        self._portfolio_stream: UpstoxPortfolioStream | None = None

        # Lists of callbacks for quote/depth subscriptions (multiple consumers).
        self._quote_callbacks: list[Callable[[MarketTickEvent], None]] = []
        self._depth_callbacks: list[Callable[[MarketTickEvent], None]] = []
        self._portfolio_callbacks: list[Callable[[OrderUpdateEvent], None]] = []
        # Reference counts: stop a shared feed only when the last consumer leaves.
        self._feed_refs: int = 0
        self._portfolio_refs: int = 0

        # Extended capabilities
        self._extensions = self._build_extensions()

    # ── Identity ─────────────────────────────────────────────────────

    @property
    def broker_id(self) -> str:
        return "upstox"

    @property
    def capabilities(self) -> ProviderCapabilities:
        # Mapper emits DEPTH_5 (slices [:5]); advertise the real supported level.
        return ProviderCapabilities.full("upstox", max_depth_levels=5)

    @property
    def risk_policy(self) -> RiskPolicyProtocol | None:
        return self._risk_policy

    @risk_policy.setter
    def risk_policy(self, value: RiskPolicyProtocol | None) -> None:
        self._risk_policy = value

    @property
    def default_account(self) -> Account:
        if self._account is None:
            self._account = Account(
                "upstox_default", self, risk_policy=self._risk_policy, event_bus=self._event_bus
            )
        return self._account

    @property
    def extensions(self) -> ExtensionAccess:
        return self._extensions

    def update_token(self, new_token: str) -> None:
        """Hot-swap the Bearer token in the underlying HTTP client.

        Called by the :class:`AuthManager` token receiver when a
        background scheduler refreshes the token.
        """
        self._client.update_token(new_token)

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _get_feeds(self) -> list:
        """Return active streaming feeds for health aggregation."""
        return [
            f for f in (self._market_feed, self._portfolio_stream)
            if f is not None
        ]

    # stream_health property provided by StreamHealthMixin

    # ── Helpers ──────────────────────────────────────────────────────

    def _broker_fallback(self, instrument: Instrument) -> str:
        """Upstox fallback: compute instrument_key from symbol + exchange."""
        return _instrument_key(instrument.symbol, instrument.exchange)



    # ── Market data ──────────────────────────────────────────────────

    async def get_quote(self, instrument: Instrument) -> Quote:
        inst_key = self.resolve_broker_id(instrument)
        data = await self._http(self._client.get_quote, [inst_key])
        raw = data.get("data", {}).get(inst_key, {})
        if not raw:
            raise ProviderError(f"No quote data for {instrument.symbol}")
        return UpstoxMapper.map_quote(raw, instrument.symbol)

    async def get_ltp(self, instrument: Instrument) -> Decimal:
        inst_key = self.resolve_broker_id(instrument)
        data = await self._http(self._client.get_ltp, [inst_key])
        raw = data.get("data", {}).get(inst_key, {})
        if not raw:
            raise ProviderError(f"No LTP data for {instrument.symbol}")
        return Decimal(str(raw.get("last_price", 0)))

    async def get_depth(self, instrument: Instrument) -> MarketDepth:
        inst_key = self.resolve_broker_id(instrument)
        data = await self._http(self._client.get_quote, [inst_key])
        raw = data.get("data", {}).get(inst_key, {})
        if not raw:
            raise ProviderError(f"No depth data for {instrument.symbol}")
        return UpstoxMapper.map_depth(raw, instrument.symbol)

    async def get_history(
        self,
        instrument: Instrument,
        *,
        timeframe: str = "1D",
        bars: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> HistoricalSeries:
        inst_key = self.resolve_broker_id(instrument)
        interval = _INTERVAL_MAP.get(timeframe.lower(), timeframe.lower())
        default_from = date.today().replace(day=1)
        default_to = date.today()
        from_str = str(from_date) if from_date else str(default_from)
        to_str = str(to_date) if to_date else str(default_to)
        data = await self._http(self._client.get_historical_candles, inst_key, interval, from_str, to_str)
        candles = data.get("data", {}).get("candles", [])
        candles = candles if isinstance(candles, list) else []

        bar_list: list[HistoricalBar] = []

        for item in candles:
            if isinstance(item, list) and len(item) >= 5:
                ts = datetime.fromisoformat(str(item[0]).replace("Z", "+00:00")) if item[0] else datetime.now(tz.utc)
                bar_list.append(HistoricalBar(
                    symbol=instrument.symbol,
                    exchange=instrument.exchange.value,
                    timeframe=timeframe,
                    event_time=ts,
                    open=Decimal(str(item[1])),
                    high=Decimal(str(item[2])),
                    low=Decimal(str(item[3])),
                    close=Decimal(str(item[4])),
                    volume=int(item[5]) if len(item) > 5 else 0,
                ))

        default_from = date.today().replace(day=1)
        default_to = date.today()
        start = from_date or default_from
        end = to_date or default_to
        return HistoricalSeries(
            bars=bar_list,
            coverage=DateRange(start=start, end=end),
            symbol=instrument.symbol,
            exchange=instrument.exchange.value,
            timeframe=timeframe,
        )

    # ── Instrument search ────────────────────────────────────────────

    async def search_instruments(self, query: str) -> list[Instrument]:
        if self._resolver is not None:
            results = self._resolver.search(query, limit=20)
            return [
                Instrument(
                    symbol=r.symbol,
                    exchange=r.exchange,
                    provider=self,
                    security_id=r.broker_id,
                    lot_size=r.lot_size,
                    tick_size=r.tick_size,
                    trading_symbol=r.trading_symbol,
                )
                for r in results
            ]
        q = query.upper()
        search_results: list[Instrument] = []
        for key, inst_key in self._instruments.items():
            symbol = key.split(":")[0]
            if q in symbol.upper():
                exchange_str = key.split(":")[1] if ":" in key else "NSE"
                search_results.append(Instrument(
                    symbol=symbol,
                    exchange=Exchange(exchange_str),
                    provider=self,
                    security_id=inst_key,
                ))
                if len(search_results) >= 20:
                    break
        return search_results

    async def get_instruments(self, exchange: str | None = None) -> list[Instrument]:
        results: list[Instrument] = []
        for key, inst_key in self._instruments.items():
            parts = key.split(":")
            symbol = parts[0]
            exchange_str = parts[1] if len(parts) > 1 else "NSE"
            if exchange is None or exchange_str == exchange:
                results.append(Instrument(
                    symbol=symbol,
                    exchange=Exchange(exchange_str),
                    provider=self,
                    security_id=inst_key,
                ))
        return results

    async def resolve_instrument(self, symbol: str, exchange: str) -> Instrument:
        key = f"{symbol}:{exchange}"
        inst_key = self._instruments.get(key, _instrument_key(symbol, Exchange(exchange)))
        lot_size = 1
        tick_size = DEFAULT_TICK_SIZE
        trading_symbol = ""
        if self._resolver is not None:
            try:
                resolved = self._resolver.resolve(symbol, Exchange(exchange))
                inst_key = resolved.broker_id
                lot_size = resolved.lot_size
                tick_size = resolved.tick_size
                trading_symbol = resolved.trading_symbol
            except InstrumentNotFoundError:
                pass
        return Instrument(
            symbol=symbol,
            exchange=Exchange(exchange),
            provider=self,
            security_id=inst_key,
            lot_size=lot_size,
            tick_size=tick_size,
            trading_symbol=trading_symbol,
        )

    # ── Derivatives ──────────────────────────────────────────────────

    async def get_option_chain(
        self,
        underlying: Instrument,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        from brokers.common.option_chain_parser import parse_option_chain

        inst_key = self.resolve_broker_id(underlying)
        exp = str(expiry) if expiry else ""
        data = await self._http(self._client.get_option_chain, inst_key, exp)
        raw_chain: dict[str, Any] | list[Any] = data.get("data") or {}
        return parse_option_chain(raw_chain, underlying, self, expiry)

    async def get_future_chain(self, underlying: Instrument) -> FutureChain:
        # Not implemented for Upstox — be honest rather than return empty silently.
        from brokers.domain.exceptions import NotSupportedError

        raise NotSupportedError(
            "get_future_chain is not implemented for the Upstox provider"
        )

    # ── Execution ────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        try:
            inst_key = self.resolve_for_order(request)
            payload = UpstoxMapper.build_order_payload(request, inst_key)
            data = await self._http(self._client.place_order, payload)
            order_id = ""
            if isinstance(data, dict):
                order_id = str(data.get("data", {}).get("order_id", data.get("order_id", "")))
            return OrderResponse.ok(order_id=order_id, message="Order placed", status=OrderStatus.OPEN)
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="UPSTOX_HTTP_ERROR")
        except Exception as exc:
            return OrderResponse.fail(str(exc), error_code="INTERNAL_ERROR")

    async def cancel_order(self, order_id: str) -> OrderResponse:
        try:
            data = await self._http(self._client.cancel_order, order_id)
            raw = data if isinstance(data, dict) else {}
            broker_status = str(raw.get("status", "")).lower()
            if broker_status in ("success", "ok"):
                return OrderResponse.ok(order_id=order_id, message="Order cancelled", status=OrderStatus.CANCELLED)
            if broker_status in ("failure", "error"):
                return OrderResponse.fail(
                    str(raw.get("remarks", raw.get("errorMessage", "Cancel failed"))),
                    error_code=str(raw.get("errorCode", "UPSTOX_CANCEL_FAILED")),
                )
            return OrderResponse.fail(
                str(raw.get("message", "Cancel failed")),
                error_code="UPSTOX_CANCEL_FAILED",
            )
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="UPSTOX_HTTP_ERROR")
        except Exception as exc:
            return OrderResponse.fail(str(exc), error_code="INTERNAL_ERROR")

    async def modify_order(self, request: ModifyOrderRequest) -> OrderResponse:
        try:
            payload = {k: v for k, v in {
                "quantity": request.quantity,
                "price": request.price,
                "trigger_price": request.trigger_price,
                "order_type": request.order_type.value if request.order_type else None,
                "validity": request.validity.value if request.validity else None,
                "product": request.product_type.value if request.product_type else None,
            }.items() if v is not None}
            data = await self._http(self._client.modify_order, request.order_id, payload)
            raw = data if isinstance(data, dict) else {}
            broker_status = str(raw.get("status", "")).lower()
            if broker_status in ("success", "ok"):
                return OrderResponse.ok(order_id=request.order_id, message="Order modified")
            if broker_status in ("failure", "error"):
                return OrderResponse.fail(
                    str(raw.get("remarks", raw.get("errorMessage", "Modify failed"))),
                    error_code=str(raw.get("errorCode", "UPSTOX_MODIFY_FAILED")),
                )
            return OrderResponse.fail(
                str(raw.get("message", "Modify failed")),
                error_code="UPSTOX_MODIFY_FAILED",
            )
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="UPSTOX_HTTP_ERROR")
        except Exception as exc:
            return OrderResponse.fail(str(exc), error_code="INTERNAL_ERROR")

    # ── Portfolio ────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        data = await self._http(self._client.get_positions)
        items = data.get("data", []) if isinstance(data, dict) else []
        return [UpstoxMapper.map_position(item) for item in (items if isinstance(items, list) else [])]

    async def get_balance(self) -> Balance:
        data = await self._http(self._client.get_funds)
        raw = data.get("data", data) if isinstance(data, dict) else {}
        if isinstance(raw, dict) and "equity" in raw:
            raw = raw["equity"]
        return UpstoxMapper.map_balance(raw if isinstance(raw, dict) else {})

    async def get_orders(self) -> list[Order]:
        from brokers.domain.order import Order
        data = await self._http(self._client.get_orderbook)
        items = data.get("data", []) if isinstance(data, dict) else []
        return [UpstoxMapper.map_order(item) for item in (items if isinstance(items, list) else [])]

    async def get_trades(self) -> list[Trade]:
        data = await self._http(self._client.get_trades)
        items = data.get("data", []) if isinstance(data, dict) else []
        return [UpstoxMapper.map_trade(item) for item in (items if isinstance(items, list) else [])]

    async def get_holdings(self) -> list[Holding]:
        data = await self._http(self._client.get_holdings)
        items = data.get("data", []) if isinstance(data, dict) else []
        return [UpstoxMapper.map_holding(item) for item in (items if isinstance(items, list) else [])]

    # ── Streaming ────────────────────────────────────────────────────

    def _update_feed_callback(self, feed: UpstoxMarketFeed) -> None:
        """Install a fan-out callback that dispatches to ALL quote/depth handlers.

        Keeps a LIST of callbacks so multiple ``subscribe_quotes`` /
        ``subscribe_depth`` consumers on the shared feed all receive ticks
        (a single callback would clobber the others).
        """
        quote_cbs = list(self._quote_callbacks)
        depth_cbs = list(self._depth_callbacks)

        def _dispatch(event: MarketTickEvent) -> None:
            for cb in quote_cbs:
                cb(event)
            if event.depth_bids or event.depth_asks:
                for cb in depth_cbs:
                    cb(event)

        if quote_cbs or depth_cbs:
            feed.set_tick_callback(_dispatch)
        else:
            feed.set_tick_callback(None)

    async def subscribe_quotes(
        self,
        instruments: list[Instrument],
        *,
        on_tick: Callable[[Quote], None] | None = None,
    ) -> Subscription:
        """Subscribe to real-time quote updates via UpstoxMarketFeed.

        Creates and starts the market feed lazily on first call. Supports
        multiple concurrent subscribers (ref-counted shared feed).
        """
        feed = await self._ensure_market_feed()
        self._feed_refs += 1

        if on_tick is not None:
            def _tick_to_quote(event: MarketTickEvent) -> None:
                on_tick(Quote(symbol=event.symbol, ltp=Decimal(str(event.ltp))))
            self._quote_callbacks.append(_tick_to_quote)
            self._update_feed_callback(feed)

        async def _cancel() -> None:
            for inst in instruments:
                inst_key = self.resolve_broker_id(inst)
                key = InstrumentKey(
                    symbol=inst.symbol, exchange=inst.exchange.value, security_id=inst_key,
                )
                await feed.unsubscribe(key)
            self._feed_refs -= 1
            if self._feed_refs <= 0:
                self._quote_callbacks.clear()
                self._depth_callbacks.clear()
                await feed.stop()

        sub = Subscription(Subscription.create_id(), _cancel)

        for inst in instruments:
            inst_key = self.resolve_broker_id(inst)
            key = InstrumentKey(
                symbol=inst.symbol, exchange=inst.exchange.value, security_id=inst_key,
            )
            await feed.subscribe(key, mode=StreamMode.QUOTE)

        return sub

    async def subscribe_depth(
        self,
        instruments: list[Instrument],
        *,
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Subscription:
        """Subscribe to real-time depth updates via UpstoxMarketFeed (D30 mode).

        Creates and starts the market feed lazily on first call. Supports
        multiple concurrent subscribers (ref-counted shared feed).
        """
        feed = await self._ensure_market_feed()
        self._feed_refs += 1

        if on_depth is not None:
            def _event_to_depth(event: MarketTickEvent) -> None:
                from brokers.domain.values import DepthLevel

                on_depth(MarketDepth(
                    symbol=event.symbol,
                    bids=[DepthLevel(price=Decimal(str(b[0])), quantity=int(b[1]))
                          for b in (event.depth_bids or ())],
                    asks=[DepthLevel(price=Decimal(str(a[0])), quantity=int(a[1]))
                          for a in (event.depth_asks or ())],
                    depth_type="DEPTH_5",
                ))
            self._depth_callbacks.append(_event_to_depth)
            self._update_feed_callback(feed)

        async def _cancel() -> None:
            for inst in instruments:
                inst_key = self.resolve_broker_id(inst)
                key = InstrumentKey(
                    symbol=inst.symbol, exchange=inst.exchange.value, security_id=inst_key,
                )
                await feed.unsubscribe(key)
            self._feed_refs -= 1
            if self._feed_refs <= 0:
                self._quote_callbacks.clear()
                self._depth_callbacks.clear()
                await feed.stop()

        sub = Subscription(Subscription.create_id(), _cancel)

        for inst in instruments:
            inst_key = self.resolve_broker_id(inst)
            key = InstrumentKey(
                symbol=inst.symbol, exchange=inst.exchange.value, security_id=inst_key,
            )
            await feed.subscribe(key, mode=StreamMode.DEPTH)

        return sub

    async def subscribe_orders(
        self,
        *,
        on_update: Callable[[Any], None] | None = None,
    ) -> Subscription:
        """Subscribe to order status updates via UpstoxPortfolioStream.

        Creates and starts the portfolio stream lazily on first call.
        Supports multiple concurrent subscribers (ref-counted shared feed);
        the feed is stopped only when the last subscriber cancels.
        """
        feed = await self._ensure_portfolio_stream()
        self._portfolio_refs += 1

        if on_update is not None:
            self._portfolio_callbacks.append(on_update)
            feed.set_order_callback(self._dispatch_order)

        async def _cancel() -> None:
            self._portfolio_refs -= 1
            if on_update is not None and on_update in self._portfolio_callbacks:
                self._portfolio_callbacks.remove(on_update)
            if self._portfolio_refs <= 0:
                self._portfolio_callbacks.clear()
                await feed.stop()

        return Subscription(Subscription.create_id(), _cancel)

    def _dispatch_order(self, event: OrderUpdateEvent) -> None:
        """Fan-out order updates to all portfolio subscribers."""
        for cb in list(self._portfolio_callbacks):
            cb(event)

    async def unsubscribe(self, subscription: Subscription) -> None:
        await subscription.cancel()

    # ── Lifecycle ────────────────────────────────────────────────────

    def _build_extensions(self) -> ExtensionAccess:
        """Build ExtensionAccess with all Upstox extended capabilities."""
        from brokers.upstox.extended.alerts import UpstoxAlerts
        from brokers.upstox.extended.cover_order import UpstoxCoverOrders
        from brokers.upstox.extended.exit_all import UpstoxExitAll
        from brokers.upstox.extended.expired_instruments import UpstoxExpiredInstruments
        from brokers.upstox.extended.fundamentals import UpstoxFundamentals
        from brokers.upstox.extended.gtt import UpstoxGTT
        from brokers.upstox.extended.ipo import UpstoxIPO
        from brokers.upstox.extended.kill_switch import UpstoxKillSwitch
        from brokers.upstox.extended.margin import UpstoxMargin
        from brokers.upstox.extended.market_intelligence import UpstoxMarketIntelligence
        from brokers.upstox.extended.market_status import UpstoxMarketStatus
        from brokers.upstox.extended.mutual_funds import UpstoxMutualFunds
        from brokers.upstox.extended.news import UpstoxNews
        from brokers.upstox.extended.order_query import UpstoxOrderQuery
        from brokers.upstox.extended.payments import UpstoxPayments
        from brokers.upstox.extended.reconciliation import UpstoxReconciliation
        from brokers.upstox.extended.slice import UpstoxSliceOrders
        from brokers.upstox.extended.static_ip import UpstoxStaticIp

        return ExtensionAccess(
            self,
            extensions={
                "alerts": UpstoxAlerts(client=self._client),
                "cover_order": UpstoxCoverOrders(client=self._client),
                "exit_all": UpstoxExitAll(client=self._client),
                "expired_instruments": UpstoxExpiredInstruments(client=self._client),
                "fundamentals": UpstoxFundamentals(client=self._client),
                "gtt": UpstoxGTT(client=self._client),
                "ipo": UpstoxIPO(client=self._client),
                "kill_switch": UpstoxKillSwitch(client=self._client),
                "margin": UpstoxMargin(client=self._client),
                "market_intelligence": UpstoxMarketIntelligence(client=self._client),
                "market_status": UpstoxMarketStatus(client=self._client),
                "mutual_funds": UpstoxMutualFunds(client=self._client),
                "news": UpstoxNews(client=self._client),
                "order_query": UpstoxOrderQuery(client=self._client),
                "payments": UpstoxPayments(client=self._client),
                "reconciliation": UpstoxReconciliation(client=self._client),
                "slice": UpstoxSliceOrders(client=self._client),
                "static_ip": UpstoxStaticIp(client=self._client),
            },
        )

    async def connect(self) -> None:
        """Mark as connected. Feeds are created lazily on first subscribe."""
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect: stop all feeds if running (thread-safe via asyncio.Lock)."""
        if self._feed_lock is None:
            self._feed_lock = asyncio.Lock()
        async with self._feed_lock:
            coros = []
            if self._market_feed is not None:
                coros.append(self._market_feed.stop())
                self._market_feed = None
            if self._portfolio_stream is not None:
                coros.append(self._portfolio_stream.stop())
                self._portfolio_stream = None
            if coros:
                await asyncio.gather(*coros)
            self._connected = False

    async def _ensure_market_feed(self) -> UpstoxMarketFeed:
        """Lazily create and start the market feed (thread-safe via asyncio.Lock)."""
        if self._feed_lock is None:
            self._feed_lock = asyncio.Lock()
        async with self._feed_lock:
            if self._market_feed is None or not self._market_feed.is_running:
                from brokers.upstox.streaming.market_feed import UpstoxMarketFeed

                self._market_feed = UpstoxMarketFeed(http_client=self._client)
                await self._market_feed.start()
            return self._market_feed

    async def _ensure_portfolio_stream(self) -> UpstoxPortfolioStream:
        """Lazily create and start the portfolio stream (thread-safe via asyncio.Lock)."""
        if self._feed_lock is None:
            self._feed_lock = asyncio.Lock()
        async with self._feed_lock:
            if self._portfolio_stream is None or not self._portfolio_stream.is_running:
                from brokers.upstox.streaming.portfolio_feed import UpstoxPortfolioStream

                self._portfolio_stream = UpstoxPortfolioStream(http_client=self._client)
                await self._portfolio_stream.start()
            return self._portfolio_stream


__all__ = ["UpstoxProvider"]
