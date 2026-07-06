"""Upstox sub-adapter composition — shared wiring for gateway and V3 adapter."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

from brokers_core.adapters.upstox.auth import UpstoxAuth
from brokers_core.adapters.upstox.auth.config import (
    UpstoxConnectionSettings,
    UpstoxSettingsLoader,
)
from brokers_core.adapters.upstox.extended import UpstoxExtended
from brokers_core.adapters.upstox.feed_authorizer import UpstoxFeedAuthorizer
from brokers_core.adapters.upstox.gtt import UpstoxGtt
from brokers_core.adapters.upstox.historical import UpstoxHistorical
from brokers_core.adapters.upstox.http_client import create_upstox_http_client
from brokers_core.adapters.upstox.instruments import UpstoxInstruments
from brokers_core.adapters.upstox.market_data import UpstoxMarketData
from brokers_core.adapters.upstox.metrics import UpstoxMetrics
from brokers_core.adapters.upstox.news import UpstoxNews
from brokers_core.adapters.upstox.options import UpstoxOptions
from brokers_core.adapters.upstox.orders import UpstoxOrders
from brokers_core.adapters.upstox.portfolio import UpstoxPortfolio
from brokers_core.adapters.upstox.portfolio_stream import UpstoxPortfolioStream
from brokers_core.adapters.upstox.streaming import UpstoxStreaming
from brokers_core.adapters.upstox.urls import resolve_upstox_urls
from brokers_core.config.endpoints import _UpstoxUrls

logger = logging.getLogger(__name__)


@dataclass
class UpstoxComponents:
    """Wired Upstox sub-adapters and shared infrastructure."""

    settings: UpstoxConnectionSettings
    urls: _UpstoxUrls
    metrics: UpstoxMetrics
    auth: UpstoxAuth
    client: Any
    feed_authorizer: UpstoxFeedAuthorizer
    portfolio: UpstoxPortfolio
    instruments: UpstoxInstruments
    historical: UpstoxHistorical
    news: UpstoxNews
    options: UpstoxOptions
    extended: UpstoxExtended
    gtt: UpstoxGtt
    market_data: UpstoxMarketData
    orders: UpstoxOrders
    streaming: UpstoxStreaming
    portfolio_stream: UpstoxPortfolioStream
    scheduler: Any | None = None


def resolve_upstox_settings(
    access_token: str | None = None,
    settings: UpstoxConnectionSettings | None = None,
    allow_live_orders: bool | None = None,
) -> UpstoxConnectionSettings:
    """Load settings from env, defaults, or explicit argument."""
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
        return replace(
            settings,
            access_token=access_token,
            auth_mode="STATIC",
            token_state_file=None,
            analytics_only=False,
            allow_live_orders=(allow_live_orders if allow_live_orders is not None else True),
        )
    return settings


def build_upstox_components(
    access_token: str | None = None,
    settings: UpstoxConnectionSettings | None = None,
    allow_live_orders: bool | None = None,
    auto_refresh: bool = True,
    lifecycle: Any | None = None,
    load_instruments: bool = False,
) -> UpstoxComponents:
    """Build and wire all Upstox sub-adapters."""
    resolved = resolve_upstox_settings(access_token, settings, allow_live_orders)
    urls = resolve_upstox_urls(resolved.environment)
    metrics = UpstoxMetrics()
    auth = UpstoxAuth(settings=resolved)
    auth.acquire()

    def _refresh_and_get() -> str | None:
        if auth.try_refresh_on_401():
            token = auth.get_token()
            if token:
                auth.force_refresh_callbacks(token)
            return token
        return None

    client = create_upstox_http_client(
        access_token=auth.get_token(),
        token_refresh_fn=_refresh_and_get,
        base_url_v2=resolved.base_v2,
        base_url_hft=resolved.base_hft,
    )

    feed_authorizer = UpstoxFeedAuthorizer(client, environment=resolved.environment)
    portfolio = UpstoxPortfolio(client, urls)
    instruments = UpstoxInstruments(cache_path=resolved.instrument_cache_path)
    historical = UpstoxHistorical(client, urls=urls, instruments=instruments)
    news = UpstoxNews(client, urls)
    options = UpstoxOptions(client, instruments, environment=resolved.environment)
    extended = UpstoxExtended(client, environment=resolved.environment)
    gtt = UpstoxGtt(client, environment=resolved.environment)

    if load_instruments:
        instruments.load()

    market_data = UpstoxMarketData(client, urls, instruments)
    orders = UpstoxOrders(
        client,
        urls,
        analytics_only=resolved.analytics_only,
        instruments=instruments,
    )
    streaming = UpstoxStreaming(
        access_token=auth.get_token,
        feed_authorizer=feed_authorizer,
        instruments=instruments,
    )
    portfolio_stream = UpstoxPortfolioStream(
        feed_authorizer=feed_authorizer,
        token_provider=auth.get_token,
    )

    auth.on_token_change(streaming.update_access_token)
    auth.on_token_change(portfolio_stream.update_access_token)
    auth.on_token_change(client.update_token)

    scheduler = None
    if auto_refresh and resolved.is_totp and resolved.has_totp_config:
        from brokers_core.adapters.upstox.auth.totp_scheduler import TotpRefreshScheduler

        scheduler = TotpRefreshScheduler(
            token_manager=auth.manager,
            refresh_hour=resolved.totp_refresh_hour,
            refresh_minute=resolved.totp_refresh_minute,
        )
        if lifecycle is not None:
            lifecycle.register(scheduler)
        else:
            scheduler.start()

    return UpstoxComponents(
        settings=resolved,
        urls=urls,
        metrics=metrics,
        auth=auth,
        client=client,
        feed_authorizer=feed_authorizer,
        portfolio=portfolio,
        instruments=instruments,
        historical=historical,
        news=news,
        options=options,
        extended=extended,
        gtt=gtt,
        market_data=market_data,
        orders=orders,
        streaming=streaming,
        portfolio_stream=portfolio_stream,
        scheduler=scheduler,
    )


def apply_components_to_gateway(gateway: Any, components: UpstoxComponents) -> None:
    """Attach composed sub-adapters onto an UpstoxGateway instance."""
    gateway._settings = components.settings
    gateway._urls = components.urls
    gateway._metrics = components.metrics
    gateway._auth = components.auth
    gateway._client = components.client
    gateway._feed_authorizer = components.feed_authorizer
    gateway._portfolio = components.portfolio
    gateway._instruments = components.instruments
    gateway._historical = components.historical
    gateway._news = components.news
    gateway._options = components.options
    gateway._extended = components.extended
    gateway._gtt = components.gtt
    gateway._market_data = components.market_data
    gateway._orders = components.orders
    gateway._streaming = components.streaming
    gateway._portfolio_stream = components.portfolio_stream
    gateway._scheduler = components.scheduler


def teardown_upstox_components(components: UpstoxComponents) -> None:
    """Release resources held by composed sub-adapters."""
    if components.scheduler is not None:
        try:
            components.scheduler.stop()
        except Exception:
            logger.warning("Failed to stop Upstox TOTP scheduler", exc_info=True)
    try:
        components.portfolio_stream.stop()
    except Exception:
        logger.warning("Failed to stop Upstox portfolio stream", exc_info=True)
    try:
        components.streaming.stop()
    except Exception:
        logger.warning("Failed to stop Upstox streaming", exc_info=True)
    try:
        components.client.close()
    except Exception:
        logger.warning("Failed to close Upstox HTTP client", exc_info=True)
