"""Tests for common streaming infrastructure.

Tests for stream_health, queue_iterator, subscription, orchestrator,
transport, and utils modules.
"""

from __future__ import annotations


import pytest

from brokers.infrastructure.streaming.queue_iterator import create_quote_stream
from brokers.infrastructure.streaming.stream_health import (
    FreshnessState,
    MarketTickEvent,
    OrderUpdateEvent,
    StreamHealth,
    StreamHealthChangeEvent,
    SubscriptionState,
    TransportState,
)
from brokers.infrastructure.streaming.subscription import (
    InstrumentKey,
    StreamMode,
    SubscriptionPlan,
)
from brokers.infrastructure.streaming.utils import map_stream_status
from brokers.domain.enums import OrderStatus


# ── StreamHealth tests ─────────────────────────────────────────────────────


class TestStreamHealth:
    def test_default_health_is_unhealthy(self):
        health = StreamHealth()
        assert health.transport == TransportState.CLOSED
        assert health.subscription == SubscriptionState.NONE
        assert health.freshness == FreshnessState.UNKNOWN
        assert health.is_healthy is False
        assert health.is_degraded is False

    def test_healthy_when_all_green(self):
        health = StreamHealth(
            transport=TransportState.OPEN,
            subscription=SubscriptionState.SYNCED,
            freshness=FreshnessState.ACTIVE,
        )
        assert health.is_healthy is True
        assert health.is_degraded is False

    def test_degraded_when_connected_but_stale(self):
        health = StreamHealth(
            transport=TransportState.OPEN,
            subscription=SubscriptionState.SYNCED,
            freshness=FreshnessState.STALE,
        )
        assert health.is_healthy is False
        assert health.is_degraded is True

    def test_not_degraded_when_disconnected(self):
        health = StreamHealth(
            transport=TransportState.CLOSED,
            subscription=SubscriptionState.NONE,
            freshness=FreshnessState.STALE,
        )
        assert health.is_degraded is False

    def test_to_dict(self):
        health = StreamHealth(
            transport=TransportState.OPEN,
            subscription=SubscriptionState.SYNCED,
            freshness=FreshnessState.ACTIVE,
            reconnect_attempts=2,
        )
        d = health.to_dict()
        assert d["transport"] == "OPEN"
        assert d["subscription"] == "SYNCED"
        assert d["freshness"] == "ACTIVE"
        assert d["is_healthy"] is True
        assert d["reconnect_attempts"] == 2


class TestStreamHealthChangeEvent:
    def test_recovery_detection(self):
        prev = StreamHealth(transport=TransportState.CLOSED)
        curr = StreamHealth(
            transport=TransportState.OPEN,
            subscription=SubscriptionState.SYNCED,
            freshness=FreshnessState.ACTIVE,
        )
        event = StreamHealthChangeEvent(previous=prev, current=curr)
        assert event.is_recovery is True
        assert event.is_degradation is False

    def test_degradation_detection(self):
        prev = StreamHealth(
            transport=TransportState.OPEN,
            subscription=SubscriptionState.SYNCED,
            freshness=FreshnessState.ACTIVE,
        )
        curr = StreamHealth(transport=TransportState.CLOSED)
        event = StreamHealthChangeEvent(previous=prev, current=curr)
        assert event.is_recovery is False
        assert event.is_degradation is True


# ── MarketTickEvent tests ──────────────────────────────────────────────────


class TestMarketTickEvent:
    def test_basic_tick(self):
        tick = MarketTickEvent(symbol="RELIANCE", ltp=2500.5)
        assert tick.symbol == "RELIANCE"
        assert tick.ltp == 2500.5
        assert tick.is_depth is False

    def test_depth_tick(self):
        tick = MarketTickEvent(
            symbol="RELIANCE",
            ltp=2500.5,
            depth_bids=((2500.0, 100),),
            depth_asks=((2501.0, 200),),
        )
        assert tick.is_depth is True

    def test_frozen(self):
        tick = MarketTickEvent(symbol="RELIANCE", ltp=2500.5)
        with pytest.raises(AttributeError):
            tick.ltp = 2600.0


# ── OrderUpdateEvent tests ─────────────────────────────────────────────────


class TestOrderUpdateEvent:
    def test_basic_order_update(self):
        update = OrderUpdateEvent(order_id="123", symbol="RELIANCE", status="FILLED")
        assert update.order_id == "123"
        assert update.status == "FILLED"
        assert update.broker_id == ""


# ── QueueIterator tests ────────────────────────────────────────────────────


class TestQueueIterator:
    @pytest.mark.asyncio
    async def test_basic_iteration(self):
        queue, iterator = create_quote_stream()
        await queue.put("item1")
        await queue.put("item2")
        iterator.close()

        items = []
        async for item in iterator:
            items.append(item)
        assert items == ["item1", "item2"]

    @pytest.mark.asyncio
    async def test_close_stops_iteration(self):
        queue, iterator = create_quote_stream()
        iterator.close()

        with pytest.raises(StopAsyncIteration):
            await iterator.__anext__()

    @pytest.mark.asyncio
    async def test_close_with_full_queue(self):
        queue, iterator = create_quote_stream(maxsize=1)
        await queue.put("item1")
        iterator.close()  # Queue is full, oldest item dropped to insert sentinel

        items = []
        async for item in iterator:
            items.append(item)
        # Item was dropped to make room for sentinel — iteration ends immediately
        assert items == []

    @pytest.mark.asyncio
    async def test_is_closed_property(self):
        _, iterator = create_quote_stream()
        assert iterator.is_closed is False
        iterator.close()
        assert iterator.is_closed is True


