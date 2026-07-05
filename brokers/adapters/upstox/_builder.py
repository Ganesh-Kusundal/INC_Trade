"""Upstox gateway builder — extracts subcomponent wiring from UpstoxGateway.

Mirrors the ``DhanGatewayBuilder`` pattern. The UpstoxGateway
constructor delegates its complex wiring to this builder, keeping
the gateway itself focused on its public BrokerGateway protocol surface.

Architecture rules:
- Imports only from ``brokers.domain``, ``brokers.ports``,
  ``brokers.adapters.upstox.*``, and stdlib.
- No service-layer imports.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from brokers.adapters.upstox.auth.config import (
    UpstoxConnectionSettings,
    UpstoxSettingsLoader,
)
from brokers.adapters.upstox.feed_authorizer import UpstoxFeedAuthorizer
from brokers.adapters.upstox.http_client import create_upstox_http_client
from brokers.adapters.upstox.urls import resolve_upstox_urls

if TYPE_CHECKING:
    from brokers.adapters.upstox.gateway import UpstoxGateway

logger = logging.getLogger(__name__)


class UpstoxGatewayBuilder:
    """Builder that constructs and wires Upstox subcomponents onto a gateway.

    Keeps ``UpstoxGateway.__init__`` short (delegates to ``build()``)
    while preserving 100% backward compatibility — every parameter
    ``UpstoxGateway.__init__`` accepts is also accepted by ``build()``.
    """

    def __init__(self, gateway: UpstoxGateway) -> None:
        self.gateway = gateway

    def _resolve_settings(
        self,
        access_token: str | None,
        settings: UpstoxConnectionSettings | None,
        allow_live_orders: bool | None,
    ) -> UpstoxConnectionSettings:
        """Load settings from env, defaults, or explicit argument.

        Order of precedence (matches the pre-refactor behavior):
        1. If ``settings`` is None, load from env. If env loading raises
           ``ValueError``, build a default settings with the access_token.
        2. **Always** apply ``access_token`` override if explicitly passed.
           This is done unconditionally so it works whether ``settings``
           came from env, default, or the explicit argument.
        """
        if settings is None:
            try:
                settings = UpstoxSettingsLoader.from_env()
            except ValueError:
                settings = UpstoxConnectionSettings(
                    client_id="default",
                    access_token=access_token or "",
                    allow_live_orders=(
                        allow_live_orders if allow_live_orders is not None else False
                    ),
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

    def _build_http(self) -> Any:
        """Create the Upstox HTTP client with a 401-retry refresh callback."""
        gateway = self.gateway
        auth = gateway._auth
        settings = gateway._settings

        def _refresh_and_get() -> str | None:
            if auth.try_refresh_on_401():
                token = auth.get_token()
                if token:
                    auth.force_refresh_callbacks(token)
                return token
            return None

        return create_upstox_http_client(
            access_token=auth.get_token(),
            token_refresh_fn=_refresh_and_get,
            base_url_v2=settings.base_v2,
            base_url_hft=settings.base_hft,
        )

    def _build_token_callbacks(self) -> None:
        """Register the streaming components as token-refresh consumers."""
        gateway = self.gateway
        gateway._auth.on_token_change(gateway._streaming.update_access_token)
        gateway._auth.on_token_change(gateway._portfolio_stream.update_access_token)
        gateway._auth.on_token_change(gateway._client.update_token)

    def _build_scheduler(
        self,
        auto_refresh: bool,
        settings: UpstoxConnectionSettings,
        lifecycle: Any | None,
    ) -> None:
        """Optionally start a TOTP refresh scheduler for live trading."""
        if not (auto_refresh and settings.is_totp and settings.has_totp_config):
            return
        from brokers.adapters.upstox.auth.totp_scheduler import TotpRefreshScheduler

        self.gateway._scheduler = TotpRefreshScheduler(
            token_manager=self.gateway._auth.manager,
            refresh_hour=settings.totp_refresh_hour,
            refresh_minute=settings.totp_refresh_minute,
        )
        if lifecycle is not None:
            lifecycle.register(self.gateway._scheduler)
        else:
            self.gateway._scheduler.start()

    def build(
        self,
        access_token: str | None = None,
        settings: UpstoxConnectionSettings | None = None,
        allow_live_orders: bool | None = None,
        auto_refresh: bool = True,
        lifecycle: Any | None = None,
        load_instruments: bool = False,
    ) -> None:
        """Build and wire all Upstox subcomponents onto ``self.gateway``.

        Args:
            access_token: Pre-configured access token.
            settings: Optional pre-built settings.
            allow_live_orders: Override allow_live_orders flag.
            auto_refresh: Enable TOTP refresh scheduler.
            lifecycle: Optional lifecycle manager.
            load_instruments: Whether to load instrument master immediately.
        """
        # Local imports inside build() to keep top-of-module dependencies clean.
        # Use ``sys.modules`` indirection so that ``patch(
        # "brokers.adapters.upstox.gateway.UpstoxStreaming")`` from tests
        # actually intercepts the construction call. The previous
        # direct import let the patch bypass our construction.
        import sys

        from brokers.adapters.upstox.auth import UpstoxAuth
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

        # Resolve UpstoxStreaming via the gateway's module so that
        # ``patch("brokers.adapters.upstox.gateway.UpstoxStreaming")``
        # (used in tests) actually intercepts this constructor call.
        UpstoxStreaming = sys.modules["brokers.adapters.upstox.gateway"].UpstoxStreaming

        gw = self.gateway
        gw._settings = self._resolve_settings(access_token, settings, allow_live_orders)
        gw._urls = resolve_upstox_urls(gw._settings.environment)
        gw._metrics = UpstoxMetrics()
        gw._auth = UpstoxAuth(settings=gw._settings)
        gw._auth.acquire()
        gw._client = self._build_http()
        gw._feed_authorizer = UpstoxFeedAuthorizer(
            gw._client,
            environment=gw._settings.environment,
        )

        gw._portfolio = UpstoxPortfolio(gw._client, gw._urls)
        gw._instruments = UpstoxInstruments(
            cache_path=gw._settings.instrument_cache_path
        )
        gw._historical = UpstoxHistorical(
            gw._client,
            urls=gw._urls,
            instruments=gw._instruments,
        )
        gw._news = UpstoxNews(gw._client, gw._urls)
        gw._options = UpstoxOptions(
            gw._client,
            gw._instruments,
            environment=gw._settings.environment,
        )
        gw._extended = UpstoxExtended(
            gw._client,
            environment=gw._settings.environment,
        )
        gw._gtt = UpstoxGtt(
            gw._client,
            environment=gw._settings.environment,
        )

        if load_instruments:
            gw.load_instruments()

        gw._market_data = UpstoxMarketData(
            gw._client,
            gw._urls,
            gw._instruments,
        )
        gw._orders = UpstoxOrders(
            gw._client,
            gw._urls,
            analytics_only=gw._settings.analytics_only,
            instruments=gw._instruments,
        )
        gw._streaming = UpstoxStreaming(
            access_token=gw._auth.get_token,
            feed_authorizer=gw._feed_authorizer,
            instruments=gw._instruments,
        )
        gw._portfolio_stream = UpstoxPortfolioStream(
            feed_authorizer=gw._feed_authorizer,
            token_provider=gw._auth.get_token,
        )

        self._build_token_callbacks()
        # Ensure _scheduler is always defined so close() is safe even when
        # TOTP refresh is not configured.
        gw._scheduler = None
        self._build_scheduler(auto_refresh, gw._settings, lifecycle)
