"""Upstox gateway — composes all Upstox adapters into BrokerGateway."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from brokers.adapters.base_streaming import StreamHandle
from brokers.adapters.upstox.auth import UpstoxAuth
from brokers.adapters.upstox.auth.config import (
    UpstoxConnectionSettings,
    UpstoxSettingsLoader,
)
from brokers.adapters.upstox.capabilities import upstox_capabilities
from brokers.adapters.upstox.extended import UpstoxExtended
from brokers.adapters.upstox.feed_authorizer import UpstoxFeedAuthorizer
from brokers.adapters.upstox.gtt import UpstoxGtt
from brokers.adapters.upstox.historical import UpstoxHistorical
from brokers.adapters.upstox.http_client import create_upstox_http_client
from brokers.adapters.upstox.instruments import UpstoxInstruments
from brokers.adapters.upstox.market_data import UpstoxMarketData
from brokers.adapters.upstox.metrics import UpstoxMetrics
from brokers.adapters.upstox.news import UpstoxNews
from brokers.adapters.upstox.options import UpstoxOptions
from brokers.adapters.upstox.orders import UpstoxOrders
from brokers.adapters.upstox.portfolio import UpstoxPortfolio
from brokers.adapters.upstox.portfolio_stream import UpstoxPortfolioStream
from brokers.adapters.upstox.streaming import UpstoxStreaming
from brokers.adapters.upstox.urls import resolve_upstox_urls
from brokers.domain.capabilities import BrokerCapabilities
from brokers.domain.enums import BrokerID
from brokers.ports.capabilities import (
    GTTProvider,
    NewsProvider,
)
from brokers.ports.extension_registry import ExtensionRegistry, ExtensionRegistryPort
from brokers.ports.streaming import StreamingPort

logger = logging.getLogger(__name__)


class UpstoxGateway:
    """Upstox broker adapter implementing BrokerGateway protocol."""

    _broker_id: BrokerID = BrokerID.UPSTOX

    @property
    def broker_id(self) -> BrokerID:
        """Canonical broker identifier."""
        return self._broker_id

    def capabilities(self) -> BrokerCapabilities:
        """Return Upstox broker capability matrix."""
        return upstox_capabilities()

    def __init__(
        self,
        access_token: str | None = None,
        settings: UpstoxConnectionSettings | None = None,
        allow_live_orders: bool | None = None,
        auto_refresh: bool = True,
        lifecycle: Any | None = None,
        load_instruments: bool = False,
    ):
        if settings is None:
            try:
                settings = UpstoxSettingsLoader.from_env()
            except ValueError:
                settings = UpstoxConnectionSettings(
                    client_id="default",
                    access_token=access_token or "",
                    allow_live_orders=allow_live_orders if allow_live_orders is not None else False,
                )

        if access_token is not None:
            settings = replace(
                settings,
                access_token=access_token,
                auth_mode="STATIC",
                token_state_file=None,
                analytics_only=False,
                allow_live_orders=(allow_live_orders if allow_live_orders is not None else True),
            )

        self._settings = settings
        self._urls = resolve_upstox_urls(settings.environment)
        self._metrics = UpstoxMetrics()
        self._auth = UpstoxAuth(settings=settings)

        self._auth.acquire()

        def _refresh_and_get() -> str | None:
            if self._auth.try_refresh_on_401():
                token = self._auth.get_token()
                if token:
                    self._auth.force_refresh_callbacks(token)  # Trigger broadcast
                return token
            return None

        self._client = create_upstox_http_client(
            access_token=self._auth.get_token(),
            token_refresh_fn=_refresh_and_get,
            base_url_v2=settings.base_v2,
            base_url_hft=settings.base_hft,
        )

        self._feed_authorizer = UpstoxFeedAuthorizer(self._client, environment=settings.environment)

        self._portfolio = UpstoxPortfolio(self._client, self._urls)
        self._instruments = UpstoxInstruments(cache_path=settings.instrument_cache_path)
        self._historical = UpstoxHistorical(
            self._client,
            urls=self._urls,
            instruments=self._instruments,
        )
        self._news = UpstoxNews(self._client, self._urls)
        self._options = UpstoxOptions(
            self._client, self._instruments, environment=settings.environment
        )
        self._extended = UpstoxExtended(self._client, environment=settings.environment)
        self._gtt = UpstoxGtt(self._client, environment=settings.environment)

        if load_instruments:
            self.load_instruments()

        self._market_data = UpstoxMarketData(self._client, self._urls, self._instruments)
        self._orders = UpstoxOrders(
            self._client,
            self._urls,
            analytics_only=settings.analytics_only,
            instruments=self._instruments,
        )
        self._streaming = UpstoxStreaming(
            access_token=self._auth.get_token,
            feed_authorizer=self._feed_authorizer,
            instruments=self._instruments,
        )
        self._portfolio_stream = UpstoxPortfolioStream(
            feed_authorizer=self._feed_authorizer,
            token_provider=self._auth.get_token,
        )

        self._auth.on_token_change(self._streaming.update_access_token)
        self._auth.on_token_change(self._portfolio_stream.update_access_token)
        self._auth.on_token_change(self._client.update_token)

        self._scheduler = None
        if auto_refresh and settings.is_totp and settings.has_totp_config:
            from brokers.adapters.upstox.auth.totp_scheduler import TotpRefreshScheduler

            self._scheduler = TotpRefreshScheduler(
                token_manager=self._auth.manager,
                refresh_hour=settings.totp_refresh_hour,
                refresh_minute=settings.totp_refresh_minute,
            )
            if lifecycle is not None:
                lifecycle.register(self._scheduler)
            else:
                self._scheduler.start()

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
    def auth(self) -> UpstoxAuth:
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
        """Registry of broker-specific extensions."""
        if not hasattr(self, "_extension_registry"):
            from brokers.ports.extension_registry import DictExtensionRegistry

            self._extension_registry = DictExtensionRegistry()
            from typing import cast
            # Register extensions
            self._extension_registry.register("upstox", cast(type, NewsProvider), self._news)
            self._extension_registry.register("upstox", cast(type, GTTProvider), self._gtt)
        return self._extension_registry

    @property
    def metrics(self) -> UpstoxMetrics:
        return self._metrics

    def load_instruments(self, source: str | None = None) -> None:
        """Download and cache instrument master (complete.json.gz)."""
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
        """Subscribe to live depth ticks (up to depth 30)."""
        mode = "full_d30" if depth_type == "DEPTH_30" else "full"
        self._streaming.mode = mode
        self._streaming.on_depth = on_depth
        self._streaming.subscribe(symbol, exchange)
        if not self._streaming.is_connected:
            self._streaming.start()

        return StreamHandle(self._streaming, symbol, exchange)

    def close(self) -> None:
        if self._scheduler is not None:
            self._scheduler.stop()
        self._portfolio_stream.stop()
        self._streaming.stop()
        self._client.close()
