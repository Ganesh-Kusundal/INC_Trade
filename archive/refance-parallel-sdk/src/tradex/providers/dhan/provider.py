"""Dhan provider — main entry point for the Dhan broker integration."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from tradex.broker.auth import AuthManager
from tradex.broker.capability import BrokerCapability, CapabilityNames, CapabilityRegistry
from tradex.broker.extensions import ExtensionRegistry
from tradex.broker.provider import BrokerProvider
from tradex.broker.session import SessionManager, SessionStatus
from tradex.providers.dhan.config import DhanConfig
from tradex.core.events import EventBus
from tradex.core.health import HealthMonitor, HealthStatus
from tradex.core.logging_config import get_logger
from tradex.core.metrics import MetricsCollector
from tradex.core.rate_limiter import RateLimiter
from tradex.providers.dhan.auth import DhanAuthProvider
from tradex.providers.dhan.execution import DhanExecutionProvider
from tradex.providers.dhan.http_client import DhanHTTPClient
from tradex.providers.dhan.instruments import DhanInstrumentMapper
from tradex.providers.dhan.market import DhanMarketDataProvider
from tradex.providers.dhan.portfolio import DhanPortfolioProvider
from tradex.providers.dhan.streaming import DhanStreamingProvider

logger = get_logger("providers.dhan")


class DhanProvider(BrokerProvider):
    """Dhan broker provider — reference implementation.

    Composes Dhan-specific sub-providers behind the broker-agnostic SPI.
    All Dhan-specific logic is confined to this package.
    """

    def __init__(
        self,
        client_id: str = "",
        access_token: str = "",
        config: Optional[DhanConfig] = None,
    ) -> None:
        # Configuration — DhanConfig.__post_init__ validates credentials
        self._config = config or DhanConfig(
            client_id=client_id,
            access_token=access_token,
        )

        # Core infrastructure
        self._event_bus = EventBus()
        self._metrics = MetricsCollector()
        self._health = HealthMonitor()
        self._session = SessionManager(broker="dhan")
        self._auth_manager = AuthManager(auto_refresh=True)

        # Shared HTTP client — single connection for all API calls
        self._http_client = DhanHTTPClient(self._config, self._auth_manager)

        # Rate limiters per category
        self._rate_limiters = {
            cat: RateLimiter(cfg, cat) for cat, cfg in self._config.rate_limits.items()
        }

        # Instrument mapper
        self._mapper = DhanInstrumentMapper(cache_ttl=self._config.cache.security_master_ttl)

        # Sub-providers — all receive the shared HTTP client
        self._auth_provider = DhanAuthProvider(
            config=self._config,
            auth_manager=self._auth_manager,
            session=self._session,
            http_client=self._http_client,
        )
        self._execution_provider = DhanExecutionProvider(
            config=self._config,
            auth_manager=self._auth_manager,
            session=self._session,
            http_client=self._http_client,
            rate_limiter=self._rate_limiters.get("order"),
            mapper=self._mapper,
            event_bus=self._event_bus,
            metrics=self._metrics,
        )
        self._market_data_provider = DhanMarketDataProvider(
            config=self._config,
            auth_manager=self._auth_manager,
            http_client=self._http_client,
            rate_limiter=self._rate_limiters.get("quote"),
            data_rate_limiter=self._rate_limiters.get("data"),
            mapper=self._mapper,
            metrics=self._metrics,
        )
        self._portfolio_provider = DhanPortfolioProvider(
            config=self._config,
            auth_manager=self._auth_manager,
            http_client=self._http_client,
            rate_limiter=self._rate_limiters.get("non_trading"),
            mapper=self._mapper,
            metrics=self._metrics,
        )
        self._streaming_provider = DhanStreamingProvider(
            config=self._config,
            auth_manager=self._auth_manager,
            event_bus=self._event_bus,
        )

        # Capabilities
        self._capabilities = CapabilityRegistry()
        self._register_capabilities()

        # Extensions
        self._extensions = ExtensionRegistry(self._capabilities)

        # Background task tracking
        self._bg_tasks: list[asyncio.Task] = []

    def _register_capabilities(self) -> None:
        """Register Dhan-specific capabilities."""
        caps = [
            BrokerCapability(
                name=CapabilityNames.SUPER_ORDERS,
                description="Bracket orders with target and stop-loss",
                parameters={"legs": ["ENTRY_LEG", "TARGET_LEG", "STOP_LOSS_LEG"]},
            ),
            BrokerCapability(
                name=CapabilityNames.FOREVER_ORDERS,
                description="Good-til-cancelled trigger orders",
                parameters={"order_flags": ["SINGLE", "OCO"]},
            ),
            BrokerCapability(
                name=CapabilityNames.DEPTH_20,
                description="20-level market depth",
                parameters={"max_levels": 20},
            ),
            BrokerCapability(
                name=CapabilityNames.DEPTH_200,
                description="200-level market depth",
                parameters={
                    "max_levels": 200,
                    "instruments_per_connection": 1,
                    "exchanges": ["NSE_EQ", "NSE_FNO"],
                },
            ),
            BrokerCapability(
                name=CapabilityNames.SLICE_ORDERS,
                description="Automatic order slicing for large orders",
            ),
            BrokerCapability(
                name=CapabilityNames.EDIS,
                description="e-Delivery Instruction Slip for selling delivery holdings",
            ),
            BrokerCapability(
                name=CapabilityNames.KILL_SWITCH,
                description="Emergency position unwind",
            ),
            BrokerCapability(
                name=CapabilityNames.MARGIN_CALCULATOR,
                description="Pre-trade margin calculation",
            ),
            BrokerCapability(
                name=CapabilityNames.TRADE_HISTORY,
                description="Historical trade book",
            ),
            BrokerCapability(
                name=CapabilityNames.LEDGER_REPORT,
                description="Ledger report for a date range",
            ),
            BrokerCapability(
                name=CapabilityNames.POSITION_CONVERSION,
                description="Convert position between product types",
            ),
            BrokerCapability(
                name=CapabilityNames.AFTER_MARKET_ORDER,
                description="After market order support",
            ),
        ]
        self._capabilities.register_many(caps)

    @property
    def name(self) -> str:
        return "dhan"

    async def connect(self) -> None:
        """Connect to Dhan and authenticate."""
        await self._session.transition(SessionStatus.CONNECTING)
        try:
            await self._auth_provider.connect()
            await self._session.transition(SessionStatus.CONNECTED)

            # Load security master in background
            task = asyncio.create_task(self._mapper.load_from_provider())
            self._bg_tasks.append(task)
            task.add_done_callback(self._on_bg_task_done)

            logger.info("dhan_connected", client_id=self._config.client_id)
        except Exception as e:
            await self._session.transition(SessionStatus.ERROR, str(e))
            raise

    def _on_bg_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("background_task_failed", error=str(exc))

    async def disconnect(self) -> None:
        """Disconnect from Dhan."""
        await self._session.transition(SessionStatus.CLOSING)
        try:
            for t in self._bg_tasks:
                if not t.done():
                    t.cancel()
            await self._streaming_provider.disconnect()
            await self._auth_provider.disconnect()
            await self._http_client.close()
            await self._session.transition(SessionStatus.DISCONNECTED)
            logger.info("dhan_disconnected")
        except Exception as e:
            logger.error("dhan_disconnect_error", error=str(e))

    async def health(self) -> Any:
        """Get health status."""
        from tradex.core.health import ComponentHealth, HealthReport

        report = HealthReport()

        # Auth health
        auth_healthy = self._auth_manager.is_authenticated
        report.add_component(
            ComponentHealth(
                name="auth",
                status=HealthStatus.HEALTHY if auth_healthy else HealthStatus.UNHEALTHY,
                message="Authenticated" if auth_healthy else "Not authenticated",
            )
        )

        # Session health
        session_healthy = self._session.is_connected
        report.add_component(
            ComponentHealth(
                name="session",
                status=HealthStatus.HEALTHY if session_healthy else HealthStatus.UNHEALTHY,
                message=f"Status: {self._session.status.value}",
            )
        )

        # Mapper health
        mapper_healthy = self._mapper.is_loaded
        report.add_component(
            ComponentHealth(
                name="mapper",
                status=HealthStatus.HEALTHY if mapper_healthy else HealthStatus.DEGRADED,
                message=f"Loaded: {self._mapper.count} instruments",
            )
        )

        return report

    @property
    def auth(self) -> DhanAuthProvider:
        return self._auth_provider

    @property
    def execution(self) -> DhanExecutionProvider:
        return self._execution_provider

    @property
    def market_data(self) -> DhanMarketDataProvider:
        return self._market_data_provider

    @property
    def portfolio(self) -> DhanPortfolioProvider:
        return self._portfolio_provider

    @property
    def streaming(self) -> DhanStreamingProvider:
        return self._streaming_provider

    @property
    def mapper(self) -> DhanInstrumentMapper:
        return self._mapper

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def metrics(self) -> MetricsCollector:
        return self._metrics

    @property
    def capabilities(self) -> CapabilityRegistry:
        return self._capabilities

    @property
    def extensions(self) -> ExtensionRegistry:
        return self._extensions

    async def get_capabilities(self) -> list[str]:
        return self._capabilities.names