# ── SubscriptionPlan tests ─────────────────────────────────────────────────


class TestSubscriptionPlan:
    def test_empty_plan(self):
        plan = SubscriptionPlan()
        assert len(plan) == 0
        assert bool(plan) is False

    def test_with_added(self):
        key = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="1333")
        plan = SubscriptionPlan().with_added(key)
        assert len(plan) == 1
        assert key in plan.instruments

    def test_with_removed(self):
        key1 = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="1333")
        key2 = InstrumentKey(symbol="TCS", exchange="NSE", security_id="11536")
        plan = SubscriptionPlan(instruments=frozenset([key1, key2]))
        plan2 = plan.with_removed(key1)
        assert len(plan2) == 1
        assert key1 not in plan2.instruments
        assert key2 in plan2.instruments

    def test_with_mode(self):
        plan = SubscriptionPlan(mode=StreamMode.LTP)
        plan2 = plan.with_mode(StreamMode.FULL)
        assert plan2.mode == StreamMode.FULL
        assert plan.mode == StreamMode.LTP  # Original unchanged

    def test_diff(self):
        key1 = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="1333")
        key2 = InstrumentKey(symbol="TCS", exchange="NSE", security_id="11536")
        key3 = InstrumentKey(symbol="INFY", exchange="NSE", security_id="1594")

        plan1 = SubscriptionPlan(instruments=frozenset([key1, key2]))
        plan2 = SubscriptionPlan(instruments=frozenset([key2, key3]))

        diff = plan2.diff(plan1)
        assert diff.has_changes is True
        assert key3 in diff.added
        assert key1 in diff.removed
        assert key2 not in diff.added
        assert key2 not in diff.removed

    def test_diff_no_changes(self):
        key = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="1333")
        plan1 = SubscriptionPlan(instruments=frozenset([key]))
        plan2 = SubscriptionPlan(instruments=frozenset([key]))

        diff = plan2.diff(plan1)
        assert diff.has_changes is False


# ── InstrumentKey tests ────────────────────────────────────────────────────


class TestInstrumentKey:
    def test_equality_distinct_security_ids(self):
        # security_id IS part of identity — distinct broker IDs with same
        # symbol+exchange must NOT be equal (otherwise cross-broker bridge
        # logic silently dedups Dhan/Upstox instruments).
        key1 = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="1333")
        key2 = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="9999")
        assert key1 != key2

    def test_hash_consistency_distinct_security_ids(self):
        key1 = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="1333")
        key2 = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="9999")
        assert hash(key1) != hash(key2)
        assert len({key1, key2}) == 2  # Distinct keys kept in a set

    def test_equality_same_all_fields(self):
        key1 = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="1333")
        key2 = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="1333")
        assert key1 == key2
        assert hash(key1) == hash(key2)
        assert len({key1, key2}) == 1

    def test_different_symbols_not_equal(self):
        key1 = InstrumentKey(symbol="RELIANCE", exchange="NSE")
        key2 = InstrumentKey(symbol="TCS", exchange="NSE")
        assert key1 != key2

    def test_different_exchanges_not_equal(self):
        key1 = InstrumentKey(symbol="RELIANCE", exchange="NSE", security_id="1333")
        key2 = InstrumentKey(symbol="RELIANCE", exchange="BSE", security_id="1333")
        assert key1 != key2


# ── map_stream_status tests ────────────────────────────────────────────────


class TestMapStreamStatus:
    def test_common_statuses(self):
        assert map_stream_status("OPEN") == OrderStatus.OPEN
        assert map_stream_status("FILLED") == OrderStatus.FILLED
        assert map_stream_status("CANCELLED") == OrderStatus.CANCELLED
        assert map_stream_status("REJECTED") == OrderStatus.REJECTED

    def test_dhan_specific_statuses(self):
        assert map_stream_status("TRADED") == OrderStatus.FILLED
        assert map_stream_status("PART_TRADED") == OrderStatus.PARTIALLY_FILLED
        assert map_stream_status("TRANSIT") == OrderStatus.OPEN

    def test_upstox_specific_statuses(self):
        assert map_stream_status("COMPLETE") == OrderStatus.FILLED
        assert map_stream_status("MODIFIED") == OrderStatus.OPEN

    def test_unknown_status(self):
        assert map_stream_status("UNKNOWN_STATUS") == OrderStatus.UNKNOWN
        assert map_stream_status("") == OrderStatus.UNKNOWN

    def test_case_insensitive(self):
        assert map_stream_status("open") == OrderStatus.OPEN
        assert map_stream_status("Filled") == OrderStatus.FILLED


# ── StreamMode tests ───────────────────────────────────────────────────────


class TestStreamMode:
    def test_values(self):
        assert StreamMode.LTP.value == "ltp"
        assert StreamMode.QUOTE.value == "quote"
        assert StreamMode.FULL.value == "full"
        assert StreamMode.DEPTH.value == "depth"
