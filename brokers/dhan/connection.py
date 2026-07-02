"""DhanConnection — wires all adapters with shared HTTP client + resolver."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from brokers.common.resilience.circuit_breaker import CircuitState
from brokers.dhan.alerts import AlertsAdapter
from brokers.dhan.conditional_triggers import ConditionalTriggersAdapter
from brokers.dhan.connection_lifecycle import ConnectionLifecycle
from brokers.dhan.connection_token_manager import ConnectionTokenManager
from brokers.dhan.depth_20 import DhanDepth20Feed
from brokers.dhan.depth_200 import DhanDepth200Feed, Depth200ConnectionPool
from brokers.dhan.edis import EDISAdapter
from brokers.dhan.exit_all import ExitAllAdapter
from brokers.dhan.forever_orders import ForeverOrdersAdapter
from brokers.dhan.futures import FuturesAdapter
from brokers.dhan.historical import HistoricalAdapter
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider
from brokers.dhan.ip_management import IPManagementAdapter
from brokers.dhan.ledger import LedgerAdapter
from brokers.dhan.loader import InstrumentLoader
from brokers.dhan.margin import MarginAdapter
from brokers.dhan.market_data import MarketDataAdapter
from brokers.dhan.options import OptionsAdapter
from brokers.dhan.orders import OrdersAdapter
from brokers.dhan.portfolio import PortfolioAdapter
from brokers.dhan.resolver import SymbolResolver
from brokers.dhan.session_manager import DhanSessionManager
from brokers.dhan.super_orders import SuperOrdersAdapter
from brokers.dhan.user_profile import UserProfileAdapter
from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream, PollingMarketFeed
from domain.ports.risk_manager import RiskManagerPort
from infrastructure.event_bus import EventBus
from infrastructure.lifecycle import LifecycleManager

logger = logging.getLogger(__name__)

# ── Adapter registry: (attr_name, adapter_class) ──
# Each entry constructs an adapter from (client, instruments).
# Entries are split by whether the adapter's constructor takes the
# instrument resolver as a second positional arg.
_ADAPTERS_WITH_INSTRUMENTS: list[tuple[str, type]] = [
    ("_market_data", MarketDataAdapter),
    ("_historical", HistoricalAdapter),
    ("_portfolio", PortfolioAdapter),
    ("_options", OptionsAdapter),
    ("_futures", FuturesAdapter),
    ("_margin", MarginAdapter),
    ("_alerts", AlertsAdapter),
    ("_super_orders", SuperOrdersAdapter),
    ("_forever_orders", ForeverOrdersAdapter),
    ("_conditional_triggers", ConditionalTriggersAdapter),
]

_ADAPTERS_CLIENT_ONLY: list[tuple[str, type]] = [
    ("_ledger", LedgerAdapter),
    ("_user_profile", UserProfileAdapter),
    ("_ip_management", IPManagementAdapter),
    ("_edis", EDISAdapter),
    ("_exit_all", ExitAllAdapter),
]


class DhanConnection:
    """Concrete connection wiring all Dhan adapters.

    Lifecycle ownership (Phase B / B5)
    ---------------------------------
    A :class:`LifecycleManager` may be supplied. When present, every
    ``ManagedService`` produced by this connection (``DhanMarketFeed``,
    ``DhanOrderStream``, ``PollingMarketFeed``) is registered with it
    so the connection's ``close()`` can drain every background thread.

    Previously, the WebSocket services were created lazily and ran as
    bare daemon threads; ``close()`` only called ``disconnect()`` and
    even ``disconnect()`` did not always join — the threads were
    leaked until process exit.
    """

    def __init__(
        self,
        client: DhanHttpClient,
        resolver: SymbolResolver | None = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManagerPort | None = None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
        reconciliation_service: object | None = None,
        lifecycle: LifecycleManager | None = None,
        allow_live_orders: bool = False,
    ):
        self._client = client
        self.instruments = resolver or SymbolResolver()
        # PR-A: single source of truth for symbol→security_id resolution.
        # All adapters that build Dhan HTTP payloads MUST go through
        # this provider rather than calling self.instruments.resolve(...)
        # directly.
        self.identity = DhanIdentityProvider(self.instruments)
        self._event_bus = event_bus
        # B5: if a lifecycle is provided, lazily-created WebSocket
        # services will be registered with it. close() then drains
        # every thread within bounded timeouts.
        self._lifecycle = lifecycle

        # ── Registry-driven adapter construction ──
        for attr_name, adapter_cls in _ADAPTERS_WITH_INSTRUMENTS:
            setattr(self, attr_name, adapter_cls(client, self.identity))
        for attr_name, adapter_cls in _ADAPTERS_CLIENT_ONLY:
            setattr(self, attr_name, adapter_cls(client))

        # Special case: OrdersAdapter takes extra kwargs
        self._orders = OrdersAdapter(
            client,
            self.identity,
            event_bus=event_bus,
            risk_manager=risk_manager,
            allow_live_orders=allow_live_orders,
        )
        self._token_manager = ConnectionTokenManager()
        self._lifecycle_helper = ConnectionLifecycle(
            client,
            self.instruments,
            register_token_receiver=self._token_manager.register_receiver,
            connection_owner=self,
            event_bus=event_bus,
            lifecycle=lifecycle,
            backfill_callback=backfill_callback,
        )
        self._backfill_callback = backfill_callback
        self._reconciliation_service = reconciliation_service
        from brokers.dhan.subscription_engine import SubscriptionEngine

        self.subscription_engine = SubscriptionEngine(self)
        self._session_manager: DhanSessionManager | None = None

    @property
    def market_data(self) -> MarketDataAdapter:
        return self._market_data

    @property
    def historical(self) -> HistoricalAdapter:
        return self._historical

    @property
    def orders(self) -> OrdersAdapter:
        return self._orders

    @property
    def portfolio(self) -> PortfolioAdapter:
        return self._portfolio

    @property
    def options(self) -> OptionsAdapter:
        return self._options

    @property
    def futures(self) -> FuturesAdapter:
        return self._futures

    @property
    def margin(self) -> MarginAdapter:
        return self._margin

    @property
    def event_bus(self) -> EventBus | None:
        return self._event_bus

    @property
    def alerts(self) -> AlertsAdapter:
        return self._alerts

    @property
    def super_orders(self) -> SuperOrdersAdapter:
        return self._super_orders

    @property
    def forever_orders(self) -> ForeverOrdersAdapter:
        return self._forever_orders

    @property
    def conditional_triggers(self) -> ConditionalTriggersAdapter:
        return self._conditional_triggers

    @property
    def ledger(self) -> LedgerAdapter:
        return self._ledger

    @property
    def user_profile(self) -> UserProfileAdapter:
        return self._user_profile

    @property
    def ip_management(self) -> IPManagementAdapter:
        return self._ip_management

    @property
    def edis(self) -> EDISAdapter:
        return self._edis

    @property
    def exit_all(self) -> ExitAllAdapter:
        return self._exit_all

    @property
    def backfill_callback(self) -> Callable[[str, datetime, datetime], list[dict]] | None:
        """Backfill callback for market feed reconnect gap fill."""
        return self._backfill_callback

    @property
    def reconciliation_service(self) -> object | None:
        """Reconciliation service wired into the trading context."""
        return self._reconciliation_service

    # ── Public accessors (avoid private _client access from gateway) ──

    @property
    def access_token(self) -> str:
        """Current API access token (delegates to HTTP client)."""
        return self._client.access_token

    @property
    def client_id(self) -> str:
        """Broker client ID (delegates to HTTP client)."""
        return self._client.client_id

    @property
    def depth_20_feed(self) -> DhanDepth20Feed | None:
        """Active 20-level depth feed, if created."""
        return self._lifecycle_helper.depth_20_feed

    @depth_20_feed.setter
    def depth_20_feed(self, value: DhanDepth20Feed) -> None:
        self._lifecycle_helper.depth_20_feed = value

    @property
    def depth_200_feed(self) -> DhanDepth200Feed | None:
        """Active 200-level depth feed, if created."""
        return self._lifecycle_helper.depth_200_feed

    @depth_200_feed.setter
    def depth_200_feed(self, value: DhanDepth200Feed) -> None:
        self._lifecycle_helper.depth_200_feed = value

    @property
    def depth_200_pool(self) -> Any:
        """Active depth-200 connection pool for managing multiple instrument connections."""
        return self._lifecycle_helper.depth_200_pool

    @property
    def market_feed(self) -> DhanMarketFeed | None:
        """Real-time market data feed (lazy — None until explicitly created)."""
        return self._lifecycle_helper.market_feed

    @market_feed.setter
    def market_feed(self, value: DhanMarketFeed) -> None:
        self._lifecycle_helper.market_feed = value

    @property
    def order_stream(self) -> DhanOrderStream | None:
        """Real-time order update stream (lazy — None until explicitly created)."""
        return self._lifecycle_helper.order_stream

    @order_stream.setter
    def order_stream(self, value: DhanOrderStream) -> None:
        self._lifecycle_helper.order_stream = value

    @property
    def polling_feed(self) -> PollingMarketFeed | None:
        """Real-time polling market feed."""
        return self._lifecycle_helper.polling_feed

    @polling_feed.setter
    def polling_feed(self, value: PollingMarketFeed) -> None:
        self._lifecycle_helper.polling_feed = value

    @property
    def client(self) -> DhanHttpClient:
        """Public accessor for the underlying HTTP client.

        Callers that need to make raw API calls (e.g. extended capabilities)
        should use this property instead of accessing ``_client`` directly.
        """
        return self._client

    @property
    def token_scheduler(self) -> object | None:
        """Active token-refresh scheduler, if one has been installed."""
        return getattr(self, "_token_scheduler", None)

    @property
    def session_manager(self) -> DhanSessionManager | None:
        """Consolidated auth + connection + subscription session view."""
        return getattr(self, "_session_manager", None)

    @token_scheduler.setter
    def token_scheduler(self, value: object) -> None:
        """Install a token-refresh scheduler on this connection."""
        self._token_scheduler = value

    @property
    def circuit_breaker_states(self) -> dict[str, int]:
        """Return circuit breaker states for observability.

        Maps each breaker category to an int:
        0 = CLOSED, 1 = OPEN, 2 = HALF_OPEN.
        """
        state_map = {
            CircuitState.CLOSED: 0,
            CircuitState.OPEN: 1,
            CircuitState.HALF_OPEN: 2,
        }
        states: dict[str, int] = {}
        for attr, short_name in [
            ("_read_circuit_breaker", "read_cb"),
            ("_write_circuit_breaker", "write_cb"),
            ("_admin_circuit_breaker", "admin_cb"),
        ]:
            cb = getattr(self._client, attr, None)
            if cb is not None:
                try:
                    states[short_name] = state_map.get(cb.state, 0)
                except Exception:
                    states[short_name] = 0
        return states

    @property
    def token_refresh_metrics(self) -> dict[str, int]:
        """Return token refresh metrics for observability."""
        scheduler = getattr(self, "_token_scheduler", None)
        if scheduler is None:
            return {"refresh_count": 0, "error_count": 0}
        try:
            return {
                "refresh_count": getattr(scheduler, "refresh_count", 0),
                "error_count": 1 if getattr(scheduler, "_last_error", None) else 0,
            }
        except Exception:
            return {"refresh_count": 0, "error_count": 0}

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        """Load instruments into memory resolver.

        PR-C: the *skipped* count returned by
        :meth:`brokers.dhan.resolver.SymbolResolver.load_from_rows` is
        logged at WARNING level when it exceeds 1% of the total row
        count. This closes the silent-failure hotspot where a partially
        broken CSV would leave the resolver incomplete without any
        operator-visible signal.
        """
        import time

        start = time.monotonic()
        if source is not None:
            if source.startswith(("http://", "https://")):
                rows = InstrumentLoader.load_from_url(source)
            else:
                rows = InstrumentLoader.load_from_file(source)
        elif use_cache:
            rows = InstrumentLoader.load_cached()
        else:
            rows = InstrumentLoader.load_cached(force_refresh=True)
        load_time = time.monotonic() - start

        logger.info(
            "instrument_load_completed",
            extra={
                "count": len(rows),
                "load_time_s": round(load_time, 2),
                "source": source or "cached",
            },
        )

        start = time.monotonic()
        stats = self.instruments.load_from_rows(rows)
        memory_time = time.monotonic() - start

        skipped = int(stats.get("skipped", 0))
        total = int(stats.get("total", len(rows)))
        if total > 0 and skipped / total > 0.01:
            logger.warning(
                "instrument_load_skipped_high",
                extra={
                    "skipped": skipped,
                    "total": total,
                    "skip_rate": round(skipped / total, 4),
                    "threshold": 0.01,
                },
            )

        logger.info(
            "instrument_memory_load_completed",
            extra={"count": len(rows), "skipped": skipped, "memory_time_s": round(memory_time, 2)},
        )

    def create_market_feed(
        self,
        access_token: str | None = None,
        instruments: list[tuple] | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ) -> DhanMarketFeed:
        """Create and return a DhanMarketFeed wired with this connection's backfill callback."""
        return self._lifecycle_helper.create_market_feed(
            access_token=access_token,
            instruments=instruments,
            access_token_fn=access_token_fn,
        )

    def create_order_stream(
        self,
        access_token: str | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ) -> DhanOrderStream:
        """Create and return a DhanOrderStream."""
        return self._lifecycle_helper.create_order_stream(
            access_token=access_token,
            access_token_fn=access_token_fn,
        )

    def create_depth_20_feed(
        self,
        access_token: str | None = None,
        instrument: tuple[str, str] | None = None,
    ) -> DhanDepth20Feed:
        """Create and return a DhanDepth20Feed for 20-level depth."""
        return self._lifecycle_helper.create_depth_20_feed(
            access_token=access_token,
            instrument=instrument,
        )

    def create_depth_200_feed(
        self,
        access_token: str | None = None,
        instrument: tuple[str, str] | None = None,
    ) -> DhanDepth200Feed:
        """Create and return a DhanDepth200Feed for 200-level depth."""
        return self._lifecycle_helper.create_depth_200_feed(
            access_token=access_token,
            instrument=instrument,
        )

    def create_polling_feed(
        self,
        instruments: list[tuple],
        interval_seconds: float = 2.0,
    ) -> PollingMarketFeed:
        """Create and return a PollingMarketFeed."""
        return self._lifecycle_helper.create_polling_feed(
            instruments,
            interval_seconds=interval_seconds,
        )

    # ── Token-receiver registry (REF-13) ──────────────────────────────────

    def register_token_receiver(self, receiver: Callable[[str], None]) -> Callable[[str], None]:
        """Register a callable invoked whenever a new access token arrives."""
        return self._token_manager.register_receiver(receiver)

    def broadcast_token(self, new_token: str) -> int:
        """Push ``new_token`` to every registered receiver."""
        return self._token_manager.broadcast(new_token)

    def get_or_create_resolver_refresher(
        self,
        interval_seconds: int = 24 * 3600,
        on_success=None,
        on_error=None,
    ):
        """Return the singleton :class:`ResolverRefresher` for this connection."""
        return self._lifecycle_helper.get_or_create_resolver_refresher(
            interval_seconds=interval_seconds,
            on_success=on_success,
            on_error=on_error,
        )

    def register_resolver_refresher_with_lifecycle(
        self,
        interval_seconds: int = 24 * 3600,
    ):
        """Create the refresher and register it with the lifecycle manager."""
        return self._lifecycle_helper.register_resolver_refresher_with_lifecycle(
            interval_seconds=interval_seconds,
        )

    def close(self) -> None:
        """Close HTTP client, stop token scheduler, and disconnect WebSocket connections.

        B5: every ManagedService is stopped via ``stop(timeout_seconds)``
        which joins the thread. The previous ``disconnect()`` was not
        always called and never joined — the daemon threads leaked on
        process exit.
        """
        # Stop token refresh scheduler (ManagedService)
        scheduler = getattr(self, "_token_scheduler", None)
        if scheduler is not None:
            try:
                scheduler.stop()
            except Exception as exc:
                logger.warning("token_scheduler_stop_failed: %s", exc)
        # PR-C: stop the resolver refresher if one was created.
        self._lifecycle_helper.close(timeout_seconds=5.0)
        self._client.close()
