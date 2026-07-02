"""Upstox broker facade — instantiates every adapter from the resolved
``UpstoxConnectionSettings`` + ``UpstoxTokenManager`` and exposes them
as direct attributes.

This is a plain class (no ABC base). The ``UpstoxBrokerGateway`` wrapper
implements the ``MarketDataGateway`` contract; this class provides the
adapter wiring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from brokers.common.services.historical_data import HistoricalDataService
from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.context import UpstoxAdapterContext
from brokers.upstox.auth.token_manager import UpstoxTokenManager
from brokers.upstox.capabilities import (
    InstrumentsCapability,
    MarketDataCapability,
    OrdersCapability,
    PortfolioCapability,
    StreamingCapability,
)
from brokers.upstox.instruments.loader import UpstoxInstrumentLoader
from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver
from brokers.upstox.instruments.search import UpstoxInstrumentSearch
from brokers.upstox.kill_switch.adapter import UpstoxKillSwitchAdapter
from brokers.upstox.kill_switch.client import UpstoxKillSwitchClient
from brokers.upstox.market_data.client_v2 import UpstoxMarketDataV2Client
from brokers.upstox.market_data.client_v3 import UpstoxMarketDataV3Client
from brokers.upstox.market_data.expired_options import UpstoxExpiredInstrumentsClient
from brokers.upstox.market_data.futures import UpstoxFuturesClient
from brokers.upstox.market_data.futures_adapter import UpstoxFuturesAdapter
from brokers.upstox.market_data.historical_v2 import UpstoxHistoricalV2Client
from brokers.upstox.market_data.historical_v3 import UpstoxHistoricalV3Client
from brokers.upstox.market_data.margin import UpstoxMarginClient
from brokers.upstox.market_data.margin_adapter import UpstoxMarginAdapter
from brokers.upstox.market_data.market_data_adapter import UpstoxMarketDataAdapter
from brokers.upstox.market_data.market_status import UpstoxMarketStatusClient
from brokers.upstox.market_data.market_status_adapter import UpstoxMarketStatusAdapter
from brokers.upstox.market_data.options_adapter import UpstoxOptionsAdapter
from brokers.upstox.market_data.options_client import UpstoxOptionsClient
from brokers.upstox.market_data.portfolio_adapter import UpstoxPortfolioAdapter
from brokers.upstox.market_data.portfolio_client import UpstoxPortfolioClient
from brokers.upstox.orders.alert_adapter import UpstoxAlertAdapter
from brokers.upstox.orders.cover_order_adapter import UpstoxCoverOrderAdapter
from brokers.upstox.orders.exit_all_adapter import UpstoxExitAllAdapter
from brokers.upstox.orders.gtt_adapter import UpstoxGttAdapter
from brokers.upstox.orders.gtt_client import UpstoxGttClient
from brokers.upstox.orders.idempotency import InMemoryIdempotencyCache
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from brokers.upstox.orders.order_command_adapter import UpstoxOrderCommandAdapter
from brokers.upstox.orders.order_query_adapter import UpstoxOrderQueryAdapter
from brokers.upstox.orders.slice_adapter import UpstoxSliceAdapter
from brokers.upstox.reconciliation.service import UpstoxReconciliationService
from brokers.upstox.websocket.feed_authorizer import UpstoxFeedAuthorizer
from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer
from brokers.upstox.websocket.portfolio_stream import UpstoxPortfolioStream
from brokers.upstox.websocket.v3_auto_reconnect import UpstoxAutoReconnect
from brokers.upstox.websocket.v3_decoder import UpstoxV3Decoder
from brokers.upstox.websocket.v3_subscription_manager import UpstoxV3SubscriptionLimits
from domain import Capability, ConnectionStatus
from domain.ports.risk_manager import RiskManagerPort
from infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _UpstoxCapabilities:
    market_data: MarketDataCapability
    orders: OrdersCapability
    portfolio: PortfolioCapability
    instruments: InstrumentsCapability
    streaming: StreamingCapability


# Core adapters required for orders, market data, and portfolio paths.
_CORE_ADAPTER_REGISTRY: list[tuple[str, type, type, Capability | None]] = [
    ("portfolio", UpstoxPortfolioClient, UpstoxPortfolioAdapter, Capability.PORTFOLIO),
    ("margin", UpstoxMarginClient, UpstoxMarginAdapter, Capability.MARGIN),
    ("options", UpstoxOptionsClient, UpstoxOptionsAdapter, Capability.OPTIONS_CHAIN),
    ("futures", UpstoxFuturesClient, UpstoxFuturesAdapter, Capability.FUTURES),
    (
        "market_status",
        UpstoxMarketStatusClient,
        UpstoxMarketStatusAdapter,
        Capability.MARKET_STATUS,
    ),
    ("kill_switch", UpstoxKillSwitchClient, UpstoxKillSwitchAdapter, Capability.KILL_SWITCH),
    ("gtt", UpstoxGttClient, UpstoxGttAdapter, Capability.GTT_ORDER),
]

# Extended adapters — loaded lazily via :meth:`_ensure_extended`.
_EXTENDED_ADAPTER_REGISTRY: list[tuple[str, str, str, str, str, Capability | None]] = [
    (
        "ipo",
        "brokers.upstox.ipo.client",
        "UpstoxIpoClient",
        "brokers.upstox.ipo.adapter",
        "UpstoxIpoAdapter",
        Capability.IPO,
    ),
    (
        "payments",
        "brokers.upstox.payments.client",
        "UpstoxPaymentsClient",
        "brokers.upstox.payments.adapter",
        "UpstoxPaymentsAdapter",
        Capability.PAYMENTS,
    ),
    (
        "mutual_funds",
        "brokers.upstox.mutual_funds.client",
        "UpstoxMutualFundsClient",
        "brokers.upstox.mutual_funds.adapter",
        "UpstoxMutualFundsAdapter",
        Capability.MUTUAL_FUNDS,
    ),
    (
        "fundamentals",
        "brokers.upstox.fundamentals.client",
        "UpstoxFundamentalsClient",
        "brokers.upstox.fundamentals.adapter",
        "UpstoxFundamentalsAdapter",
        Capability.FUNDAMENTALS,
    ),
    (
        "news",
        "brokers.upstox.news.client",
        "UpstoxNewsClient",
        "brokers.upstox.news.adapter",
        "UpstoxNewsAdapter",
        Capability.NEWS,
    ),
    (
        "intelligence",
        "brokers.upstox.market_intelligence.client",
        "UpstoxMarketIntelligenceClient",
        "brokers.upstox.market_intelligence.adapter",
        "UpstoxMarketIntelligenceAdapter",
        Capability.MARKET_INTELLIGENCE,
    ),
    (
        "static_ip",
        "brokers.upstox.static_ip.client",
        "UpstoxStaticIpClient",
        "brokers.upstox.static_ip.adapter",
        "UpstoxStaticIpAdapter",
        Capability.STATIC_IP,
    ),
]


class UpstoxBrokerBuilder:
    """Encapsulates the full construction of an :class:`UpstoxBroker`.

    Each named method corresponds to one construction phase, keeping the
    ``__init__`` body thin and making the wiring order explicit.
    """

    def __init__(
        self,
        broker: UpstoxBroker,
        settings: UpstoxConnectionSettings,
        token_manager: UpstoxTokenManager | None,
        oms: Any,
        event_bus: EventBus | None,
        risk_manager: RiskManagerPort | None,
        backfill_callback: Any | None,
        reconciliation_service: Any | None,
    ) -> None:
        self._broker = broker
        self._settings = settings
        self._token_manager = token_manager
        self._oms = oms
        self._event_bus = event_bus
        self._risk_manager = risk_manager
        self._backfill_callback = backfill_callback
        self._reconciliation_service = reconciliation_service

    def build(self) -> None:
        self._init_basic_state()
        self._init_http_clients()
        self._init_core_adapters()
        self._init_special_adapters()
        self._init_websocket_layer()
        self._init_services()
        self._init_capabilities()

    def _init_basic_state(self) -> None:
        settings = self._settings
        b = self._broker
        b._name = "upstox"
        b._broker_id = settings.client_id
        b._capabilities: set[Capability] = set()
        b._capability_map: dict[Capability, Any] = {}
        b._status = ConnectionStatus.DISCONNECTED
        b.settings = settings
        b._token_manager = self._token_manager or UpstoxTokenManager(settings=settings)
        b.context = UpstoxAdapterContext(
            settings=settings,
            token_provider=b._token_manager.bearer_token,
            token_manager=b._token_manager,
        )
        b._oms = self._oms
        b._event_bus = self._event_bus
        b._risk_manager = self._risk_manager
        b._backfill_callback = self._backfill_callback
        b._reconciliation_service = self._reconciliation_service
        b._extended_ready = False

    def _init_http_clients(self) -> None:
        b = self._broker
        b.instrument_resolver = UpstoxInstrumentResolver()
        b.instrument_loader = UpstoxInstrumentLoader()
        b.instrument_search = UpstoxInstrumentSearch(b.context.http_client)

    def _init_core_adapters(self) -> None:
        b = self._broker
        # Standalone clients (no corresponding adapter from registry)
        b.market_data_v2 = UpstoxMarketDataV2Client(
            b.context.http_client, b.context.url_resolver
        )
        b.market_data_v3 = UpstoxMarketDataV3Client(
            b.context.http_client, b.context.url_resolver
        )
        b.historical_v2 = UpstoxHistoricalV2Client(
            b.context.http_client, b.context.url_resolver
        )
        b.historical_v3 = UpstoxHistoricalV3Client(
            b.context.http_client, url_resolver=b.context.url_resolver
        )
        b.order_client = UpstoxRestOrderClient(
            b.context.http_client, b.context.url_resolver
        )
        b.expired_instruments_client = UpstoxExpiredInstrumentsClient(
            b.context.http_client, b.context.url_resolver
        )

        # Core registry-driven client + adapter pairs
        for name, client_cls, adapter_cls, capability in _CORE_ADAPTER_REGISTRY:
            client = client_cls(b.context.http_client, b.context.url_resolver)
            setattr(b, f"{name}_client", client)

            if name == "options":
                adapter = adapter_cls(client, b.instrument_resolver)
            elif name == "futures":
                futures_client = UpstoxFuturesClient(
                    b.context.http_client,
                    b.context.url_resolver,
                    b.instrument_resolver,
                )
                b.futures_client = futures_client
                adapter = adapter_cls(futures_client)
            else:
                adapter = adapter_cls(client)

            setattr(b, name, adapter)
            if capability is not None:
                b._register_capability(capability, adapter)

    def _init_special_adapters(self) -> None:
        b = self._broker
        b.market_data = UpstoxMarketDataAdapter(
            b.market_data_v2, b.market_data_v3, b.historical_v2
        )

        # Orders
        b.idempotency_cache = InMemoryIdempotencyCache()
        b.order_command = UpstoxOrderCommandAdapter(
            b.order_client,
            b.instrument_resolver,
            b.idempotency_cache,
            use_v3=True,
            algo_name=self._settings.algo_name or None,
            market_protection_default=self._settings.market_protection_default,
            event_bus=b._event_bus,
            risk_manager=b._risk_manager,
        )
        b.order_query = UpstoxOrderQueryAdapter(b.order_client, b.instrument_resolver)
        # self.gtt created by _init_core_adapters above
        b.slice = UpstoxSliceAdapter(b.order_client, b.instrument_resolver)
        b.cover = UpstoxCoverOrderAdapter(b.order_client)
        b.alert = UpstoxAlertAdapter(b.gtt)
        b.exit_all = UpstoxExitAllAdapter(b.kill_switch_client)

    def _init_websocket_layer(self) -> None:
        b = self._broker
        settings = self._settings
        b.feed_authorizer = UpstoxFeedAuthorizer(
            b.context.http_client, b.context.url_resolver
        )
        ws_limits = (
            UpstoxV3SubscriptionLimits.for_plus_plan()
            if settings.ws_plus_plan
            else UpstoxV3SubscriptionLimits()
        )
        b.market_data_websocket = UpstoxMarketDataV3Multiplexer(
            authorizer=b.feed_authorizer,
            decoder=UpstoxV3Decoder(),
            limits=ws_limits,
            auto_reconnect=UpstoxAutoReconnect(
                enabled=settings.ws_auto_reconnect,
                interval_seconds=settings.ws_reconnect_interval_s,
                max_retries=settings.ws_reconnect_max_retries,
            ),
            event_bus=b._event_bus,
            backfill_callback=b._backfill_callback,
        )
        b.portfolio_stream = UpstoxPortfolioStream(
            authorizer=b.feed_authorizer,
            event_bus=b._event_bus,
        )

    def _init_services(self) -> None:
        b = self._broker
        settings = self._settings
        # Shared historical data service (V2 historical client)
        b.historical_service = HistoricalDataService(
            b.historical_v2,
            parquet_cache_path=settings.instrument_cache_path,
        )

        # Reconciliation
        if self._reconciliation_service is not None:
            b.reconciliation_service = self._reconciliation_service
        else:
            b.reconciliation_service = UpstoxReconciliationService(
                b.order_client, b.portfolio_client, oms=b._oms, auto_repair=False
            )

    def _init_capabilities(self) -> None:
        b = self._broker
        b.capabilities = _UpstoxCapabilities(
            market_data=MarketDataCapability(
                market_data=b.market_data,
                market_data_v2=b.market_data_v2,
                market_data_v3=b.market_data_v3,
                historical_v2=b.historical_v2,
                historical_v3=b.historical_v3,
                options=b.options,
                futures=b.futures,
                expired_instruments_client=b.expired_instruments_client,
                market_status=b.market_status,
                intelligence=None,
                intelligence_snapshot=None,
            ),
            orders=OrdersCapability(
                order_command=b.order_command,
                order_query=b.order_query,
                slice=b.slice,
                cover=b.cover,
                gtt=b.gtt,
                alert=b.alert,
                exit_all=b.exit_all,
                order_client=b.order_client,
            ),
            portfolio=PortfolioCapability(
                portfolio=b.portfolio,
                margin=b.margin,
                portfolio_client=b.portfolio_client,
                margin_client=b.margin_client,
            ),
            instruments=InstrumentsCapability(
                instrument_resolver=b.instrument_resolver,
                instrument_loader=b.instrument_loader,
                instrument_search=b.instrument_search,
            ),
            streaming=StreamingCapability(
                feed_authorizer=b.feed_authorizer,
                market_data_websocket=b.market_data_websocket,
            ),
        )
        b._register_all_capabilities()


class UpstoxBroker:
    def __init__(
        self,
        settings: UpstoxConnectionSettings | None = None,
        *,
        token_manager: UpstoxTokenManager | None = None,
        oms: Any = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManagerPort | None = None,
        backfill_callback: Any | None = None,
        reconciliation_service: Any | None = None,
    ) -> None:
        if settings is None:
            settings = UpstoxConnectionSettings(client_id="placeholder")

        builder = UpstoxBrokerBuilder(
            broker=self,
            settings=settings,
            token_manager=token_manager,
            oms=oms,
            event_bus=event_bus,
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
        )
        builder.build()

    def _ensure_extended(self) -> None:
        """Load extended adapters on first access (IPO, payments, fundamentals, etc.)."""
        if self._extended_ready:
            return

        import importlib

        for (
            name,
            client_mod,
            client_cls_name,
            adapter_mod,
            adapter_cls_name,
            capability,
        ) in _EXTENDED_ADAPTER_REGISTRY:
            client_cls = getattr(importlib.import_module(client_mod), client_cls_name)
            adapter_cls = getattr(importlib.import_module(adapter_mod), adapter_cls_name)
            client = client_cls(self.context.http_client, self.context.url_resolver)
            setattr(self, f"{name}_client", client)
            adapter = adapter_cls(client)
            setattr(self, name, adapter)
            if capability is not None:
                self._register_capability(capability, adapter)

        snapshot_mod = importlib.import_module("brokers.upstox.market_intelligence.snapshot")
        self.intelligence_snapshot = snapshot_mod.UpstoxMarketIntelligenceSnapshotBuilder(
            self.intelligence_client
        )
        trade_pnl_mod = importlib.import_module("brokers.upstox.market_data.trade_pnl")
        self.trade_pnl_calculator = trade_pnl_mod.TradePnLCalculator(
            self.portfolio_client,
            self.market_data_v2,
        )
        self.capabilities.market_data.intelligence = self.intelligence
        self.capabilities.market_data.intelligence_snapshot = self.intelligence_snapshot
        self._register_capability(Capability.OPTION_GREEKS, self.intelligence)
        self._register_capability(Capability.OI_PCR_MAXPAIN, self.intelligence)
        self._register_capability(Capability.SMARTLIST, self.intelligence)
        self._register_capability(Capability.FII_DII, self.intelligence)
        self._extended_ready = True

    def _register_all_capabilities(self) -> None:
        # Capabilities registered by the _CORE_ADAPTER_REGISTRY loop in __init__:
        #   PORTFOLIO, MARGIN, OPTIONS_CHAIN, FUTURES, MARKET_STATUS,
        #   KILL_SWITCH, GTT_ORDER
        #
        # Extended capabilities (IPO, PAYMENTS, etc.) register in _ensure_extended().
        self._register_capability(Capability.MARKET_DATA, self.market_data)
        self._register_capability(Capability.DEPTH, self.market_data)
        self._register_capability(Capability.HISTORICAL_DATA, self.market_data)
        self._register_capability(Capability.ORDER_COMMAND, self.order_command)
        self._register_capability(Capability.ORDER_QUERY, self.order_query)
        self._register_capability(Capability.INSTRUMENTS, self.instrument_resolver)
        self._register_capability(Capability.SLICE_ORDER, self.slice)
        self._register_capability(Capability.ORDER_SLICING, self.slice)
        self._register_capability(Capability.COVER_ORDER, self.cover)
        self._register_capability(Capability.ALERTS, self.alert)
        self._register_capability(Capability.WEBSOCKET, self.market_data_websocket)
        self._register_capability(Capability.PORTFOLIO_STREAM, self.portfolio_stream)
        self._register_capability(Capability.IDEMPOTENCY, self.idempotency_cache)
        self._register_capability(Capability.WEBHOOKS, self.feed_authorizer)
        self._register_capability(Capability.MULTI_ORDER, self.order_client)
        self._register_capability(Capability.AMO_ORDER, self.order_command)
        self._register_capability(Capability.EXIT_ALL, self.exit_all)
        if self._risk_manager is not None:
            self._register_capability(Capability.SESSION_RISK, self._risk_manager)

    # ── Connection lifecycle ──

    @property
    def name(self) -> str:
        return self._name

    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @property
    def token_manager(self) -> UpstoxTokenManager:
        return self._token_manager

    def connect(self) -> bool:
        try:
            self._token_manager.bootstrap()
            self._set_status(ConnectionStatus.CONNECTED)
            return True
        except Exception as exc:
            logger.warning("Upstox connect failed: %s", exc)
            self._set_status(ConnectionStatus.DISCONNECTED)
            return False

    def disconnect(self) -> bool:
        self._set_status(ConnectionStatus.DISCONNECTED)
        return True

    def reconnect(self) -> bool:
        return self.connect()

    # ── Capability registry ──

    def _register_capability(self, capability: Capability, provider: Any) -> None:
        self._capabilities.add(capability)
        self._capability_map[capability] = provider

    def has_capability(self, capability: Capability) -> bool:
        return capability in self._capabilities

    def get_capability(self, capability: Capability) -> Any:
        return self._capability_map.get(capability)

    def _set_status(self, status: ConnectionStatus) -> None:
        self._status = status

    def __enter__(self) -> UpstoxBroker:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()
