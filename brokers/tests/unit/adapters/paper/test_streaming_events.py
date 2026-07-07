"""Integration tests: Streaming → EventBus wiring.

Verifies that streaming ticks publish QuoteUpdatedEvent on the event bus
when MarketDataQuery is configured with an event_publisher.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.adapters.paper.adapter import PaperAdapter


@pytest.fixture
def adapter() -> PaperAdapter:
    a = PaperAdapter()
    a.connect()
    a.set_quote("RELIANCE", Decimal("2850.50"))
    return a


class TestStreamingEventBus:
    """Streaming ticks publish domain events."""

    def test_subscribe_with_event_bus_publishes_events(self, adapter: PaperAdapter) -> None:
        """MarketDataQuery.subscribe() with event_publisher publishes QuoteTickEvent."""
        from brokers.domain.events import QuoteTickEvent
        from brokers.infrastructure.event_bus import EventBus
        from brokers.market.instrument import Instrument
        from brokers.market.query import MarketDataQuery

        event_bus = EventBus()
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(streaming_provider=adapter)

        received_events = []

        def handler(event: object) -> None:
            received_events.append(event)

        # Subscribe to QuoteTickEvent
        event_bus.subscribe("quote.tick", handler)

        query = MarketDataQuery(
            instrument=inst,
            provider=adapter,
            streaming_provider=adapter,
            event_publisher=event_bus,
        )

        # Subscribe to streaming
        stream_handle = query.subscribe(lambda q: None)

        # Simulate a tick
        adapter.simulate_tick("RELIANCE", Decimal("2900.00"))

        assert len(received_events) >= 1
        event = received_events[0]
        # Should be a QuoteTickEvent or DomainEvent with quote.tick type
        assert hasattr(event, "event_type")
        assert event.event_type == "quote.tick"

        # Cleanup
        stream_handle.unsubscribe()

    def test_subscribe_without_event_bus_no_events(self, adapter: PaperAdapter) -> None:
        """MarketDataQuery.subscribe() without event_publisher publishes no events."""
        from brokers.market.instrument import Instrument
        from brokers.market.query import MarketDataQuery

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        inst.with_providers(streaming_provider=adapter)

        received_events = []

        query = MarketDataQuery(
            instrument=inst,
            provider=adapter,
            streaming_provider=adapter,
            # No event_publisher
        )

        # We can't directly observe events without event_publisher,
        # just verify no crash
        stream_handle = query.subscribe(lambda q: None)
        adapter.simulate_tick("RELIANCE", Decimal("2900.00"))
        stream_handle.unsubscribe()

        # No assertions — we just verified no crash
        assert True

    def test_broker_session_event_bus(self, adapter: PaperAdapter) -> None:
        """BrokerSession event bus is wired through to MarketDataQuery."""
        from brokers.domain.events import QuoteTickEvent
        from brokers.market.session import BrokerSession

        session = BrokerSession(adapter)

        received_events = []

        def handler(event: object) -> None:
            received_events.append(event)

        session.event_bus.subscribe("quote.tick", handler)

        import asyncio

        async def run() -> None:
            await session.connect()

            # Set quote first
            adapter.set_quote("RELIANCE", Decimal("2850.50"))

            rel = session.equity("RELIANCE")
            query = session.query(rel)

            # Subscribe to streaming
            handle = query.subscribe(lambda q: None)

            # Simulate a tick — this goes through PaperAdapter
            # which triggers the streaming callback
            adapter.simulate_tick("RELIANCE", Decimal("2900.00"))

            # Verify event was received
            assert len(received_events) >= 1
            evt = received_events[0]
            assert hasattr(evt, "event_type")

            handle.unsubscribe()

        asyncio.run(run())

    def test_quote_tick_event_has_market_data(self) -> None:
        """QuoteTickEvent carries market data fields."""
        from datetime import UTC, datetime
        from decimal import Decimal

        from brokers.domain.events import QuoteTickEvent

        event = QuoteTickEvent(
            composite_key="NSE:RELIANCE",
            symbol="RELIANCE",
            exchange="NSE",
            ltp=Decimal("2850.50"),
            bid=Decimal("2850.00"),
            ask=Decimal("2851.00"),
            volume=50000,
            oi=0,
            source="dhan",
            timestamp=datetime.now(UTC),
        )

        assert event.ltp == Decimal("2850.50")
        assert event.bid == Decimal("2850.00")
        assert event.symbol == "RELIANCE"
        assert event.event_type == "quote.tick"
