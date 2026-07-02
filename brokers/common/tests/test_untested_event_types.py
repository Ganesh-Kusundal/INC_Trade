"""Tests for the 14 event types that previously had zero dedicated tests.

Covers: SCAN_STARTED, SCAN_COMPLETED, CANDIDATE_GENERATED,
STRATEGY_ACTIVATED, STRATEGY_PAUSED, STRATEGY_DISABLED,
POSITION_OPENED, POSITION_CLOSED, RISK_APPROVED, RISK_REJECTED,
HEALTH_CHECK_PASSED, HEALTH_CHECK_FAILED, PORTFOLIO_UPDATED,
METRICS_UPDATED.
"""

from __future__ import annotations

from infrastructure.event_bus import DomainEvent, EventBus, EventType


class TestScannerEvents:
    def test_scan_started_publish_and_subscribe(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.SCAN_STARTED.value, received.append)
        event = DomainEvent.now(
            EventType.SCAN_STARTED.value, {"scanner": "nifty50"}, source="scanner"
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["scanner"] == "nifty50"

    def test_scan_completed_publish_and_subscribe(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.SCAN_COMPLETED.value, received.append)
        event = DomainEvent.now(
            EventType.SCAN_COMPLETED.value,
            {"scanner": "nifty50", "candidates": 12},
            source="scanner",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["candidates"] == 12

    def test_candidate_generated_publish_and_subscribe(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.CANDIDATE_GENERATED.value, received.append)
        event = DomainEvent.now(
            EventType.CANDIDATE_GENERATED.value,
            {"symbol": "RELIANCE", "score": 0.95},
            symbol="RELIANCE",
            source="scanner",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["score"] == 0.95


class TestStrategyEvents:
    def test_strategy_activated(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.STRATEGY_ACTIVATED.value, received.append)
        event = DomainEvent.now(
            EventType.STRATEGY_ACTIVATED.value,
            {"strategy": "momentum_v2", "symbol": "RELIANCE"},
            symbol="RELIANCE",
            source="strategy",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["strategy"] == "momentum_v2"

    def test_strategy_paused(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.STRATEGY_PAUSED.value, received.append)
        event = DomainEvent.now(
            EventType.STRATEGY_PAUSED.value,
            {"strategy": "momentum_v2", "reason": "risk_breach"},
            source="strategy",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["reason"] == "risk_breach"

    def test_strategy_disabled(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.STRATEGY_DISABLED.value, received.append)
        event = DomainEvent.now(
            EventType.STRATEGY_DISABLED.value,
            {"strategy": "momentum_v2"},
            source="strategy",
        )
        bus.publish(event)
        assert len(received) == 1


class TestPositionLifecycleEvents:
    def test_position_opened(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.POSITION_OPENED.value, received.append)
        event = DomainEvent.now(
            EventType.POSITION_OPENED.value,
            {"symbol": "RELIANCE", "side": "BUY", "quantity": 100},
            symbol="RELIANCE",
            source="PositionManager",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["quantity"] == 100

    def test_position_closed(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.POSITION_CLOSED.value, received.append)
        event = DomainEvent.now(
            EventType.POSITION_CLOSED.value,
            {"symbol": "RELIANCE", "pnl": 5000.0},
            symbol="RELIANCE",
            source="PositionManager",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["pnl"] == 5000.0


class TestRiskDecisionEvents:
    def test_risk_approved(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.RISK_APPROVED.value, received.append)
        event = DomainEvent.now(
            EventType.RISK_APPROVED.value,
            {"order_id": "ORD-001", "symbol": "RELIANCE"},
            symbol="RELIANCE",
            source="RiskManager",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["order_id"] == "ORD-001"

    def test_risk_rejected(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.RISK_REJECTED.value, received.append)
        event = DomainEvent.now(
            EventType.RISK_REJECTED.value,
            {"order_id": "ORD-002", "reason": "capital_exceeded"},
            symbol="RELIANCE",
            source="RiskManager",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["reason"] == "capital_exceeded"


class TestHealthEvents:
    def test_health_check_passed(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.HEALTH_CHECK_PASSED.value, received.append)
        event = DomainEvent.now(
            EventType.HEALTH_CHECK_PASSED.value,
            {"service": "dhan.websocket", "latency_ms": 12},
            source="LifecycleManager",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["latency_ms"] == 12

    def test_health_check_failed(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.HEALTH_CHECK_FAILED.value, received.append)
        event = DomainEvent.now(
            EventType.HEALTH_CHECK_FAILED.value,
            {"service": "dhan.websocket", "error": "timeout"},
            source="LifecycleManager",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["error"] == "timeout"


class TestPortfolioAndMetricsEvents:
    def test_portfolio_updated(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.PORTFOLIO_UPDATED.value, received.append)
        event = DomainEvent.now(
            EventType.PORTFOLIO_UPDATED.value,
            {"total_value": 1_000_000, "unrealized_pnl": 5000},
            source="PortfolioManager",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["total_value"] == 1_000_000

    def test_metrics_updated(self):
        bus = EventBus()
        received: list[DomainEvent] = []
        bus.subscribe(EventType.METRICS_UPDATED.value, received.append)
        event = DomainEvent.now(
            EventType.METRICS_UPDATED.value,
            {"metric": "tick_latency_p99", "value_ms": 4.2},
            source="MetricsCollector",
        )
        bus.publish(event)
        assert len(received) == 1
        assert received[0].payload["value_ms"] == 4.2


class TestEventIsolation:
    def test_unrelated_events_do_not_cross_contaminate(self):
        bus = EventBus()
        scan_events: list = []
        risk_events: list = []
        bus.subscribe(EventType.SCAN_STARTED.value, scan_events.append)
        bus.subscribe(EventType.RISK_APPROVED.value, risk_events.append)

        bus.publish(DomainEvent.now(EventType.SCAN_STARTED.value, {"scanner": "x"}, source="s"))
        bus.publish(DomainEvent.now(EventType.RISK_APPROVED.value, {"order_id": "1"}, source="r"))

        assert len(scan_events) == 1
        assert len(risk_events) == 1
        assert scan_events[0].event_type == EventType.SCAN_STARTED.value
        assert risk_events[0].event_type == EventType.RISK_APPROVED.value
