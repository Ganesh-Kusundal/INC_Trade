"""Dhan gateway — composes all Dhan adapters into BrokerGateway.

Wires up the complete token lifecycle: auth, HTTP client with 401 auto-retry,
streaming with lazy token access, background refresh scheduler, token broadcast,
and optional persistence.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any

from brokers.adapters.dhan.auth import DhanAuth
from brokers.adapters.dhan.capabilities import dhan_capabilities
from brokers.adapters.dhan.connection_manager import DhanConnectionManager
from brokers.adapters.dhan.depth20 import DhanDepth20Stream
from brokers.adapters.dhan.depth200 import DhanDepth200Stream
from brokers.adapters.dhan.extensions.forever_orders import DhanForeverOrders
from brokers.adapters.dhan.extensions.margin import DhanMargin
from brokers.adapters.dhan.extensions.super_orders import DhanSuperOrders
from brokers.adapters.dhan.health_reporter import DhanHealthReporter
from brokers.adapters.dhan.historical import DhanHistorical
from brokers.adapters.dhan.http_client import create_dhan_http_client
from brokers.adapters.dhan.identity import DhanInstrumentRef, DhanInstrumentResolver
from brokers.adapters.dhan.instruments import DhanInstruments
from brokers.adapters.dhan.market_data import DhanMarketData
from brokers.adapters.dhan.options import DhanOptions
from brokers.adapters.dhan.order_stream import DhanOrderStream
from brokers.adapters.dhan.orders import DhanOrders
from brokers.adapters.dhan.portfolio import DhanPortfolio
from brokers.adapters.dhan.streaming import DhanStreaming
from inc_trade.domain.capabilities import BrokerCapabilities
from inc_trade.domain.enums import BrokerID
from inc_trade.infrastructure.lifecycle import LifecycleManager
from inc_trade.infrastructure.token_broadcast import TokenManager
from inc_trade.ports.capabilities import (
    AlertsProvider,
    ExitAllProvider,
    ForeverOrderProvider,
    IPManagementProvider,
    MarginProvider,
    SliceOrderProvider,
    SuperOrderProvider,
)
from inc_trade.ports.event_publisher import EventPublisherPort
from inc_trade.ports.extension_registry import ExtensionRegistry, ExtensionRegistryPort
from inc_trade.ports.risk_manager import RiskManagerPort
from inc_trade.ports.streaming import StreamingPort
from inc_trade.ports.token_store import TokenStorePort

logger = logging.getLogger(__name__)


class DhanGateway:
    """Dhan broker adapter implementing BrokerGateway protocol.

    Manages the complete token lifecycle:
    - Auth with TOTP generation and state tracking
    - HTTP client with 401 auto-retry via token refresh
    - Streaming with lazy token access (reconnects use latest token)
    - Background refresh scheduler with rate-limit backoff
    - Token broadcast to notify all consumers of refreshes
    - Optional persistence to JSON store and .env file

    Args:
        access_token: Pre-configured access token (skips TOTP if provided).
        client_id: Dhan client ID.
        pin: PIN for TOTP login.
        totp_secret: Secret for TOTP login.
        allow_live_orders: Enable live order placement (kill switch).
        env_path: Path to .env file for token persistence.
        token_state_dir: Directory for JSON token state persistence.
        auto_refresh: Enable background token refresh scheduler.
        refresh_interval_seconds: How often to check token validity.
        refresh_buffer_seconds: Refresh if token expires within this window.
        lifecycle: Optional lifecycle manager to register scheduler with.
        token_store: Optional externally-provided token store. If omitted
            and ``token_state_dir`` is set, a ``JsonTokenStateStore`` is
            created automatically.
    """

    _broker_id: BrokerID = BrokerID.DHAN

    @property
    def broker_id(self) -> BrokerID:
        """Canonical broker identifier."""
        return self._broker_id

    def capabilities(self) -> Capabilities:
        """Return Dhan broker capability matrix."""
        return dhan_capabilities()

    def __init__(
        self,
        access_token: str | None = None,
        client_id: str | None = None,
        pin: str | None = None,
        totp_secret: str | None = None,
        allow_live_orders: bool = False,
        env_path: Path | None = None,
        token_state_dir: Path | None = None,
        auto_refresh: bool = True,
        refresh_interval_seconds: int = 60,
        refresh_buffer_seconds: float = 300.0,
        lifecycle: LifecycleManager | None = None,
        event_bus: EventPublisherPort | None = None,
        risk_manager: RiskManagerPort | None = None,
        token_store: TokenStorePort | None = None,
    ):
        builder = DhanGatewayBuilder(self)
        builder.build(
            access_token=access_token,
            client_id=client_id,
            pin=pin,
            totp_secret=totp_secret,
            allow_live_orders=allow_live_orders,
            env_path=env_path,
            token_state_dir=token_state_dir,
            auto_refresh=auto_refresh,
            refresh_interval_seconds=refresh_interval_seconds,
            refresh_buffer_seconds=refresh_buffer_seconds,
            lifecycle=lifecycle,
            event_bus=event_bus,
            risk_manager=risk_manager,
            token_store=token_store,
        )

    @property
    def token_manager(self) -> TokenManager:
        """Access the token manager for health monitoring."""
        return self._conn_mgr.token_manager

    @property
    def resolver(self) -> DhanInstrumentResolver:
        return self._resolver

    def _resolve_ref(
        self,
        symbol: str,
        exchange: str,
        *,
        expected_segment: str | None = None,
    ) -> DhanInstrumentRef:
        return self._resolver.resolve(symbol, exchange, expected_segment=expected_segment)

    # ── Sub-component property accessors ─────────────────────────────────

    @property
    def orders(self) -> DhanOrders:
        return self._orders

    @property
    def market_data(self) -> DhanMarketData:
        return self._market_data

    @property
    def portfolio(self) -> DhanPortfolio:
        return self._portfolio

    @property
    def instruments(self) -> DhanInstruments:
        return self._instruments

    @property
    def auth(self) -> DhanAuth:
        return self._auth

    @property
    def historical(self) -> DhanHistorical:
        return self._historical

    @property
    def margin(self) -> DhanMargin:
        return self._margin

    @property
    def forever_orders(self) -> DhanForeverOrders:
        return self._forever_orders

    @property
    def super_orders(self) -> DhanSuperOrders:
        return self._super_orders

    @property
    def options(self) -> DhanOptions:
        return self._options

    @property
    def streaming(self) -> StreamingPort:
        return self._streaming

    @property
    def extensions(self) -> ExtensionRegistryPort:
        """Registry of broker-specific extensions."""
        if not hasattr(self, "_extension_registry"):
            from inc_trade.ports.extension_registry import DictExtensionRegistry

            self._extension_registry = DictExtensionRegistry()
            # Register extensions
            self._extension_registry.register("dhan", MarginProvider, self._margin)
            self._extension_registry.register("dhan", SuperOrderProvider, self._super_orders)
            self._extension_registry.register("dhan", ForeverOrderProvider, self._forever_orders)
            self._extension_registry.register(
                "dhan",
                SliceOrderProvider,
                self._orders,  # DhanOrders implements slice orders
            )
            if hasattr(self, "_alerts") and self._alerts:
                self._extension_registry.register("dhan", AlertsProvider, self._alerts)
            if hasattr(self, "_exit_all") and self._exit_all:
                self._extension_registry.register("dhan", ExitAllProvider, self._exit_all)
            if hasattr(self, "_ip_management") and self._ip_management:
                self._extension_registry.register("dhan", IPManagementProvider, self._ip_management)
            if hasattr(self, "_transfer") and self._transfer:
                self._extension_registry.register(
                    "dhan", BrokerToBrokerTransferProvider, self._transfer
                )
        return self._extension_registry

    # ── Health & observability ─────────────────────────────────────────

    def health(self) -> dict:
        """Health status including token lifecycle metrics."""
        return self._health_reporter.health()

    # ── Lifecycle ──────────────────────────────────────────────────────

    def close(self) -> None:
        """Stop scheduler, streaming, and close HTTP client."""
        self._conn_mgr.close()

        pool = getattr(self, "_depth_200_pool", None)
        if pool is None:
            pool = getattr(self._depth200_stream, "_pool", None)
        if pool is not None:
            with contextlib.suppress(Exception):
                pool.close_all()

        for feed in (
            self._streaming,
            self._order_stream,
            self._depth20_stream,
            self._depth200_stream,
        ):
            self._stop_feed(feed)

        self._client.close()

    @staticmethod
    def _stop_feed(feed: Any) -> None:
        stop = getattr(feed, "stop", None)
        if stop is not None:
            with contextlib.suppress(Exception):
                stop()
        admission = getattr(feed, "_admission", None)
        if admission is not None:
            with contextlib.suppress(Exception):
                admission.release()


class DhanGatewayBuilder:
    """Builder class extracting complex subcomponent wiring from DhanGateway."""

    def __init__(self, gateway: DhanGateway) -> None:
        self.gateway = gateway

    def build(
        self,
        access_token: str | None = None,
        client_id: str | None = None,
        pin: str | None = None,
        totp_secret: str | None = None,
        allow_live_orders: bool = False,
        env_path: Path | None = None,
        token_state_dir: Path | None = None,
        auto_refresh: bool = True,
        refresh_interval_seconds: int = 60,
        refresh_buffer_seconds: float = 300.0,
        lifecycle: LifecycleManager | None = None,
        event_bus: EventPublisherPort | None = None,
        risk_manager: RiskManagerPort | None = None,
        token_store: TokenStorePort | None = None,
    ) -> None:
        gw = self.gateway
        gw._env_path = env_path
        gw._token_state_dir = token_state_dir
        gw._auto_refresh = auto_refresh

        # Create token store if directory provided (backward compat fallback)
        gw._token_store = token_store
        if gw._token_store is None and token_state_dir:
            token_state_dir.mkdir(parents=True, exist_ok=True)
            from inc_trade.infrastructure.storage.token_store import JsonTokenStateStore

            gw._token_store = JsonTokenStateStore(token_state_dir / "dhan-token-state.json")

        gw._auth = DhanAuth(
            access_token=access_token,
            client_id=client_id,
            pin=pin,
            totp_secret=totp_secret,
            token_store=gw._token_store,
        )

        # Connection manager — owns token lifecycle, broadcast, scheduler
        gw._conn_mgr = DhanConnectionManager(
            auth=gw._auth,
            client_id=client_id or "",
            pin=pin,
            totp_secret=totp_secret,
            token_store=gw._token_store,
            env_path=env_path,
            token_state_dir=token_state_dir,
            auto_refresh=auto_refresh,
            refresh_interval_seconds=refresh_interval_seconds,
            refresh_buffer_seconds=refresh_buffer_seconds,
            lifecycle=lifecycle,
        )

        token = gw._auth.get_token()

        gw._client = create_dhan_http_client(
            client_id=client_id or "",
            access_token=token,
            token_refresh_fn=gw._conn_mgr.refresh_token_for_http,
        )

        gw._resolver = DhanInstrumentResolver()
        gw._orders = DhanOrders(
            gw._client,
            gw._resolver,
            event_bus=event_bus,
            risk_manager=risk_manager,
        )
        gw._market_data = DhanMarketData(gw._client, gw._resolver)
        gw._portfolio = DhanPortfolio(gw._client)
        gw._instruments = DhanInstruments(gw._resolver)
        gw._historical = DhanHistorical(gw._client, gw._resolver)
        gw._options = DhanOptions(gw._client, gw._instruments)

        # Extensions
        gw._margin = DhanMargin(gw._client, gw._resolver)
        gw._forever_orders = DhanForeverOrders(gw._client, gw._resolver)
        gw._super_orders = DhanSuperOrders(gw._client, gw._resolver)

        gw._streaming = DhanStreaming(
            access_token=gw._auth.get_token,
            client_id=client_id or "",
            resolver=gw._resolver,
        )

        gw._order_stream = DhanOrderStream(
            access_token=gw._auth.get_token,
            client_id=client_id or "",
        )

        gw._depth20_stream = DhanDepth20Stream(
            access_token=gw._auth.get_token,
            client_id=client_id or "",
            resolver=gw._resolver,
        )

        gw._depth200_stream = DhanDepth200Stream(
            access_token=gw._auth.get_token,
            client_id=client_id or "",
            resolver=gw._resolver,
        )

        # Register token consumers on the connection manager
        for consumer in (
            gw._client.update_token,
            gw._streaming.update_token,
            gw._order_stream.update_token,
            gw._depth20_stream.update_token,
            gw._depth200_stream.update_token,
        ):
            gw._conn_mgr.register_consumer(consumer)

        # Persist initial token if configured
        gw._conn_mgr.persist_initial_token()

        # Health reporter — aggregated health, connection status, metrics
        gw._health_reporter = DhanHealthReporter(
            auth=gw._auth,
            connection_manager=gw._conn_mgr,
            http_client=gw._client,
            streaming=gw._streaming,
            order_stream=gw._order_stream,
            depth20_stream=gw._depth20_stream,
            depth200_stream=gw._depth200_stream,
        )
