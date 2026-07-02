"""Integration tests for StreamOrchestrator health and subscription lifecycle."""

from __future__ import annotations

import asyncio
from unittest import mock

import pytest

from brokers.common.broker_port import BrokerStreamPlan
from brokers.common.policy import auto_dual_broker_policy
from brokers.common.registry import BrokerRegistry
from brokers.common.router import BrokerRouter
from brokers.common.stream_orchestrator import (
    MarketTick,
    StreamOrchestrator,
    SubscriptionRequest,
)
from brokers.common.tests.fixtures.in_memory_gateway import InMemoryBrokerGateway
from brokers.dhan.capabilities import dhan_capabilities
from brokers.upstox.capabilities import upstox_capabilities
from domain.stream_health import FreshnessState, SubscriptionState, TransportState
from infrastructure.time_service import time_service


class _RecordingConsumer:
    def __init__(self, consumer_id: str = "consumer-1") -> None:
        self._id = consumer_id
        self.ticks: list[MarketTick] = []

    def consumer_id(self) -> str:
        return self._id

    async def on_market_tick(self, tick: MarketTick) -> None:
        self.ticks.append(tick)

    async def on_order_update(self, update) -> None:
        pass

    async def on_stream_health_change(self, session_id: str, health) -> None:
        pass


@pytest.fixture
async def orchestrator():
    registry = BrokerRegistry()
    registry.register(InMemoryBrokerGateway("dhan", dhan_capabilities()))
    registry.register(InMemoryBrokerGateway("upstox", upstox_capabilities()))
    router = BrokerRouter(registry, auto_dual_broker_policy())
    orch = StreamOrchestrator(registry=registry, router=router)
    await orch.start()
    yield orch
    await orch.stop()


