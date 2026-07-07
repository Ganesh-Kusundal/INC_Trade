"""Tests for the streaming framework — StreamEngine, MarketFeed, OrderFeed."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from tradex.core.events import EventBus
from tradex.domain.enums import OrderStatus
from tradex.domain.events import QuoteReceived
from tradex.streaming.engine import StreamConfig, StreamEngine
from tradex.streaming.feed import MarketFeed
from tradex.streaming.order_feed import OrderFeed

# ============================================================
# StreamEngine
# ============================================================


class TestStreamEngine:
    def test_initial_state(self):
        config = StreamConfig(url="wss://test.example.com/ws")
        engine = StreamEngine(config)
        assert not engine.is_connected

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        config = StreamConfig(url="wss://test.example.com/ws", reconnect=False)
        engine = StreamEngine(config)

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.CancelledError)

        async def create_ws():
            return mock_ws

        await engine.connect(create_ws)
        assert engine.is_connected

        await engine.disconnect()
        assert not engine.is_connected

    @pytest.mark.asyncio
    async def test_message_handler(self):
        config = StreamConfig(url="wss://test.example.com/ws", reconnect=False)
        engine = StreamEngine(config)

        received = []

        async def handler(data):
            received.append(data)

        engine.on_message(handler)

        mock_ws = AsyncMock()
        msg = json.dumps({"type": "tick", "ltp": 2450})
        call_count = [0]

        async def fake_recv():
            call_count[0] += 1
            if call_count[0] == 1:
                return msg
            raise asyncio.CancelledError

        mock_ws.recv = fake_recv
        mock_ws.close = AsyncMock()

        async def create_ws():
            return mock_ws

        await engine.connect(create_ws)
        await asyncio.sleep(0.2)
        await engine.disconnect()

        assert len(received) == 1
        assert received[0]["type"] == "tick"

    @pytest.mark.asyncio
    async def test_on_connect_callback(self):
        config = StreamConfig(url="wss://test.example.com/ws", reconnect=False)
        engine = StreamEngine(config)

        connected_called = [False]

        async def on_connect():
            connected_called[0] = True

        engine.on_connect(on_connect)

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.CancelledError)

        async def create_ws():
            return mock_ws

        await engine.connect(create_ws)
        await asyncio.sleep(0.05)
        await engine.disconnect()

        assert connected_called[0]

    @pytest.mark.asyncio
    async def test_on_disconnect_callback(self):
        config = StreamConfig(
            url="wss://test.example.com/ws",
            reconnect=True,
            max_reconnect_attempts=0,
        )
        engine = StreamEngine(config)

        disconnect_reasons = []

        async def on_disconnect(reason):
            disconnect_reasons.append(reason)

        engine.on_disconnect(on_disconnect)

        async def failing_ws():
            raise ConnectionError("test")

        await engine.connect(failing_ws)
        await asyncio.sleep(0.1)

        assert any("Max reconnect" in r for r in disconnect_reasons)

    @pytest.mark.asyncio
    async def test_send_message(self):
        config = StreamConfig(url="wss://test.example.com/ws", reconnect=False)
        engine = StreamEngine(config)

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.CancelledError)
        mock_ws.send = AsyncMock()

        async def create_ws():
            return mock_ws

        await engine.connect(create_ws)
        await asyncio.sleep(0.05)

        await engine.send({"action": "subscribe"})
        mock_ws.send.assert_called_once_with(json.dumps({"action": "subscribe"}))

        await engine.disconnect()

    @pytest.mark.asyncio
    async def test_send_not_connected(self):
        config = StreamConfig(url="wss://test.example.com/ws", reconnect=False)
        engine = StreamEngine(config)

        with pytest.raises(Exception, match="Not connected"):
            await engine.send({"action": "test"})

    @pytest.mark.asyncio
    async def test_heartbeat_ping(self):
        config = StreamConfig(
            url="wss://test.example.com/ws",
            reconnect=False,
            ping_interval=0.05,
        )
        engine = StreamEngine(config)

        mock_ws = AsyncMock()
        ping_count = [0]

        async def fake_recv():
            await asyncio.sleep(2)
            raise asyncio.CancelledError

        async def fake_ping():
            ping_count[0] += 1

        mock_ws.recv = fake_recv
        mock_ws.ping = fake_ping

        async def create_ws():
            return mock_ws

        await engine.connect(create_ws)
        await asyncio.sleep(0.3)
        await engine.disconnect()

        assert ping_count[0] >= 1

    @pytest.mark.asyncio
    async def test_message_queue(self):
        config = StreamConfig(
            url="wss://test.example.com/ws",
            reconnect=False,
            message_buffer_size=10,
        )
        engine = StreamEngine(config)

        mock_ws = AsyncMock()
        msg_count = [0]

        async def fake_recv():
            msg_count[0] += 1
            if msg_count[0] <= 2:
                return json.dumps({"seq": msg_count[0]})
            raise asyncio.CancelledError

        mock_ws.recv = fake_recv

        async def create_ws():
            return mock_ws

        await engine.connect(create_ws)
        await asyncio.sleep(0.2)

        msg = await engine.get_messages(timeout=0.5)
        assert msg is not None
        assert msg["seq"] == 1

        await engine.disconnect()

    @pytest.mark.asyncio
    async def test_get_messages_timeout(self):
        config = StreamConfig(url="wss://test.example.com/ws", reconnect=False)
        engine = StreamEngine(config)

        msg = await engine.get_messages(timeout=0.05)
        assert msg is None

    @pytest.mark.asyncio
    async def test_reconnect_logic(self):
        config = StreamConfig(
            url="wss://test.example.com/ws",
            reconnect=True,
            max_reconnect_attempts=2,
            reconnect_delay=0.01,
        )
        engine = StreamEngine(config)

        connect_count = [0]

        async def create_ws():
            connect_count[0] += 1
            if connect_count[0] > 2:
                raise ConnectionError("done")
            mock_ws = AsyncMock()
            mock_ws.recv = AsyncMock(side_effect=ConnectionError("disconnect"))
            return mock_ws

        await engine.connect(create_ws)
        await asyncio.sleep(0.5)

        assert connect_count[0] >= 2
        assert not engine.is_connected


# ============================================================
# MarketFeed
# ============================================================


class TestMarketFeed:
    @pytest.mark.asyncio
    async def test_subscribe(self):
        engine = AsyncMock()
        engine.is_connected = True
        engine.send = AsyncMock()

        feed = MarketFeed(engine=engine)
        instruments = [("NSE_EQ", "2885", 15)]
        await feed.subscribe(instruments)
        engine.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscribe_no_duplicates(self):
        engine = AsyncMock()
        engine.is_connected = True
        engine.send = AsyncMock()

        feed = MarketFeed(engine=engine)
        instruments = [("NSE_EQ", "2885", 15)]
        await feed.subscribe(instruments)
        await feed.subscribe(instruments)  # duplicate
        engine.send.assert_called_once()  # only one call

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        engine = AsyncMock()
        engine.is_connected = True
        engine.send = AsyncMock()

        feed = MarketFeed(engine=engine)
        instruments = [("NSE_EQ", "2885", 15)]
        await feed.subscribe(instruments)
        await feed.unsubscribe(instruments)
        engine.send.assert_called()

    @pytest.mark.asyncio
    async def test_unsubscribe_not_subscribed(self):
        engine = AsyncMock()
        engine.is_connected = True
        engine.send = AsyncMock()

        feed = MarketFeed(engine=engine)
        instruments = [("NSE_EQ", "2885", 15)]
        await feed.unsubscribe(instruments)
        engine.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_tick_handler(self):
        engine = AsyncMock()
        engine.is_connected = True
        engine.send = AsyncMock()

        feed = MarketFeed(engine=engine)
        received = []

        async def handler(data):
            received.append(data)

        feed.on_tick(handler)
        await feed.process_tick({"security_id": "2885", "LTP": 2450})
        assert len(received) == 1
        assert received[0]["security_id"] == "2885"

    @pytest.mark.asyncio
    async def test_tick_deduplication(self):
        engine = AsyncMock()
        engine.is_connected = True
        engine.send = AsyncMock()

        feed = MarketFeed(engine=engine)
        received = []

        async def handler(data):
            received.append(data)

        feed.on_tick(handler)

        tick = {"security_id": "2885", "LTP": 2450, "LTT": "12345"}
        await feed.process_tick(tick)
        await feed.process_tick(tick)  # duplicate

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_tick_different_time_not_deduped(self):
        engine = AsyncMock()
        engine.is_connected = True
        engine.send = AsyncMock()

        feed = MarketFeed(engine=engine)
        received = []

        async def handler(data):
            received.append(data)

        feed.on_tick(handler)

        await feed.process_tick({"security_id": "2885", "LTP": 2450, "LTT": "t1"})
        await feed.process_tick({"security_id": "2885", "LTP": 2451, "LTT": "t2"})

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_event_bus_publishing(self):
        engine = AsyncMock()
        engine.is_connected = True
        engine.send = AsyncMock()

        event_bus = EventBus()
        feed = MarketFeed(engine=engine, event_bus=event_bus)

        events_received = []

        @event_bus.on(QuoteReceived)
        async def handler(event):
            events_received.append(event)

        await feed.process_tick(
            {
                "security_id": "2885",
                "exchange_segment": "NSE_EQ",
                "LTP": 2450.50,
                "volume": 1000,
                "bid_price": 2449,
                "ask_price": 2451,
            }
        )

        assert len(events_received) == 1
        assert events_received[0].security_id == "2885"
        assert events_received[0].last_price == 2450.50

    @pytest.mark.asyncio
    async def test_tick_handler_error_doesnt_break(self):
        engine = AsyncMock()
        engine.is_connected = True
        engine.send = AsyncMock()

        feed = MarketFeed(engine=engine)

        async def bad_handler(data):
            raise RuntimeError("oops")

        async def good_handler(data):
            pass

        feed.on_tick(bad_handler)
        feed.on_tick(good_handler)

        # Should not raise
        await feed.process_tick({"security_id": "1", "LTP": 100})

    def test_is_connected(self):
        engine = AsyncMock()
        engine.is_connected = True
        feed = MarketFeed(engine=engine)
        assert feed.is_connected

    def test_make_dedup_key(self):
        engine = AsyncMock()
        feed = MarketFeed(engine=engine)

        key = feed._make_dedup_key({"security_id": "2885", "LTT": "12345"})
        assert key == "2885:12345"

        assert feed._make_dedup_key({}) is None

    def test_parse_tick_event(self):
        engine = AsyncMock()
        feed = MarketFeed(engine=engine)

        event = feed._parse_tick_event(
            {
                "security_id": "2885",
                "exchange_segment": "NSE_EQ",
                "LTP": "2450",
                "volume": 500,
                "bid_price": 2449,
                "ask_price": 2451,
            }
        )
        assert event is not None
        assert event.security_id == "2885"
        assert event.last_price == 2450.0

    def test_parse_tick_event_bad_data(self):
        engine = AsyncMock()
        feed = MarketFeed(engine=engine)

        event = feed._parse_tick_event({})
        assert event is None


# ============================================================
# OrderFeed
# ============================================================


class TestOrderFeed:
    @pytest.mark.asyncio
    async def test_process_update_placed(self):
        event_bus = EventBus()
        feed = OrderFeed(event_bus=event_bus)

        events_received = []

        @event_bus.on(QuoteReceived)
        async def catch_quote(event):
            events_received.append(event)

        # We need a more general handler
        from tradex.core.events import DomainEvent

        all_events = []

        @event_bus.on(DomainEvent)
        async def catch_all(event):
            all_events.append(event)

        await feed.process_update(
            {
                "orderId": "ORD_001",
                "orderStatus": "PLACED",
                "securityId": "2885",
            }
        )

        # Should have OrderPlaced + OrderStatusChanged events
        assert len(all_events) >= 2
        from tradex.domain.events import OrderPlaced

        placed_events = [e for e in all_events if isinstance(e, OrderPlaced)]
        assert len(placed_events) == 1
        assert placed_events[0].order_id == "ORD_001"

    @pytest.mark.asyncio
    async def test_process_update_traded(self):
        event_bus = EventBus()
        feed = OrderFeed(event_bus=event_bus)

        from tradex.core.events import DomainEvent

        all_events = []

        @event_bus.on(DomainEvent)
        async def catch_all(event):
            all_events.append(event)

        await feed.process_update(
            {
                "orderId": "ORD_002",
                "orderStatus": "TRADED",
                "filledQty": "10",
                "averagePrice": "2450.50",
            }
        )

        from tradex.domain.events import OrderFilled

        filled = [e for e in all_events if isinstance(e, OrderFilled)]
        assert len(filled) == 1
        assert filled[0].filled_quantity == 10

    @pytest.mark.asyncio
    async def test_process_update_rejected(self):
        event_bus = EventBus()
        feed = OrderFeed(event_bus=event_bus)

        from tradex.core.events import DomainEvent

        all_events = []

        @event_bus.on(DomainEvent)
        async def catch_all(event):
            all_events.append(event)

        await feed.process_update(
            {
                "orderId": "ORD_003",
                "orderStatus": "REJECTED",
                "rejectionReason": "Insufficient margin",
            }
        )

        from tradex.domain.events import OrderRejected

        rejected = [e for e in all_events if isinstance(e, OrderRejected)]
        assert len(rejected) == 1
        assert rejected[0].reason == "Insufficient margin"

    @pytest.mark.asyncio
    async def test_process_update_pending(self):
        event_bus = EventBus()
        feed = OrderFeed(event_bus=event_bus)

        from tradex.core.events import DomainEvent

        all_events = []

        @event_bus.on(DomainEvent)
        async def catch_all(event):
            all_events.append(event)

        await feed.process_update(
            {
                "orderId": "ORD_004",
                "orderStatus": "PENDING",
                "filledQty": "0",
                "pendingQty": "10",
            }
        )

        from tradex.domain.events import OrderStatusChanged

        status_events = [e for e in all_events if isinstance(e, OrderStatusChanged)]
        assert len(status_events) == 1
        assert status_events[0].new_status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_handler_called(self):
        feed = OrderFeed()
        received = []

        async def handler(data):
            received.append(data)

        feed.on_update(handler)
        await feed.process_update({"orderId": "O1", "orderStatus": "PLACED"})
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_handler_error_doesnt_break(self):
        feed = OrderFeed()

        async def bad_handler(data):
            raise RuntimeError("oops")

        feed.on_update(bad_handler)

        # Should not raise
        await feed.process_update({"orderId": "O1", "orderStatus": "PLACED"})

    @pytest.mark.asyncio
    async def test_order_cache(self):
        feed = OrderFeed()
        await feed.process_update({"orderId": "O1", "orderStatus": "PLACED"})
        await feed.process_update({"orderId": "O2", "orderStatus": "PENDING"})

        cached = feed.cached_orders
        assert "O1" in cached
        assert "O2" in cached
        assert len(cached) == 2

    @pytest.mark.asyncio
    async def test_status_changed_always_emitted(self):
        event_bus = EventBus()
        feed = OrderFeed(event_bus=event_bus)

        from tradex.core.events import DomainEvent
        from tradex.domain.events import OrderStatusChanged

        all_events = []

        @event_bus.on(DomainEvent)
        async def catch_all(event):
            all_events.append(event)

        # Cancelled status should emit OrderStatusChanged but not OrderFilled
        await feed.process_update(
            {
                "orderId": "O5",
                "orderStatus": "CANCELLED",
            }
        )

        status_events = [e for e in all_events if isinstance(e, OrderStatusChanged)]
        assert len(status_events) == 1
        assert status_events[0].new_status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_parse_order_update_various_statuses(self):
        event_bus = EventBus()
        feed = OrderFeed(event_bus=event_bus)

        for status_str, expected_cls_name in [
            ("PLACED", "OrderPlaced"),
            ("REJECTED", "OrderRejected"),
            ("TRADED", "OrderFilled"),
            ("PART_TRADED", None),
            ("CANCELLED", None),
            ("PENDING", None),
            ("OPEN", None),
        ]:
            events = feed._parse_order_update(
                {
                    "orderId": "O1",
                    "orderStatus": status_str,
                    "filledQty": "0",
                    "pendingQty": "10",
                }
            )
            # Always has at least OrderStatusChanged
            assert len(events) >= 1
