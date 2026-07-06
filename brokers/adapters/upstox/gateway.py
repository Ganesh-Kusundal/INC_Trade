"""Upstox gateway — composes all Upstox adapters into a single interface."""

from __future__ import annotations

import logging
from typing import Any, cast

from brokers.domain.capabilities import BrokerCapabilities
from brokers.domain.enums import BrokerID
from brokers.ports.capabilities import (
    GTTProvider,
    NewsProvider,
)
from brokers.ports.extension_registry import ExtensionRegistryPort
from brokers.ports.streaming import StreamingPort

from brokers.adapters.base_streaming import StreamHandle
from brokers.adapters.upstox.auth.config import UpstoxConnectionSettings
from brokers.adapters.upstox.capabilities import upstox_capabilities
from brokers.adapters.upstox.composition import (
    UpstoxComponents,
    apply_components_to_gateway,
    build_upstox_components,
    teardown_upstox_components,
)
from brokers.adapters.upstox.extended import UpstoxExtended
from brokers.adapters.upstox.gtt import UpstoxGtt
from brokers.adapters.upstox.historical import UpstoxHistorical
from brokers.adapters.upstox.instruments import UpstoxInstruments
from brokers.adapters.upstox.market_data import UpstoxMarketData
from brokers.adapters.upstox.metrics import UpstoxMetrics
from brokers.adapters.upstox.news import UpstoxNews
from brokers.adapters.upstox.options import UpstoxOptions
from brokers.adapters.upstox.orders import UpstoxOrders
from brokers.adapters.upstox.portfolio import UpstoxPortfolio
from brokers.adapters.upstox.portfolio_stream import UpstoxPortfolioStream
from brokers.adapters.upstox.streaming import UpstoxStreaming

logger = logging.getLogger(__name__)


class UpstoxGateway:
    """Upstox broker gateway — facade for BrokerFacade / brokers.connect()."""

    _broker_id: BrokerID = BrokerID.UPSTOX

    @property
    def broker_id(self) -> BrokerID:
        return self._broker_id

    def capabilities(self) -> BrokerCapabilities:
        return upstox_capabilities()

    def __init__(
        self,
        access_token: str | None = None,
        settings: UpstoxConnectionSettings | None = None,
        allow_live_orders: bool | None = None,
        auto_refresh: bool = True,
        lifecycle: Any | None = None,
        load_instruments: bool = False,
    ) -> None:
        components = build_upstox_components(
            access_token=access_token,
            settings=settings,
            allow_live_orders=allow_live_orders,
            auto_refresh=auto_refresh,
            lifecycle=lifecycle,
            load_instruments=load_instruments,
        )
        self._components = components
        apply_components_to_gateway(self, components)

    @property
    def orders(self) -> UpstoxOrders:
        return self._orders

    @property
    def market_data(self) -> UpstoxMarketData:
        return self._market_data

    @property
    def portfolio(self) -> UpstoxPortfolio:
        return self._portfolio

    @property
    def instruments(self) -> UpstoxInstruments:
        return self._instruments

    @property
    def auth(self) -> Any:
        return self._auth

    @property
    def historical(self) -> UpstoxHistorical:
        return self._historical

    @property
    def streaming(self) -> StreamingPort:
        return self._streaming

    @property
    def news(self) -> UpstoxNews:
        return self._news

    @property
    def options(self) -> UpstoxOptions:
        return self._options

    @property
    def extended(self) -> UpstoxExtended:
        return self._extended

    @property
    def gtt(self) -> UpstoxGtt:
        return self._gtt

    @property
    def portfolio_stream(self) -> UpstoxPortfolioStream:
        return self._portfolio_stream

    @property
    def extensions(self) -> ExtensionRegistryPort:
        if not hasattr(self, "_extension_registry"):
            from brokers.ports.extension_registry import DictExtensionRegistry

            self._extension_registry = DictExtensionRegistry()
            self._extension_registry.register("upstox", cast("type", NewsProvider), self._news)
            self._extension_registry.register("upstox", cast("type", GTTProvider), self._gtt)
        return self._extension_registry

    @property
    def metrics(self) -> UpstoxMetrics:
        return self._metrics

    def load_instruments(self, source: str | None = None) -> None:
        self._instruments.load(source=source)

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Any]:
        return self._market_data.ltp_batch(symbols, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Any]:
        return self._market_data.quote_batch(symbols, exchange)

    def option_chain(self, underlying: str, exchange: str = "NFO", expiry: str | None = None):
        return self._options.get_option_chain(underlying, exchange, expiry)

    def get_connection_status(self) -> dict[str, bool]:
        return {
            "market_data_ws": self._streaming.is_connected,
            "portfolio_stream": self._portfolio_stream.is_connected,
        }

    def get_token_refresh_metrics(self) -> dict[str, int]:
        return self._metrics.token_refresh_snapshot()

    def stream_depth(
        self,
        symbol: str,
        exchange: str = "NSE",
        depth_type: str = "DEPTH_5",
        on_depth: Any = None,
    ) -> Any:
        mode = "full_d30" if depth_type == "DEPTH_30" else "full"
        self._streaming.mode = mode
        self._streaming.on_depth = on_depth
        self._streaming.subscribe(symbol, exchange)
        if not self._streaming.is_connected:
            self._streaming.start()
        return StreamHandle(self._streaming, symbol, exchange)

    def close(self) -> None:
        teardown_upstox_components(self._components)