class TestStreamOrchestrator:
    @pytest.mark.asyncio
    async def test_subscribe_returns_subscription_id(self, orchestrator):
        consumer = _RecordingConsumer()
        sub_id = await orchestrator.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer,
                instruments=frozenset({"RELIANCE:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )
        assert sub_id
        await orchestrator.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_session_created_and_healthy_after_subscribe(self, orchestrator):
        consumer = _RecordingConsumer()
        sub_id = await orchestrator.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer,
                instruments=frozenset({"RELIANCE:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )
        sessions = orchestrator.all_sessions()
        assert len(sessions) >= 1
        session = sessions[0]
        assert session.broker_id in {"dhan", "upstox"}
        assert session.health.transport == TransportState.CONNECTED
        assert session.health.subscription == SubscriptionState.ACKNOWLEDGED
        await orchestrator.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_deliver_tick_updates_freshness(self, orchestrator):
        consumer = _RecordingConsumer()
        sub_id = await orchestrator.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer,
                instruments=frozenset({"RELIANCE:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )
        session = orchestrator.all_sessions()[0]
        tick = orchestrator._normalize_tick(
            {"symbol": "RELIANCE", "exchange": "NSE", "ltp": 2500.0, "volume": 100},
            session.session_id,
            session.broker_id,
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
        assert tick is not None
        await orchestrator._deliver_tick(session.session_id, tick)
        assert consumer.ticks
        health = orchestrator.session_health(session.session_id)
        assert health is not None
        assert health.freshness == FreshnessState.FRESH
        await orchestrator.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_session_when_last_consumer(self, orchestrator):
        consumer = _RecordingConsumer()
        sub_id = await orchestrator.subscribe(
            SubscriptionRequest(
                stream_kind="order",
                consumer=consumer,
                instruments=frozenset(),
                modes=frozenset(),
            )
        )
        assert orchestrator.all_sessions()
        await orchestrator.unsubscribe(sub_id)
        assert orchestrator.all_sessions() == []

    @pytest.mark.asyncio
    async def test_build_stream_summary(self, orchestrator):
        consumer = _RecordingConsumer()
        sub_id = await orchestrator.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer,
                instruments=frozenset({"RELIANCE:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )
        session = orchestrator.all_sessions()[0]
        summary = orchestrator.build_stream_summary(session.broker_id)
        assert summary.active_sessions >= 1
        # Freshness starts UNKNOWN until first tick — not yet healthy
        assert summary.healthy_sessions == 0
        await orchestrator.unsubscribe(sub_id)

    def test_stream_health_stale_when_freshness_not_within_sla(self):
        from domain.stream_health import StreamHealth

        health = StreamHealth(
            transport=TransportState.CONNECTED,
            subscription=SubscriptionState.ACKNOWLEDGED,
            freshness=FreshnessState.STALE,
        )
        assert not health.healthy()
        assert any("freshness" in r for r in health.failure_reasons())


class _TransportLossGateway:
    """Simulates a broker gateway that drops transport while preserving tick delivery."""

    def __init__(self) -> None:
        self._connected = True
        self._plans: list[BrokerStreamPlan] = []
        self._tick_callback = None

    @property
    def broker_id(self) -> str:
        return "dhan"

    def list_capabilities(self):
        from brokers.common.capabilities import CapabilityDescriptor

        return CapabilityDescriptor.build(dhan_capabilities(), frozenset())

    def supports(self, feature: str) -> bool:
        return True

    async def open_market_stream(self, plan: BrokerStreamPlan):
        self._plans.append(plan)
        if plan.on_raw_frame is not None:
            self._tick_callback = plan.on_raw_frame

        handle = mock.MagicMock()
        handle.is_connected = lambda: self._connected
        handle.disconnect = mock.AsyncMock(side_effect=self._simulate_transport_loss)
        return handle

    async def open_order_stream(self, plan: BrokerStreamPlan):
        return await self.open_market_stream(plan)

    def _simulate_transport_loss(self) -> None:
        self._connected = False

    def deliver_tick(self, symbol: str = "RELIANCE", ltp: float = 100.0) -> None:
        if self._tick_callback:
            self._tick_callback(
                {"symbol": symbol, "exchange": "NSE", "ltp": ltp, "volume": 1}
            )

    async def health(self):
        from brokers.common.broker_port import BrokerHealthSnapshot

        return BrokerHealthSnapshot(broker_id="dhan", alive=True, auth_valid=True)


class _MarketTickConsumer:
    def __init__(self, consumer_id: str) -> None:
        self._id = consumer_id
        self.ticks: list[MarketTick] = []

    def consumer_id(self) -> str:
        return self._id

    async def on_market_tick(self, tick: MarketTick) -> None:
        self.ticks.append(tick)

    async def on_order_update(self, update) -> None:
        pass

    async def on_stream_health_change(self, session_id: str, health) -> None:
        pass


@pytest.fixture
async def orchestrator_with_transport_loss():
    gateway = _TransportLossGateway()
    registry = BrokerRegistry()
    registry.register(gateway)
    router = BrokerRouter(registry, auto_dual_broker_policy(execution_account="dhan"))
    orch = StreamOrchestrator(registry=registry, router=router)
    await orch.start()
    yield orch, gateway
    await orch.stop()


class TestStreamOrchestratorAfterTransportLoss:
    @pytest.mark.asyncio
    async def test_ticks_resume_after_reconnect(self, orchestrator_with_transport_loss):
        orch, gateway = orchestrator_with_transport_loss
        consumer = _MarketTickConsumer("desk-a")
        sub_id = await orch.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer,
                instruments=frozenset({"RELIANCE:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )

        assert gateway._plans[0].on_raw_frame is not None
        gateway.deliver_tick()
        await asyncio.sleep(0.05)
        assert len(consumer.ticks) == 1

        gateway._connected = False
        await asyncio.sleep(2.5)

        assert len(gateway._plans) >= 2
        assert gateway._plans[-1].on_raw_frame is not None

        gateway._connected = True
        gateway.deliver_tick(ltp=101.0)
        await asyncio.sleep(0.05)
        assert len(consumer.ticks) >= 2

        await orch.unsubscribe(sub_id)


class TestStreamOrchestratorSharedSession:
    @pytest.mark.asyncio
    async def test_second_consumer_adds_instruments_to_existing_session(
        self, orchestrator_with_transport_loss
    ):
        orch, gateway = orchestrator_with_transport_loss
        consumer_a = _MarketTickConsumer("desk-a")
        consumer_b = _MarketTickConsumer("desk-b")

        sub_a = await orch.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer_a,
                instruments=frozenset({"RELIANCE:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )
        session = orch.all_sessions()[0]
        session.health.freshness = FreshnessState.FRESH
        session.health.last_valid_tick_at = time_service.now()

        sub_b = await orch.subscribe(
            SubscriptionRequest(
                stream_kind="market",
                consumer=consumer_b,
                instruments=frozenset({"TCS:NSE"}),
                modes=frozenset({"LTP"}),
            )
        )

        assert len(orch.all_sessions()) == 1
        assert "TCS:NSE" in orch.all_sessions()[0].instruments
        assert len(gateway._plans) >= 2

        await orch.unsubscribe(sub_a)
        await orch.unsubscribe(sub_b)
