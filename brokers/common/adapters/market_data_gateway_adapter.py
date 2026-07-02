"""Wrap sync MarketDataGateway instances as CommonBrokerGateway adapters."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections.abc import Sequence
from typing import Any

from brokers.common.adapters.historical_mapper import dataframe_to_historical_bars
from brokers.common.broker_port import (
    BrokerHealthSnapshot,
    BrokerStreamHandle,
    BrokerStreamPlan,
    HistoricalBarRequest,
    QuotaToken,
)
from brokers.common.capabilities import BrokerCapabilities, CapabilityDescriptor
from brokers.common.gateway import MarketDataGateway
from domain.entities import Balance, Order, OrderResponse, Position, Quote, Trade
from domain.entities.market import MarketDepth
from domain.historical import InstrumentRef
from domain.requests import ModifyOrderRequest, OrderRequest

logger = logging.getLogger(__name__)

def capabilities_for_gateway(gateway: MarketDataGateway, broker_id: str) -> BrokerCapabilities:
    get_capabilities = getattr(gateway, "capabilities", None)
    if callable(get_capabilities):
        capabilities = get_capabilities()
        if isinstance(capabilities, BrokerCapabilities):
            return capabilities
    return BrokerCapabilities(broker_id=broker_id)


class _GatewayStreamHandle:
    """Stream handle wrapping a legacy gateway feed object with subscription tracking."""

    def __init__(
        self,
        adapter: MarketDataGatewayAdapter,
        feed: Any,
        instruments: list[str],
        on_tick: Any,
        *,
        stream_kind: str = "market",
    ) -> None:
        self._adapter = adapter
        self._feed = feed
        self._instruments = list(instruments)
        self._on_tick = on_tick
        self._stream_kind = stream_kind
        self._broker_id = adapter.broker_id
        self._session_id = str(uuid.uuid4())

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def broker_id(self) -> str:
        return self._broker_id

    async def disconnect(self) -> None:
        if self._stream_kind == "order":
            unstream_order = getattr(self._adapter.legacy_gateway, "unstream_order", None)
            if callable(unstream_order):
                await asyncio.to_thread(unstream_order, self._on_tick)
            await self._adapter.release_order_stream(self)
            return

        # Market stream: unstream each instrument
        for instrument_key in self._instruments:
            if ":" in instrument_key:
                symbol, exchange = instrument_key.split(":", 1)
            else:
                symbol, exchange = instrument_key, "NSE"

            await asyncio.to_thread(
                self._adapter.legacy_gateway.unstream,
                symbol,
                exchange,
                self._on_tick,
            )

        await self._adapter.release_market_stream(self)

    def is_connected(self) -> bool:
        if self._feed is None:
            return False
        health = getattr(self._feed, "health", None)
        if callable(health):
            try:
                snapshot = health()
                metrics = getattr(snapshot, "metrics", {}) or {}
                if metrics.get("is_stale"):
                    return False
            except Exception:
                logger.debug("stream_handle_health_check_failed", exc_info=True)
        connected = getattr(self._feed, "is_connected", None)
        if callable(connected):
            return bool(connected())
        return bool(connected)


class MarketDataGatewayAdapter:
    """Adapts a legacy ``MarketDataGateway`` to ``CommonBrokerGateway``."""

    def __init__(
        self,
        gateway: MarketDataGateway,
        broker_id: str,
        *,
        capabilities: BrokerCapabilities | None = None,
        extensions: frozenset[str] | None = None,
    ) -> None:
        self._gateway = gateway
        self._broker_id = broker_id
        self._capabilities = capabilities or capabilities_for_gateway(gateway, broker_id)
        self._extensions = extensions or frozenset()
        self._active_market_handles: set[str] = set()
        self._active_order_handles: set[str] = set()
        self._handle_lock = threading.Lock()

    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def legacy_gateway(self) -> MarketDataGateway:
        """Underlying MarketDataGateway — for transitional call sites."""
        return self._gateway

    def list_capabilities(self) -> CapabilityDescriptor:
        return CapabilityDescriptor.build(self._capabilities, self._extensions)

    def supports(self, feature: str) -> bool:
        return self._capabilities.supports(feature)

    async def place_order(self, request: OrderRequest, *, quota: QuotaToken) -> OrderResponse:
        return await asyncio.to_thread(self._place_order_sync, request)

    def _place_order_sync(self, request: OrderRequest) -> OrderResponse:
        kwargs = {
            "symbol": request.symbol,
            "exchange": request.exchange,
            "side": request.transaction_type.value,
            "quantity": request.quantity,
            "price": request.price,
            "order_type": request.order_type.value,
            "product_type": request.product_type.value,
            "validity": request.validity.value,
            "trigger_price": request.trigger_price or request.price,
            "correlation_id": request.correlation_id,
        }
        return self._gateway.place_order(**kwargs)

    async def cancel_order(self, order_id: str, *, quota: QuotaToken) -> OrderResponse:
        return await asyncio.to_thread(self._gateway.cancel_order, order_id)

    async def modify_order(
        self, request: ModifyOrderRequest, *, quota: QuotaToken
    ) -> OrderResponse:
        changes = {}
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

    async def get_quote_snapshot(self, instrument: InstrumentRef, *, quota: QuotaToken) -> Quote:
        return await asyncio.to_thread(self._gateway.quote, instrument.symbol, instrument.exchange)

    async def get_depth_snapshot(
        self, instrument: InstrumentRef, *, quota: QuotaToken
    ) -> MarketDepth:
        return await asyncio.to_thread(self._gateway.depth, instrument.symbol, instrument.exchange)

    async def get_historical_bars(
        self, request: HistoricalBarRequest, *, quota: QuotaToken
    ) -> Sequence:
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
            df,
            request.instrument,
            request.timeframe,
            self._broker_id,
            request.request_id,
        )

    async def open_market_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        feed = None
        mode = next(iter(plan.modes), "LTP") if plan.modes else "LTP"

        def _on_tick(data: Any) -> None:
            if plan.on_raw_frame is None:
                return
            if hasattr(data, "__dict__"):
                frame = {
                    "symbol": getattr(data, "symbol", ""),
                    "exchange": "NSE",
                    "ltp": float(getattr(data, "ltp", 0)),
                    "volume": int(getattr(data, "volume", 0)),
                }
            elif isinstance(data, dict):
                frame = data
            else:
                frame = {"ltp": data}
            plan.on_raw_frame(frame)

        for instrument_key in plan.instruments:
            if ":" in instrument_key:
                symbol, exchange = instrument_key.split(":", 1)
            else:
                symbol, exchange = instrument_key, "NSE"
            feed = await asyncio.to_thread(
                self._gateway.stream,
                symbol,
                exchange,
                mode,
                _on_tick,
            )

        handle = _GatewayStreamHandle(self, feed, plan.instruments, _on_tick)
        with self._handle_lock:
            self._active_market_handles.add(handle.session_id)
        return handle

    async def open_order_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        def _on_order(data: Any) -> None:
            if plan.on_raw_frame is None:
                return
            frame = data if isinstance(data, dict) else {"order_id": str(data)}
            plan.on_raw_frame(frame)

        stream_order = getattr(self._gateway, "stream_order", None)
        if not callable(stream_order):
            raise RuntimeError(
                f"Gateway {self._broker_id!r} does not implement stream_order()"
            )

        feed = await asyncio.to_thread(stream_order, _on_order)
        handle = _GatewayStreamHandle(
            self, feed, list(plan.instruments), _on_order, stream_kind="order"
        )
        with self._handle_lock:
            self._active_order_handles.add(handle.session_id)
        return handle

    async def release_market_stream(self, handle: _GatewayStreamHandle) -> None:
        with self._handle_lock:
            if handle.session_id in self._active_market_handles:
                self._active_market_handles.remove(handle.session_id)

            # Only stop the physical feed if no active logical handles remain
            if not self._active_market_handles and handle._feed is not None:
                disconnect = getattr(handle._feed, "disconnect", None)
                if callable(disconnect):
                    await asyncio.to_thread(disconnect)

    async def release_order_stream(self, handle: _GatewayStreamHandle) -> None:
        with self._handle_lock:
            if handle.session_id in self._active_order_handles:
                self._active_order_handles.remove(handle.session_id)

            if not self._active_order_handles and handle._feed is not None:
                stop = getattr(handle._feed, "stop", None)
                disconnect = getattr(handle._feed, "disconnect", None)
                if callable(stop):
                    await asyncio.to_thread(stop, 5.0)
                elif callable(disconnect):
                    await asyncio.to_thread(disconnect)

    async def health(self) -> BrokerHealthSnapshot:
        describe = await asyncio.to_thread(self._gateway.describe)
        connected = bool(describe.get("connected", True))
        return BrokerHealthSnapshot(
            broker_id=self._broker_id,
            alive=connected,
            auth_valid=connected,
            reason="" if connected else "disconnected",
        )

    async def close(self) -> None:
        await asyncio.to_thread(self._gateway.close)


def wrap_market_gateway(
    gateway: MarketDataGateway,
    broker_id: str,
    *,
    capabilities: BrokerCapabilities | None = None,
    extensions: frozenset[str] | None = None,
) -> MarketDataGatewayAdapter:
    """Wrap a legacy gateway as CommonBrokerGateway."""
    return MarketDataGatewayAdapter(
        gateway,
        broker_id,
        capabilities=capabilities,
        extensions=extensions,
    )
