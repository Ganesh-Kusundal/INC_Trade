"""Tests for domain historical, stream_health, and events."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from brokers.domain.historical import (
    BarLabelConvention,
    DateRange,
    Gap,
    HistoricalBar,
    HistoricalSeries,
)
from brokers.domain.stream_health import (
    FreshnessState,
    StreamHealth,
    StreamSession,
    StreamStateSummary,
    SubscriptionState,
    TransportState,
)
from brokers.domain.events import (
    EVENT_PAYLOADS,
    DomainEvent,
    EventType,
    canonical_event_types,
    make_payload,
)


# ── Historical ─────────────────────────────────────────────────────────


class TestHistoricalBar:
    def test_defaults(self) -> None:
        bar = HistoricalBar(
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
            event_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=Decimal("2500"),
            high=Decimal("2550"),
            low=Decimal("2480"),
            close=Decimal("2520"),
            volume=100000,
        )
        assert bar.open_interest == 0
        assert bar.is_partial is False
        assert bar.label_convention == BarLabelConvention.LEFT


class TestDateRange:
    def test_days(self) -> None:
        dr = DateRange(start=date(2026, 1, 1), end=date(2026, 1, 10))
        assert dr.days() == 10

    def test_contains(self) -> None:
        dr = DateRange(start=date(2026, 1, 1), end=date(2026, 1, 10))
        assert date(2026, 1, 5) in dr
        assert date(2026, 1, 15) not in dr


class TestGap:
    def test_defaults(self) -> None:
        gap = Gap(start=date(2026, 1, 1), end=date(2026, 1, 5))
        assert gap.reason == "no_data"


class TestHistoricalSeries:
    def test_is_complete(self) -> None:
        series = HistoricalSeries(
            bars=[],
            coverage=DateRange(start=date(2026, 1, 1), end=date(2026, 1, 10)),
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
        )
        assert series.is_complete is True

    def test_has_gaps(self) -> None:
        series = HistoricalSeries(
            bars=[],
            coverage=DateRange(start=date(2026, 1, 1), end=date(2026, 1, 10)),
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
            gaps=[Gap(start=date(2026, 1, 3), end=date(2026, 1, 5))],
        )
        assert series.is_complete is False

    def test_bar_count(self) -> None:
        bar = HistoricalBar(
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
            event_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=Decimal("2500"), high=Decimal("2550"),
            low=Decimal("2480"), close=Decimal("2520"),
            volume=100000,
        )
        series = HistoricalSeries(
            bars=[bar],
            coverage=DateRange(start=date(2026, 1, 1), end=date(2026, 1, 10)),
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="1D",
        )
        assert series.bar_count == 1


# ── Stream health ──────────────────────────────────────────────────────


class TestTransportState:
    def test_is_usable_connected(self) -> None:
        assert TransportState.CONNECTED.is_usable() is True

    def test_is_usable_disconnected(self) -> None:
        assert TransportState.DISCONNECTED.is_usable() is False

    def test_is_usable_reconnecting(self) -> None:
        assert TransportState.RECONNECTING.is_usable() is False


class TestSubscriptionState:
    def test_is_usable_acknowledged(self) -> None:
        assert SubscriptionState.ACKNOWLEDGED.is_usable() is True

    def test_is_usable_partial(self) -> None:
        assert SubscriptionState.PARTIAL.is_usable() is True

    def test_is_usable_idle(self) -> None:
        assert SubscriptionState.IDLE.is_usable() is False


class TestFreshnessState:
    def test_within_sla_fresh(self) -> None:
        assert FreshnessState.FRESH.within_sla() is True

    def test_within_sla_stale(self) -> None:
        assert FreshnessState.STALE.within_sla() is False

    def test_within_sla_unknown(self) -> None:
        assert FreshnessState.UNKNOWN.within_sla() is False


class TestStreamHealth:
    def test_healthy_all_green(self) -> None:
        h = StreamHealth(
            transport=TransportState.CONNECTED,
            subscription=SubscriptionState.ACKNOWLEDGED,
            freshness=FreshnessState.FRESH,
        )
        assert h.healthy() is True
        assert h.failure_reasons() == []

    def test_not_healthy_transport_down(self) -> None:
        h = StreamHealth(
            transport=TransportState.DISCONNECTED,
            subscription=SubscriptionState.ACKNOWLEDGED,
            freshness=FreshnessState.FRESH,
        )
        assert h.healthy() is False
        assert "transport:DISCONNECTED" in h.failure_reasons()

    def test_multiple_failures(self) -> None:
        h = StreamHealth(
            transport=TransportState.DISCONNECTED,
            subscription=SubscriptionState.IDLE,
            freshness=FreshnessState.STALE,
        )
        reasons = h.failure_reasons()
        assert len(reasons) == 3


class TestStreamSession:
    def test_update_transport(self) -> None:
        session = StreamSession(
            session_id="s1",
            broker_id="dhan",
            stream_kind="market",
            instruments=frozenset({"RELIANCE:NSE"}),
            modes=frozenset({"FULL"}),
        )
        now = datetime.now(timezone.utc)
        session.update_transport(TransportState.CONNECTED, at=now)
        assert session.health.transport == TransportState.CONNECTED
        assert session.last_state_change_at == now

    def test_increment_reconnect(self) -> None:
        session = StreamSession(
            session_id="s1",
            broker_id="dhan",
            stream_kind="market",
            instruments=frozenset(),
            modes=frozenset(),
        )
        assert session.reconnect_generation == 0
        session.increment_reconnect()
        assert session.reconnect_generation == 1


class TestStreamStateSummary:
    def test_all_healthy(self) -> None:
        s = StreamStateSummary(
            broker_id="dhan", active_sessions=3, healthy_sessions=3,
            stale_sessions=0, degraded_sessions=0,
        )
        assert s.all_healthy() is True

    def test_not_all_healthy(self) -> None:
        s = StreamStateSummary(
            broker_id="dhan", active_sessions=3, healthy_sessions=2,
            stale_sessions=1, degraded_sessions=0,
        )
        assert s.all_healthy() is False


# ── Events ─────────────────────────────────────────────────────────────


class TestDomainEvent:
    def test_now_factory(self) -> None:
        event = DomainEvent.now("TICK", {"ltp": 2500})
        assert event.event_type == "TICK"
        assert event.payload == {"ltp": 2500}
        assert event.timestamp.tzinfo is not None

    def test_requires_tz_aware_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            DomainEvent(event_type="TICK", timestamp=datetime.now(), payload={})

    def test_has_event_id(self) -> None:
        event = DomainEvent.now("TICK", {})
        assert len(event.event_id) == 16


class TestEventType:
    def test_str_enum(self) -> None:
        assert EventType.TICK == "TICK"
        assert EventType.ORDER_PLACED == "ORDER_PLACED"

    def test_string_comparison(self) -> None:
        assert EventType.TICK == "TICK"


class TestCanonicalEventTypes:
    def test_returns_all(self) -> None:
        types = canonical_event_types()
        assert "TICK" in types
        assert "ORDER_PLACED" in types
        assert isinstance(types, frozenset)


class TestMakePayload:
    def test_pass_through(self) -> None:
        payload = {"ltp": 2500}
        result = make_payload(EventType.TICK, payload, validate=False)
        assert result == payload

    def test_validate_success(self) -> None:
        # TICK has no required keys
        result = make_payload(EventType.TICK, {"ltp": 2500}, validate=True)
        assert result == {"ltp": 2500}

    def test_validate_missing_keys(self) -> None:
        with pytest.raises(KeyError, match="missing required keys"):
            make_payload(EventType.ORDER_CANCELLED, {}, validate=True)

    def test_validate_unknown_event_type(self) -> None:
        # Unknown type passes through
        result = make_payload("UNKNOWN", {"foo": "bar"}, validate=True)
        assert result == {"foo": "bar"}


class TestEventPayloads:
    def test_all_event_types_have_payloads(self) -> None:
        for event_type in EventType:
            assert event_type in EVENT_PAYLOADS, f"Missing payload contract for {event_type}"
