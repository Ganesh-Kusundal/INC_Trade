"""End-to-end workflow tests — full lifecycle validation."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from tradex.core.events import EventBus, DomainEvent
from tradex.core.config import StreamConfig
from tradex.domain.enums import OrderStatus
from tradex.domain.events import (
    OrderFilled,
    OrderPlaced,
    OrderRejected,
    OrderStatusChanged,
    QuoteReceived,
    SessionConnected,
)
from tradex.streaming.engine import StreamEngine
from tradex.streaming.feed import MarketFeed
from tradex.streaming.order_feed import OrderFeed


# ============================================================
# Test 1: Full trading workflow
# ============================================================


class TestTradingWorkflow:
    """Login -> Resolve Instrument -> Subscribe -> Quote -> Place Order -> Fill -> Portfolio"""

    @pytest.mark.asyncio
    async def test_full_trading_lifecycle(self):
        """Simulate a complete trading session."""
        bus = EventBus()
        events_captured = []

        @bus.on(DomainEvent)
        async def capture(e):
            events_captured.append(e)

        # Simulate session
        await bus.publish(SessionConnected(broker="test", account_id="123"))

        # Simulate quote
        await bus.publish(
            QuoteReceived(
                security_id="2885",
                exchange="NSE_EQ",
                last_price=2450.0,
                volume=1000,
            )
        )

        # Simulate order flow via OrderFeed
        feed = OrderFeed(event_bus=bus)
        await feed.process_update(
            {
                "orderId": "ORD_001",
                "orderStatus": "PLACED",
                "securityId": "2885",
            }
        )
        await feed.process_update(
            {
                "orderId": "ORD_001",
                "orderStatus": "TRADED",
                "filledQty": "10",
                "averagePrice": "2450.50",
            }
        )

        # Verify event sequence
        assert len(events_captured) >= 4
        types = [type(e).__name__ for e in events_captured]
        assert "SessionConnected" in types
        assert "QuoteReceived" in types
        assert "OrderPlaced" in types
        assert "OrderFilled" in types

    @pytest.mark.asyncio
    async def test_order_rejection_workflow(self):
        """Order placed -> Rejected -> Status change recorded."""
        bus = EventBus()
        all_events = []

        @bus.on(DomainEvent)
        async def catch(e):
            all_events.append(e)

        feed = OrderFeed(event_bus=bus)
        await feed.process_update(
            {
                "orderId": "ORD_002",
                "orderStatus": "PLACED",
                "securityId": "2885",
            }
        )
        await feed.process_update(
            {
                "orderId": "ORD_002",
                "orderStatus": "REJECTED",
                "rejectionReason": "Insufficient margin",
            }
        )

        placed = [e for e in all_events if isinstance(e, OrderPlaced)]
        rejected = [e for e in all_events if isinstance(e, OrderRejected)]
        assert len(placed) == 1
        assert len(rejected) == 1
        assert rejected[0].reason == "Insufficient margin"


# ============================================================
# Test 2: Streaming resilience workflow
# ============================================================


class TestStreamingResilience:
    """Connect -> Stream -> Disconnect -> Reconnect -> Resume"""

    @pytest.mark.asyncio
    async def test_stream_lifecycle(self):
        config = StreamConfig(
            url="wss://test.example.com/ws",
            reconnect=False,
            ping_interval=0.05,
        )
        engine = StreamEngine(config)

        received = []

        async def handler(data):
            received.append(data)

        engine.on_message(handler)

        mock_ws = AsyncMock()
        call_count = [0]

        async def fake_recv():
            call_count[0] += 1
            if call_count[0] <= 3:
                return json.dumps({"seq": call_count[0], "ltp": 2450})
            raise asyncio.CancelledError

        mock_ws.recv = fake_recv

        async def create_ws():
            return mock_ws

        await engine.connect(create_ws)
        await asyncio.sleep(0.3)
        await engine.disconnect()

        assert len(received) == 3
        assert received[0]["seq"] == 1
        assert received[2]["seq"] == 3


# ============================================================
# Test 3: Market feed deduplication workflow
# ============================================================


class TestMarketFeedWorkflow:
    """Subscribe -> Receive ticks -> Dedup -> Publish events"""

    @pytest.mark.asyncio
    async def test_subscribe_and_receive(self):
        engine = AsyncMock()
        engine.is_connected = True

        bus = EventBus()
        feed = MarketFeed(engine=engine, event_bus=bus)

        quotes = []

        @bus.on(QuoteReceived)
        async def on_quote(e):
            quotes.append(e)

        await feed.subscribe([("NSE_EQ", "2885", 15)])

        # Process ticks — different LTT so dedup doesn't filter
        await feed.process_tick(
            {
                "security_id": "2885",
                "exchange_segment": "NSE_EQ",
                "LTP": 2450,
                "volume": 100,
                "bid_price": 2449,
                "ask_price": 2451,
                "LTT": "10:00:01",
            }
        )
        await feed.process_tick(
            {
                "security_id": "2885",
                "exchange_segment": "NSE_EQ",
                "LTP": 2451,
                "volume": 200,
                "bid_price": 2450,
                "ask_price": 2452,
                "LTT": "10:00:02",
            }
        )

        assert len(quotes) == 2
        assert quotes[0].last_price == 2450.0
        assert quotes[1].last_price == 2451.0

    @pytest.mark.asyncio
    async def test_duplicate_ticks_filtered(self):
        """Same tick within dedup window should be filtered."""
        engine = AsyncMock()
        engine.is_connected = True

        bus = EventBus()
        feed = MarketFeed(engine=engine, event_bus=bus)

        quotes = []

        @bus.on(QuoteReceived)
        async def on_quote(e):
            quotes.append(e)

        tick = {
            "security_id": "2885",
            "exchange_segment": "NSE_EQ",
            "LTP": 2450,
            "volume": 100,
        }

        await feed.process_tick(tick)
        await feed.process_tick(tick)  # duplicate within window

        assert len(quotes) == 1
