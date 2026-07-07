"""Dhan provider — implements the unified Provider protocol for Dhan.

Adapts the existing DhanHttpClient and DhanMapper to the new
:class:`Provider` protocol.  Methods take :class:`Instrument` objects
instead of raw symbol/exchange strings.

Usage::

    from brokers import Broker
    broker = Broker.dhan(client_id="123", access_token="tok")
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
from brokers.domain.enums import Exchange, OrderStatus
from brokers.domain.exceptions import ProviderError
from brokers.domain.historical import DateRange, HistoricalBar, HistoricalSeries
from brokers.domain.instrument import Instrument
from brokers.domain.option_chain import FutureChain, OptionChain, OptionContract
from brokers.domain.requests import ModifyOrderRequest, OrderRequest
from brokers.domain.values import (
    Balance,
    DepthLevel,
    Holding,
    MarketDepth,
    OrderResponse,
    Position,
    Quote,
    Subscription,
    Trade,
)
from brokers.common.instrument_resolver import InstrumentNotFoundError
from brokers.dhan.client import DhanHttpClient
from brokers.dhan.mapper import DhanMapper
from brokers.infrastructure.event_bus import EventBus
from brokers.infrastructure.http_client import HttpError
from brokers.infrastructure.streaming.stream_health import (
    MarketTickEvent,
)
from brokers.infrastructure.streaming.subscription import InstrumentKey, StreamMode
from brokers.common.async_http import AsyncHttpMixin
from brokers.common.parsing import dec as _dec
from brokers.common.resolution import ResolutionMixin
from brokers.common.stream_health_mixin import StreamHealthMixin
from brokers.provider.extensions import ExtensionAccess

if TYPE_CHECKING:
    from brokers.common.instrument_resolver import InstrumentResolver
    from brokers.dhan.streaming.depth_feed import DhanDepth20Feed
    from brokers.dhan.streaming.market_feed import DhanMarketFeed
    from brokers.dhan.streaming.order_feed import DhanOrderFeed

# ── Segment mapping ────────────────────────────────────────────────────────

from brokers.common import segments as _segments


def _segment_for(exchange: Exchange) -> str:
    return _segments.dhan_segment_for(exchange)


_EXCHANGE_TO_INSTRUMENT: dict[str, str] = {
    "NSE": "EQUITY",
    "BSE": "EQUITY",
    "NFO": "FUTIDX",  # Default for derivatives; overridden by asset_class
    "MCX": "FUTCOM",
    "INDEX": "EQUITY",
}

_ASSET_CLASS_TO_INSTRUMENT: dict[str, str] = {
    "OPTION": "OPTIDX",
    "FUTURE": "FUTIDX",
    "EQUITY": "EQUITY",
    "INDEX": "EQUITY",
    "COMMODITY": "FUTCOM",
}


def _instrument_type_for(exchange: Exchange, asset_class: str = "") -> str:
    if asset_class:
        mapped = _ASSET_CLASS_TO_INSTRUMENT.get(asset_class.upper())
        if mapped:
            return mapped
    return _EXCHANGE_TO_INSTRUMENT.get(exchange.value, "EQUITY")


_INTERVAL_MAP: dict[str, str] = {
    "1m": "1", "1M": "1", "1": "1",
    "5m": "5", "5M": "5", "5": "5",
    "15m": "15", "15M": "15", "15": "15",
    "30m": "30", "30M": "30", "30": "30",
    "60m": "60", "60M": "60", "60": "60", "1h": "60",
}


def _interval_for(timeframe: str) -> str:
    return _INTERVAL_MAP.get(timeframe, timeframe)


from brokers.common.parsing import parse_epoch as _parse_dhan_timestamp


class DhanProvider(ResolutionMixin, AsyncHttpMixin, StreamHealthMixin):
    """Dhan broker provider implementing the Provider protocol.

    Each method: resolve instrument → call HTTP client → map response →
    return domain entity.  Errors are caught and converted to
    OrderResponse.fail() for trading ops or raised as ProviderError.
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
        "_order_feed",
        "_depth_feed",
        "_resolver",
        "_risk_policy",
    )

    def __init__(
        self,
        *,
        client_id: str,
        access_token: str,
        instruments: dict[str, str] | None = None,
        resolver: InstrumentResolver | None = None,
        event_bus: EventBus | None = None,
        risk_policy: RiskPolicyProtocol | None = None,
        **kwargs: Any,
    ) -> None:
        self._client = DhanHttpClient(
            client_id=client_id,
            access_token=access_token,
            **kwargs,
        )
        self._instruments: dict[str, str] = instruments or {}
        self._resolver = resolver
        self._connected = False
        self._event_bus = event_bus or EventBus()
        self._account: Account | None = None
        self._risk_policy = risk_policy
        self._feed_lock: asyncio.Lock | None = None

        # Streaming feeds (created lazily on first subscribe, stopped in disconnect())
        self._market_feed: DhanMarketFeed | None = None
        self._order_feed: DhanOrderFeed | None = None
        self._depth_feed: DhanDepth20Feed | None = None

        # Extended capabilities
        self._extensions = self._build_extensions()

    # ── Identity ─────────────────────────────────────────────────────

    @property
    def broker_id(self) -> str:
        return "dhan"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities.full("dhan", max_depth_levels=20)

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
                "dhan_default", self, risk_policy=self._risk_policy, event_bus=self._event_bus
            )
        return self._account

    @property
    def extensions(self) -> ExtensionAccess:
        return self._extensions

    def update_token(self, new_token: str) -> None:
        """Hot-swap the access token in the underlying HTTP client.

        Called by the :class:`AuthManager` token receiver when the
        background :class:`DhanTokenScheduler` refreshes the token.
        """
        self._client.update_access_token(new_token)

        # Propagate the refreshed token to any active WS feeds so they
        # reconnect with the new token.  Guard with the feed lock and only
        # touch feeds that are currently running.
        async def _forward() -> None:
            if self._feed_lock is None:
                return
            async with self._feed_lock:
                for feed in (self._market_feed, self._order_feed, self._depth_feed):
                    if feed is not None and feed.is_running and hasattr(feed, "update_token"):
                        feed.update_token(new_token)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(_forward())

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _get_feeds(self) -> list:
        """Return active streaming feeds for health aggregation."""
        return [
            f for f in (self._market_feed, self._order_feed, self._depth_feed)
            if f is not None
        ]

    # stream_health property provided by StreamHealthMixin

    # ── Helpers ──────────────────────────────────────────────────────

    def _broker_fallback(self, instrument: Instrument) -> str:
        """Dhan fallback: return raw symbol (will fail _require_numeric_sid)."""
        return instrument.symbol

    @staticmethod
    def _require_numeric_sid(security_id: str, symbol: str) -> int:
        if not security_id.isdigit():
            raise ValueError(
                f"security_id for {symbol} is not numeric: {security_id!r}. "
                f"Populate instruments dict with correct Dhan security IDs."
            )
        return int(security_id)

    def _resolve_modify_security_id(self, request: ModifyOrderRequest) -> str | None:
        """Best-effort security_id resolution for modify_order.

        Dhan's modify endpoint requires the order's securityId (and ideally
        exchangeSegment / transactionType).  ``ModifyOrderRequest`` may carry
        an ``instrument``, or ``symbol``/``exchange`` attributes.  When none
        are present we return ``None`` and the change-set is sent as-is.
        """
        instrument = getattr(request, "instrument", None)
        if instrument is not None:
            try:
                return self.resolve_broker_id(instrument)
            except Exception:
                return None
        symbol = getattr(request, "symbol", None)
        exchange = getattr(request, "exchange", None)
        if symbol and exchange is not None:
            try:
                return self._broker_fallback_for_symbol(symbol, exchange)
            except Exception:
                return None
        return None



    # ── Market data ──────────────────────────────────────────────────

    async def get_quote(self, instrument: Instrument) -> Quote:
        security_id = self.resolve_broker_id(instrument)
        segment = _segment_for(instrument.exchange)
        sid_int = self._require_numeric_sid(security_id, instrument.symbol)
        data = await self._http(self._client.get_quote, segment, [sid_int])
        segment_data = data.get("data", {}).get(segment, {})
        raw = segment_data.get(str(sid_int)) or segment_data.get(security_id)
        if raw is None:
            raise ProviderError(f"No quote data for {instrument.symbol}")
        return DhanMapper.map_quote(raw, instrument.symbol)

    async def get_ltp(self, instrument: Instrument) -> Decimal:
        security_id = self.resolve_broker_id(instrument)
        segment = _segment_for(instrument.exchange)
        sid_int = self._require_numeric_sid(security_id, instrument.symbol)
        data = await self._http(self._client.get_ltp, segment, [sid_int])
        segment_data = data.get("data", {}).get(segment, {})
        entry = segment_data.get(str(sid_int)) or segment_data.get(security_id)
        if entry is None:
            raise ProviderError(f"No LTP data for {instrument.symbol}")
        return Decimal(str(entry.get("last_price", 0)))

    async def get_depth(self, instrument: Instrument) -> MarketDepth:
        security_id = self.resolve_broker_id(instrument)
        segment = _segment_for(instrument.exchange)
        sid_int = self._require_numeric_sid(security_id, instrument.symbol)
        data = await self._http(self._client.get_quote, segment, [sid_int])
        segment_data = data.get("data", {}).get(segment, {})
        raw = segment_data.get(str(sid_int)) or segment_data.get(security_id)
        if raw is None:
            raise ProviderError(f"No depth data for {instrument.symbol}")
        return DhanMapper.map_depth(raw, instrument.symbol)

    async def get_history(
        self,
        instrument: Instrument,
        *,
        timeframe: str = "1D",
        bars: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> HistoricalSeries:
        security_id = self.resolve_broker_id(instrument)
        segment = _segment_for(instrument.exchange)
        default_from = date.today().replace(day=1)
        default_to = date.today()
        from_str = str(from_date) if from_date else str(default_from)
        to_str = str(to_date) if to_date else str(default_to)
        is_daily = timeframe.upper() in ("1D", "DAILY", "1DAY")
        endpoint = "/charts/historical" if is_daily else "/charts/intraday"
        instrument_type = _instrument_type_for(instrument.exchange, instrument.asset_class.value)
        payload: dict[str, Any] = {
            "securityId": security_id,
            "exchangeSegment": segment,
            "instrument": instrument_type,
            "expiryCode": 0,
            "oi": True,
            "fromDate": from_str,
            "toDate": to_str,
        }
        if not is_daily:
            payload["interval"] = _interval_for(timeframe)
            payload["fromDate"] = f"{from_str} 09:15:00"
            payload["toDate"] = f"{to_str} 15:30:00"
        data = await self._http(self._client.post, endpoint, json=payload)
        items = data.get("data", {}).get("ohlc", data.get("data", []))
        if isinstance(items, dict):
            items = items.get("candles", [])
        items = items if isinstance(items, list) else []

        # Convert to HistoricalBar list
        bar_list: list[HistoricalBar] = []

        for item in items:
            if isinstance(item, list) and len(item) >= 5:
                # [timestamp, open, high, low, close, volume]
                # Dhan returns epoch integers — convert explicitly
                ts = _parse_dhan_timestamp(item[0])
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
            elif isinstance(item, dict):
                ts_raw = item.get("date", item.get("timestamp", ""))
                ts = _parse_dhan_timestamp(ts_raw)
                bar_list.append(HistoricalBar(
                    symbol=instrument.symbol,
                    exchange=instrument.exchange.value,
                    timeframe=timeframe,
                    event_time=ts,
                    open=Decimal(str(item.get("open", 0))),
                    high=Decimal(str(item.get("high", 0))),
                    low=Decimal(str(item.get("low", 0))),
                    close=Decimal(str(item.get("close", 0))),
                    volume=int(item.get("volume", 0)),
                ))

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
        for key, sid in self._instruments.items():
            symbol = key.split(":")[0]
            if q in symbol.upper():
                exchange_str = key.split(":")[1] if ":" in key else "NSE"
                search_results.append(Instrument(
                    symbol=symbol,
                    exchange=Exchange(exchange_str),
                    provider=self,
                    security_id=sid,
                ))
                if len(search_results) >= 20:
                    break
        return search_results

    async def get_instruments(self, exchange: str | None = None) -> list[Instrument]:
        results: list[Instrument] = []
        for key, sid in self._instruments.items():
            parts = key.split(":")
            symbol = parts[0]
            exchange_str = parts[1] if len(parts) > 1 else "NSE"
            if exchange is None or exchange_str == exchange:
                results.append(Instrument(
                    symbol=symbol,
                    exchange=Exchange(exchange_str),
                    provider=self,
                    security_id=sid,
                ))
        return results

    async def resolve_instrument(self, symbol: str, exchange: str) -> Instrument:
        key = f"{symbol}:{exchange}"
        sid = self._instruments.get(key, symbol)
        lot_size = 1
        tick_size = DEFAULT_TICK_SIZE
        trading_symbol = ""
        if self._resolver is not None:
            try:
                resolved = self._resolver.resolve(symbol, Exchange(exchange))
                sid = resolved.broker_id
                lot_size = resolved.lot_size
                tick_size = resolved.tick_size
                trading_symbol = resolved.trading_symbol
            except InstrumentNotFoundError:
                pass
        return Instrument(
            symbol=symbol,
            exchange=Exchange(exchange),
            provider=self,
            security_id=sid,
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

        segment = _segment_for(underlying.exchange)
        security_id = self.resolve_broker_id(underlying)
        payload = {
            "UnderlyingScrip": self._require_numeric_sid(security_id, underlying.symbol),
            "UnderlyingSeg": segment,
            "Expiry": str(expiry) if expiry else "",
        }
        data = await self._http(self._client.get_option_chain, payload)
        raw_chain: dict[str, Any] | list[Any] = data.get("data") or {}
        return parse_option_chain(raw_chain, underlying, self, expiry)

    async def get_future_chain(self, underlying: Instrument) -> FutureChain:
        # Dhan future chain endpoint varies — return empty for now
        return FutureChain(underlying=underlying, contracts=[])

    # ── Execution ────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        try:
            security_id = self.resolve_for_order(request)
            segment = _segment_for(request.exchange)
            payload = DhanMapper.build_order_payload(
                request, security_id, segment, self._client.client_id
            )
            data = await self._http(self._client.place_order, payload)

            # Check for broker-level error: errorCode or status=="failure"
            raw = data if isinstance(data, dict) else {}
            broker_status = str(raw.get("status", "")).lower()
            if broker_status in ("failure", "error"):
                return OrderResponse.fail(
                    str(raw.get("remarks", raw.get("errorMessage", "Order failed"))),
                    error_code=str(raw.get("errorCode", "")),
                )

            order_data = raw.get("data", raw) if isinstance(raw, dict) else {}
            if isinstance(order_data, dict) and order_data.get("errorCode"):
                return OrderResponse.fail(
                    str(order_data.get("errorMessage", "Order failed")),
                    error_code=str(order_data.get("errorCode", "")),
                )

            order_id = str(order_data.get("orderId", ""))
            return OrderResponse.ok(order_id=order_id, message="Order placed", status=OrderStatus.OPEN)
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="DHAN_HTTP_ERROR")
        except Exception as exc:
            # Catch-all for unexpected errors (malformed response, mapper errors, etc.)
            # This prevents programming bugs from crashing order placement.
            return OrderResponse.fail(str(exc), error_code="INTERNAL_ERROR")

    async def cancel_order(self, order_id: str) -> OrderResponse:
        try:
            data = await self._http(self._client.cancel_order, order_id)
            raw = data if isinstance(data, dict) else {}

            # Dhan's cancel response has NO top-level "status" field; it uses
            # orderStatus / orderId. Detect success via presence of orderId and/or
            # a terminal orderStatus rather than a top-level "status"=="success".
            order_status = str(raw.get("orderStatus", "")).upper()
            data_block = raw.get("data") if isinstance(raw.get("data"), dict) else {}
            has_order_id = bool(str(raw.get("orderId", ""))) or bool(str(data_block.get("orderId", "")))
            if raw.get("errorCode"):
                return OrderResponse.fail(
                    str(raw.get("errorMessage", "Cancel failed")),
                    error_code=str(raw.get("errorCode", "")),
                )
            if has_order_id or order_status in ("CANCELLED", "CANCELED", "SUCCESS"):
                return OrderResponse.ok(
                    order_id=order_id, message="Order cancelled", status=OrderStatus.CANCELLED
                )

            broker_status = str(raw.get("status", "")).lower()
            if broker_status in ("success", "ok"):
                return OrderResponse.ok(
                    order_id=order_id, message="Order cancelled", status=OrderStatus.CANCELLED
                )
            if broker_status in ("failure", "error"):
                return OrderResponse.fail(
                    str(raw.get("remarks", raw.get("errorMessage", "Cancel failed"))),
                    error_code=str(raw.get("errorCode", "")),
                )
            # Unrecognized but non-error response — treat as cancelled.
            return OrderResponse.ok(
                order_id=order_id, message="Order cancelled", status=OrderStatus.CANCELLED
            )
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="DHAN_HTTP_ERROR")
        except Exception as exc:
            return OrderResponse.fail(str(exc), error_code="INTERNAL_ERROR")

    async def modify_order(self, request: ModifyOrderRequest) -> OrderResponse:
        try:
            # Build the change-set (only the fields the caller wants modified).
            changes = {k: v for k, v in {
                "quantity": request.quantity,
                "price": request.price,
                "triggerPrice": request.trigger_price,
                "orderType": request.order_type.value if request.order_type else None,
                "validity": request.validity.value if request.validity else None,
                "productType": request.product_type.value if request.product_type else None,
            }.items() if v is not None}

            # Include the required Dhan modify identifiers
            # (securityId / exchangeSegment / transactionType) when we can
            # resolve them — mirroring place_order.  The securityId is taken
            # from the resolved instrument (or request.symbol/exchange); the
            # exchangeSegment/transactionType are derived from the instrument
            # or a request.side attribute when present.
            instrument = getattr(request, "instrument", None)
            security_id = self._resolve_modify_security_id(request)
            if security_id is not None:
                changes["securityId"] = security_id
                if instrument is not None and getattr(instrument, "exchange", None) is not None:
                    changes["exchangeSegment"] = _segment_for(instrument.exchange)
                side = getattr(request, "side", None) or getattr(request, "transaction_type", None)
                if side is not None:
                    changes["transactionType"] = side.value if hasattr(side, "value") else side

            data = await self._http(self._client.modify_order, request.order_id, changes)
            raw = data if isinstance(data, dict) else {}
            broker_status = str(raw.get("status", "")).lower()
            if broker_status in ("failure", "error"):
                return OrderResponse.fail(
                    str(raw.get("remarks", raw.get("errorMessage", "Modify failed"))),
                    error_code=str(raw.get("errorCode", "")),
                )
            if isinstance(raw, dict) and raw.get("errorCode"):
                return OrderResponse.fail(
                    str(raw.get("errorMessage", "Modify failed")),
                    error_code=str(raw.get("errorCode", "")),
                )
            return OrderResponse.ok(order_id=request.order_id, message="Order modified")
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="DHAN_HTTP_ERROR")
        except Exception as exc:
            return OrderResponse.fail(str(exc), error_code="INTERNAL_ERROR")

    # ── Portfolio ────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        data = await self._http(self._client.get_positions)
        items = data.get("data", []) if isinstance(data, dict) else []
        return [DhanMapper.map_position(item) for item in (items if isinstance(items, list) else [])]

    async def get_balance(self) -> Balance:
        data = await self._http(self._client.get_funds)
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return DhanMapper.map_balance(raw if isinstance(raw, dict) else {})

    async def get_orders(self) -> list[Order]:
        from brokers.domain.order import Order
        data = await self._http(self._client.get_orderbook)
        items = data.get("data", []) if isinstance(data, dict) else []
        return [DhanMapper.map_order(item) for item in (items if isinstance(items, list) else [])]

    async def get_trades(self) -> list[Trade]:
        data = await self._http(self._client.get_trades)
        items = data.get("data", []) if isinstance(data, dict) else []
        return [DhanMapper.map_trade(item) for item in (items if isinstance(items, list) else [])]

    async def get_holdings(self) -> list[Holding]:
        data = await self._http(self._client.get_holdings)
        items = data.get("data", []) if isinstance(data, dict) else []
        return [DhanMapper.map_holding(item) for item in (items if isinstance(items, list) else [])]

    # ── Streaming ────────────────────────────────────────────────────

    async def subscribe_quotes(
        self,
        instruments: list[Instrument],
        *,
        on_tick: Callable[[Quote], None] | None = None,
    ) -> Subscription:
        """Subscribe to real-time quote updates via DhanMarketFeed.

        Creates and starts the market feed lazily on first call.
        Callbacks are wrapped to convert MarketTickEvent → Quote.
        """
        feed = await self._ensure_market_feed()

        # Wrap tick callback for MarketTickEvent → Quote conversion
        if on_tick is not None:
            def _tick_to_quote(event: MarketTickEvent) -> None:
                on_tick(Quote(symbol=event.symbol, ltp=Decimal(str(event.ltp))))
            feed.set_tick_callback(_tick_to_quote)

        async def _cancel() -> None:
            for inst in instruments:
                sid = self.resolve_broker_id(inst)
                key = InstrumentKey(
                    symbol=inst.symbol, exchange=inst.exchange.value, security_id=sid,
                )
                await feed.unsubscribe(key)

        sub = Subscription(Subscription.create_id(), _cancel)

        for inst in instruments:
            sid = self.resolve_broker_id(inst)
            key = InstrumentKey(
                symbol=inst.symbol, exchange=inst.exchange.value, security_id=sid,
            )
            await feed.subscribe(key, mode=StreamMode.QUOTE)

        return sub

    async def subscribe_depth(
        self,
        instruments: list[Instrument],
        *,
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Subscription:
        """Subscribe to real-time depth updates via DhanDepth20Feed.

        Creates and starts the depth feed lazily on first call.
        """
        feed = await self._ensure_depth_feed()

        if on_depth is not None:
            def _event_to_depth(event: MarketTickEvent) -> None:
                on_depth(MarketDepth(
                    symbol=event.symbol,
                    bids=[DepthLevel(price=Decimal(str(b[0])), quantity=int(b[1]))
                          for b in (event.depth_bids or ())],
                    asks=[DepthLevel(price=Decimal(str(a[0])), quantity=int(a[1]))
                          for a in (event.depth_asks or ())],
                    depth_type="DEPTH_20",
                ))

            # Depth feed callback is set via public API
            feed.set_on_depth(_event_to_depth)

        async def _cancel() -> None:
            for inst in instruments:
                sid = self.resolve_broker_id(inst)
                key = InstrumentKey(
                    symbol=inst.symbol, exchange=inst.exchange.value, security_id=sid,
                )
                await feed.unsubscribe(key)

        sub = Subscription(Subscription.create_id(), _cancel)

        for inst in instruments:
            sid = self.resolve_broker_id(inst)
            key = InstrumentKey(
                symbol=inst.symbol, exchange=inst.exchange.value, security_id=sid,
            )
            await feed.subscribe(key)

        return sub

    async def subscribe_orders(
        self,
        *,
        on_update: Callable[[Any], None] | None = None,
    ) -> Subscription:
        """Subscribe to order status updates via DhanOrderFeed.

        Creates and starts the order feed lazily on first call.
        """
        feed = await self._ensure_order_feed()
        feed.add_subscriber()

        if on_update is not None:
            feed.set_order_callback(on_update)

        async def _cancel() -> None:
            await feed.remove_subscriber()

        return Subscription(Subscription.create_id(), _cancel)

    async def unsubscribe(self, subscription: Subscription) -> None:
        await subscription.cancel()

    # ── Lifecycle ────────────────────────────────────────────────────

    # ── Async extension adapters ─────────────────────────────────────
    # The typed extension protocols (provider/extensions.py) are async, but
    # the underlying Dhan extended modules are synchronous.  These thin
    # wrappers satisfy the async protocols by offloading the sync client
    # calls to the thread pool via asyncio.to_thread.

    class _AsyncSuperOrders:
        def __init__(self, sync: Any) -> None:
            self._s = sync

        async def place(self, request: Any) -> Any:
            return await asyncio.to_thread(self._s.place, request)

    class _AsyncForeverOrders:
        def __init__(self, sync: Any) -> None:
            self._s = sync

        async def place(self, **kwargs: Any) -> Any:
            return await asyncio.to_thread(self._s.place, **kwargs)

        async def cancel(self, order_id: str) -> Any:
            return await asyncio.to_thread(self._s.cancel, order_id)

        async def list(self) -> list[Any]:
            return await asyncio.to_thread(self._s.get_orders)

    class _AsyncMargin:
        def __init__(self, sync: Any) -> None:
            self._s = sync

        async def calculate(self, **kwargs: Any) -> Any:
            return await asyncio.to_thread(self._s.calculate, **kwargs)

    class _AsyncExitAll:
        def __init__(self, sync: Any) -> None:
            self._s = sync

        async def exit_all(self) -> Any:
            return await asyncio.to_thread(self._s.execute)

    class _DhanDepthExtension:
        """Async depth extension backed by the live depth feed(s)."""

        def __init__(self, provider: DhanProvider, depth_type: str) -> None:
            self._provider = provider
            self._depth_type = depth_type

        async def get(self) -> dict[str, Any]:
            if self._depth_type == "DEPTH_200":
                from brokers.dhan.streaming.depth_feed import Depth200ConnectionPool

                pool = Depth200ConnectionPool(
                    client_id=self._provider._client.client_id,
                    access_token=self._provider._client.get_access_token(),
                )
                result: dict[str, Any] = {}
                for feed in pool._feeds.values():
                    result.update(dict(feed._depth_cache))
                return result
            feed = await self._provider._ensure_depth_feed()
            return dict(feed._depth_cache)

    def _build_extensions(self) -> ExtensionAccess:
        """Build ExtensionAccess with all Dhan extended capabilities."""
        from brokers.dhan.extended.alerts import DhanAlerts
        from brokers.dhan.extended.conditional_triggers import DhanConditionalTriggers
        from brokers.dhan.extended.convert_position import DhanConvertPosition
        from brokers.dhan.extended.edis import DhanEdis
        from brokers.dhan.extended.exit_all import DhanExitAll
        from brokers.dhan.extended.expired_options import DhanExpiredOptions
        from brokers.dhan.extended.forever_orders import DhanForeverOrders
        from brokers.dhan.extended.ip_management import DhanIpManagement
        from brokers.dhan.extended.kill_switch import DhanKillSwitch
        from brokers.dhan.extended.ledger import DhanLedger
        from brokers.dhan.extended.margin import DhanMargin
        from brokers.dhan.extended.order_lookup import DhanOrderLookup
        from brokers.dhan.extended.slice_order import DhanSliceOrder
        from brokers.dhan.extended.super_orders import DhanSuperOrders
        from brokers.dhan.extended.user_profile import DhanUserProfile

        # Sync instances (also used directly by the facade / tests).
        super_orders = DhanSuperOrders(client=self._client)
        forever_orders = DhanForeverOrders(client=self._client)
        margin = DhanMargin(client=self._client)
        exit_all = DhanExitAll(client=self._client)

        return ExtensionAccess(
            self,
            extensions={
                "alerts": DhanAlerts(client=self._client),
                "conditional_triggers": DhanConditionalTriggers(client=self._client),
                "convert_position": DhanConvertPosition(client=self._client),
                "depth20": self._DhanDepthExtension(self, "DEPTH_20"),
                "depth200": self._DhanDepthExtension(self, "DEPTH_200"),
                "edis": DhanEdis(client=self._client),
                "exit_all": self._AsyncExitAll(exit_all),
                "expired_options": DhanExpiredOptions(client=self._client),
                "forever_orders": self._AsyncForeverOrders(forever_orders),
                "ip_management": DhanIpManagement(client=self._client),
                "kill_switch": DhanKillSwitch(client=self._client),
                "ledger": DhanLedger(client=self._client),
                "margin": self._AsyncMargin(margin),
                "order_lookup": DhanOrderLookup(client=self._client),
                "slice_order": DhanSliceOrder(client=self._client),
                "super_orders": self._AsyncSuperOrders(super_orders),
                "user_profile": DhanUserProfile(client=self._client),
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
            if self._order_feed is not None:
                coros.append(self._order_feed.stop())
                self._order_feed = None
            if self._depth_feed is not None:
                coros.append(self._depth_feed.stop())
                self._depth_feed = None
            if coros:
                await asyncio.gather(*coros)
            self._connected = False

    async def _ensure_market_feed(self) -> DhanMarketFeed:
        """Lazily create and start the market feed (thread-safe via asyncio.Lock)."""
        if self._feed_lock is None:
            self._feed_lock = asyncio.Lock()
        async with self._feed_lock:
            if self._market_feed is None or not self._market_feed.is_running:
                from brokers.dhan.streaming.market_feed import DhanMarketFeed

                self._market_feed = DhanMarketFeed(
                    client_id=self._client.client_id,
                    access_token=self._client.get_access_token(),
                )
                await self._market_feed.start()
            return self._market_feed

    async def _ensure_order_feed(self) -> DhanOrderFeed:
        """Lazily create and start the order feed (thread-safe via asyncio.Lock)."""
        if self._feed_lock is None:
            self._feed_lock = asyncio.Lock()
        async with self._feed_lock:
            if self._order_feed is None or not self._order_feed.is_running:
                from brokers.dhan.streaming.order_feed import DhanOrderFeed

                self._order_feed = DhanOrderFeed(
                    client_id=self._client.client_id,
                    access_token=self._client.get_access_token(),
                )
                await self._order_feed.start()
            return self._order_feed

    async def _ensure_depth_feed(self) -> DhanDepth20Feed:
        """Lazily create and start the depth feed (thread-safe via asyncio.Lock)."""
        if self._feed_lock is None:
            self._feed_lock = asyncio.Lock()
        async with self._feed_lock:
            if self._depth_feed is None or not self._depth_feed.is_running:
                from brokers.dhan.streaming.depth_feed import DhanDepth20Feed

                self._depth_feed = DhanDepth20Feed(
                    client_id=self._client.client_id,
                    access_token=self._client.get_access_token(),
                )
                await self._depth_feed.start()
            return self._depth_feed


__all__ = ["DhanProvider"]
