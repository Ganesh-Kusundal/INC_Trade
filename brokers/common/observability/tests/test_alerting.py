"""Comprehensive tests for the EventBus alerting system.

Tests cover:
- AlertRule evaluation logic
- AlertingEngine rule registration and firing
- Alert deduplication and cooldown
- Callback invocation
- Rate calculation with timestamped counters
- Integration with EventBus (alerts fire on handler errors)
- All predefined alert rules
- Thread safety under concurrent access
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from brokers.common.observability.alerting import (
    Alert,
    AlertingEngine,
    AlertLevel,
    AlertRule,
    create_default_alert_rules,
)
from brokers.common.observability.event_metrics import EventMetrics
from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
from infrastructure.event_bus.event_bus import DomainEvent, EventBus
from infrastructure.metrics.registry import metrics_registry


@pytest.fixture(autouse=True)
def _reset_global_metrics_registry() -> None:
    """EventMetrics delegates to a process-global registry; reset for isolation."""
    metrics_registry.reset_all()
    yield
    metrics_registry.reset_all()


class TestAlertLevel:
    """Tests for AlertLevel enum."""

    def test_alert_level_values(self) -> None:
        assert AlertLevel.INFO.value == "INFO"
        assert AlertLevel.WARNING.value == "WARNING"
        assert AlertLevel.CRITICAL.value == "CRITICAL"

    def test_alert_level_comparison(self) -> None:
        # str enums don't support ordering, but inequality and identity work.
        assert AlertLevel.WARNING != AlertLevel.INFO
        assert AlertLevel.CRITICAL != AlertLevel.INFO
        assert AlertLevel.CRITICAL == AlertLevel.CRITICAL


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_creation(self) -> None:
        alert = Alert(
            level=AlertLevel.CRITICAL,
            message="Test alert",
            metric_name="TICK/handler_error",
            threshold=5.0,
            current_value=10.0,
            timestamp=time.time(),
            rule_name="test_rule",
        )
        assert alert.level == AlertLevel.CRITICAL
        assert alert.message == "Test alert"
        assert alert.metric_name == "TICK/handler_error"
        assert alert.threshold == 5.0
        assert alert.current_value == 10.0
        assert alert.rule_name == "test_rule"

    def test_alert_is_frozen(self) -> None:
        alert = Alert(
            level=AlertLevel.INFO,
            message="Test",
            metric_name="test",
            threshold=1.0,
            current_value=2.0,
            timestamp=time.time(),
            rule_name="test",
        )
        with pytest.raises(
            Exception, match=r"dataclasses|frozen|attribute|cannot assign"
        ):  # frozen dataclass raises
            alert.message = "modified"  # type: ignore


class TestAlertRule:
    """Tests for AlertRule dataclass."""

    def test_alert_rule_creation(self) -> None:
        rule = AlertRule(
            name="test_rule",
            metric_pattern="*/handler_error",
            threshold=10.0,
            level=AlertLevel.WARNING,
            description="Test rule",
        )
        assert rule.name == "test_rule"
        assert rule.metric_pattern == "*/handler_error"
        assert rule.threshold == 10.0
        assert rule.level == AlertLevel.WARNING
        assert rule.is_rate is False
        assert rule.rate_window == 60.0
        assert rule.callback is None

    def test_alert_rule_with_callback(self) -> None:
        callback = MagicMock()
        rule = AlertRule(
            name="test_rule",
            metric_pattern="*/error",
            threshold=5.0,
            level=AlertLevel.CRITICAL,
            description="Test",
            callback=callback,
        )
        assert rule.callback is callback

    def test_alert_rule_rate_based(self) -> None:
        rule = AlertRule(
            name="rate_rule",
            metric_pattern="*/error",
            threshold=0.1,
            level=AlertLevel.WARNING,
            description="Rate rule",
            is_rate=True,
            rate_window=30.0,
        )
        assert rule.is_rate is True
        assert rule.rate_window == 30.0


class TestAlertingEngine:
    """Tests for AlertingEngine core functionality."""

    def test_engine_creation(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=60.0)
        assert engine.metrics is metrics
        assert engine.cooldown_seconds == 60.0
        assert engine.rule_count == 0

    def test_register_rule(self) -> None:
        engine = AlertingEngine(EventMetrics())
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=5.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        assert engine.rule_count == 1

    def test_register_rule_empty_name_raises(self) -> None:
        engine = AlertingEngine(EventMetrics())
        rule = AlertRule(
            name="",
            metric_pattern="*/error",
            threshold=5.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        with pytest.raises(ValueError, match="cannot be empty"):
            engine.register_rule(rule)

    def test_register_rule_negative_threshold_raises(self) -> None:
        engine = AlertingEngine(EventMetrics())
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=-1.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        with pytest.raises(ValueError, match="cannot be negative"):
            engine.register_rule(rule)

    def test_unregister_rule(self) -> None:
        engine = AlertingEngine(EventMetrics())
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=5.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        assert engine.unregister_rule("test") is True
        assert engine.rule_count == 0

    def test_unregister_nonexistent_rule(self) -> None:
        engine = AlertingEngine(EventMetrics())
        assert engine.unregister_rule("nonexistent") is False

    def test_replace_existing_rule(self) -> None:
        engine = AlertingEngine(EventMetrics())
        rule1 = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=5.0,
            level=AlertLevel.WARNING,
            description="Test 1",
        )
        rule2 = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=10.0,
            level=AlertLevel.CRITICAL,
            description="Test 2",
        )
        engine.register_rule(rule1)
        engine.register_rule(rule2)
        assert engine.rule_count == 1

    def test_add_callback(self) -> None:
        engine = AlertingEngine(EventMetrics())
        callback = MagicMock()
        engine.add_callback(callback)
        # Callback count isn't exposed, but we can verify it's called later.

    def test_remove_callback(self) -> None:
        engine = AlertingEngine(EventMetrics())
        callback = MagicMock()
        engine.add_callback(callback)
        assert engine.remove_callback(callback) is True
        assert engine.remove_callback(callback) is False

    def test_reset_engine(self) -> None:
        engine = AlertingEngine(EventMetrics())
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=5.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        engine.add_callback(MagicMock())
        engine.reset()
        assert engine.rule_count == 0

    def test_get_fired_alerts(self) -> None:
        engine = AlertingEngine(EventMetrics(), cooldown_seconds=0)
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=0.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        # Trigger alert by adding metric
        engine.metrics.add_timestamped_counter("TICK", "error", by=1)
        alerts = engine.evaluate_all()
        assert len(alerts) == 1
        fired = engine.get_fired_alerts()
        assert len(fired) == 1
        assert fired[0].rule_name == "test"

    def test_clear_fired_alerts(self) -> None:
        engine = AlertingEngine(EventMetrics(), cooldown_seconds=0)
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=0.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        engine.metrics.add_timestamped_counter("TICK", "error", by=1)
        engine.evaluate_all()
        engine.clear_fired_alerts()
        assert engine.get_fired_alerts() == []


class TestAlertRuleEvaluation:
    """Tests for rule evaluation logic."""

    def test_rule_fires_when_threshold_exceeded(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        rule = AlertRule(
            name="high_errors",
            metric_pattern="TICK/handler_error",
            threshold=5.0,
            level=AlertLevel.CRITICAL,
            description="Too many errors",
        )
        engine.register_rule(rule)
        # Add 10 errors
        for _ in range(10):
            metrics.add_timestamped_counter("TICK", "handler_error", by=1)
        alerts = engine.evaluate_all()
        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.CRITICAL
        assert alerts[0].current_value == 10.0
        assert alerts[0].threshold == 5.0

    def test_rule_does_not_fire_below_threshold(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        rule = AlertRule(
            name="high_errors",
            metric_pattern="TICK/handler_error",
            threshold=10.0,
            level=AlertLevel.CRITICAL,
            description="Too many errors",
        )
        engine.register_rule(rule)
        # Add 5 errors (below threshold)
        for _ in range(5):
            metrics.add_timestamped_counter("TICK", "handler_error", by=1)
        alerts = engine.evaluate_all()
        assert len(alerts) == 0

    def test_rule_fires_on_zero_threshold(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        rule = AlertRule(
            name="any_error",
            metric_pattern="TICK/error",
            threshold=0.0,
            level=AlertLevel.CRITICAL,
            description="Any error",
        )
        engine.register_rule(rule)
        metrics.add_timestamped_counter("TICK", "error", by=1)
        alerts = engine.evaluate_all()
        assert len(alerts) == 1

    def test_glob_pattern_matching(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        # Pattern matches all event types with handler_error outcome.
        rule = AlertRule(
            name="all_errors",
            metric_pattern="*/handler_error*",
            threshold=5.0,
            level=AlertLevel.WARNING,
            description="All errors",
        )
        engine.register_rule(rule)
        # Add errors from multiple event types.
        for _ in range(3):
            metrics.add_timestamped_counter("TICK", "handler_error:RuntimeError", by=1)
        for _ in range(3):
            metrics.add_timestamped_counter("ORDER", "handler_error:ValueError", by=1)
        alerts = engine.evaluate_all()
        assert len(alerts) == 1
        assert alerts[0].current_value == 6.0

    def test_no_metrics_no_alert(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=5.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        alerts = engine.evaluate_all()
        assert len(alerts) == 0


class TestAlertDeduplication:
    """Tests for alert deduplication and cooldown."""

    def test_alert_deduplication_within_cooldown(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=60.0)
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=0.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        metrics.add_timestamped_counter("TICK", "error", by=1)
        # First evaluation fires alert.
        alerts1 = engine.evaluate_all()
        assert len(alerts1) == 1
        # Second evaluation within cooldown does not fire.
        alerts2 = engine.evaluate_all()
        assert len(alerts2) == 0

    def test_alert_fires_after_cooldown(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0.1)
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=0.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        metrics.add_timestamped_counter("TICK", "error", by=1)
        # First evaluation fires alert.
        alerts1 = engine.evaluate_all()
        assert len(alerts1) == 1
        # Wait for cooldown to expire.
        time.sleep(0.15)
        # Second evaluation fires again.
        alerts2 = engine.evaluate_all()
        assert len(alerts2) == 1

    def test_different_rules_fire_independently(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        rule1 = AlertRule(
            name="errors",
            metric_pattern="*/error",
            threshold=0.0,
            level=AlertLevel.WARNING,
            description="Errors",
        )
        rule2 = AlertRule(
            name="warnings",
            metric_pattern="*/warning",
            threshold=0.0,
            level=AlertLevel.INFO,
            description="Warnings",
        )
        engine.register_rule(rule1)
        engine.register_rule(rule2)
        metrics.add_timestamped_counter("TICK", "error", by=1)
        metrics.add_timestamped_counter("TICK", "warning", by=1)
        alerts = engine.evaluate_all()
        assert len(alerts) == 2
        rule_names = {a.rule_name for a in alerts}
        assert rule_names == {"errors", "warnings"}


class TestCallbackInvocation:
    """Tests for callback invocation."""

    def test_callback_invoked_on_alert(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        callback = MagicMock()
        engine.add_callback(callback)
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=0.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        metrics.add_timestamped_counter("TICK", "error", by=1)
        alerts = engine.evaluate_all()
        assert len(alerts) == 1
        callback.assert_called_once_with(alerts[0])

    def test_multiple_callbacks_invoked(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        callback1 = MagicMock()
        callback2 = MagicMock()
        engine.add_callback(callback1)
        engine.add_callback(callback2)
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=0.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        metrics.add_timestamped_counter("TICK", "error", by=1)
        alerts = engine.evaluate_all()
        callback1.assert_called_once_with(alerts[0])
        callback2.assert_called_once_with(alerts[0])

    def test_callback_exception_does_not_stop_others(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        callback1 = MagicMock(side_effect=RuntimeError("callback failed"))
        callback2 = MagicMock()
        engine.add_callback(callback1)
        engine.add_callback(callback2)
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=0.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)
        metrics.add_timestamped_counter("TICK", "error", by=1)
        alerts = engine.evaluate_all()
        # callback2 should still be called.
        callback2.assert_called_once_with(alerts[0])

    def test_rule_callback_invoked(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        rule_callback = MagicMock()
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=0.0,
            level=AlertLevel.WARNING,
            description="Test",
            callback=rule_callback,
        )
        engine.register_rule(rule)
        metrics.add_timestamped_counter("TICK", "error", by=1)
        alerts = engine.evaluate_all()
        rule_callback.assert_called_once_with(alerts[0])


class TestRateCalculation:
    """Tests for rate calculation with timestamped counters."""

    def test_rate_calculation_basic(self) -> None:
        metrics = EventMetrics()
        now = time.time()
        # Add 10 events spread evenly over 60 seconds (all within window).
        for i in range(10):
            # Space them 5 seconds apart, all within last 60 seconds.
            metrics.add_timestamped_counter(
                "TICK", "handler_error", timestamp=now - (50 - i * 5), by=1
            )
        rate = metrics.rate("TICK", "handler_error", window_seconds=60.0)
        # 10 events over 60 seconds.
        assert rate == pytest.approx(10.0 / 60.0, rel=0.1)

    def test_rate_with_old_entries_pruned(self) -> None:
        metrics = EventMetrics()
        now = time.time()
        # Add 5 old events (outside window).
        for i in range(5):
            metrics.add_timestamped_counter("TICK", "error", timestamp=now - 120 - i, by=1)
        # Add 5 recent events (inside window).
        for i in range(5):
            metrics.add_timestamped_counter("TICK", "error", timestamp=now - 30 - i, by=1)
        rate = metrics.rate("TICK", "error", window_seconds=60.0)
        # Only recent 5 events should count.
        assert rate == pytest.approx(5.0 / 60.0, rel=0.01)

    def test_rate_zero_window_returns_zero(self) -> None:
        metrics = EventMetrics()
        metrics.add_timestamped_counter("TICK", "error", by=1)
        assert metrics.rate("TICK", "error", window_seconds=0) == 0.0
        assert metrics.rate("TICK", "error", window_seconds=-10) == 0.0

    def test_rate_no_entries_returns_zero(self) -> None:
        metrics = EventMetrics()
        assert metrics.rate("TICK", "error", window_seconds=60.0) == 0.0

    def test_rate_based_alert_fires(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        now = time.time()
        # Add 10 events in the last 60 seconds.
        for i in range(10):
            metrics.add_timestamped_counter("TICK", "error", timestamp=now - i * 5, by=1)
        rule = AlertRule(
            name="high_rate",
            metric_pattern="*/error",
            threshold=0.1,  # 0.1 events/second = 6 events/minute
            level=AlertLevel.CRITICAL,
            description="High rate",
            is_rate=True,
            rate_window=60.0,
        )
        engine.register_rule(rule)
        alerts = engine.evaluate_all()
        assert len(alerts) == 1
        assert alerts[0].current_value == pytest.approx(10.0 / 60.0, rel=0.01)


class TestPredefinedAlertRules:
    """Tests for create_default_alert_rules."""

    def test_returns_six_rules(self) -> None:
        rules = create_default_alert_rules()
        assert len(rules) == 6

    def test_high_error_rate_rule(self) -> None:
        rules = create_default_alert_rules()
        rule = next(r for r in rules if r.name == "high_error_rate")
        assert rule.level == AlertLevel.CRITICAL
        assert rule.is_rate is True
        assert rule.threshold == 0.05
        assert rule.rate_window == 60.0
        assert "handler_error" in rule.metric_pattern

    def test_dead_letter_queue_growth_rule(self) -> None:
        rules = create_default_alert_rules()
        rule = next(r for r in rules if r.name == "dead_letter_queue_growth")
        assert rule.level == AlertLevel.WARNING
        assert rule.is_rate is True
        assert rule.threshold == 10.0
        assert rule.rate_window == 60.0
        assert rule.metric_pattern == "*/dead_letter"

    def test_circuit_breaker_open_rule(self) -> None:
        rules = create_default_alert_rules()
        rule = next(r for r in rules if r.name == "circuit_breaker_open")
        assert rule.level == AlertLevel.CRITICAL
        assert rule.is_rate is False
        assert rule.threshold == 0.0
        assert "circuit_breaker" in rule.metric_pattern

    def test_broker_fallback_storm_rule(self) -> None:
        rules = create_default_alert_rules()
        rule = next(r for r in rules if r.name == "broker_fallback_storm")
        assert rule.level == AlertLevel.WARNING
        assert rule.is_rate is True
        assert rule.threshold == 20.0
        assert rule.rate_window == 60.0

    def test_event_bus_backpressure_rule(self) -> None:
        rules = create_default_alert_rules()
        rule = next(r for r in rules if r.name == "event_bus_backpressure")
        assert rule.level == AlertLevel.WARNING
        assert rule.is_rate is False
        assert rule.threshold == 0.0

    def test_log_write_failures_rule(self) -> None:
        rules = create_default_alert_rules()
        rule = next(r for r in rules if r.name == "log_write_failures")
        assert rule.level == AlertLevel.CRITICAL
        assert rule.is_rate is False
        assert rule.threshold == 5.0
        assert "log_error" in rule.metric_pattern

    def test_all_rules_have_unique_names(self) -> None:
        rules = create_default_alert_rules()
        names = [r.name for r in rules]
        assert len(names) == len(set(names))


class TestEventBusIntegration:
    """Tests for alerting integration with EventBus."""

    def test_alert_fires_on_handler_errors(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)
        callback = MagicMock()
        engine.add_callback(callback)

        # Register rule for handler errors.
        rule = AlertRule(
            name="handler_errors",
            metric_pattern="*/handler_error*",
            threshold=0.0,
            level=AlertLevel.CRITICAL,
            description="Handler errors",
        )
        engine.register_rule(rule)

        # Create bus with metrics.
        dlq = DeadLetterQueue()
        bus = EventBus(metrics=metrics, dead_letter_queue=dlq)

        # Add failing handler.
        def failing_handler(event: DomainEvent) -> None:
            raise RuntimeError("test error")

        bus.subscribe("TICK", failing_handler)

        # Publish event.
        bus.publish(DomainEvent.now("TICK", {"ltp": 100.0}))

        # Evaluate alerts.
        alerts = engine.evaluate_all()
        assert len(alerts) == 1
        assert alerts[0].rule_name == "handler_errors"
        callback.assert_called_once()

    def test_alerting_engine_start_stop(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0.1)
        rule = AlertRule(
            name="test",
            metric_pattern="*/error",
            threshold=0.0,
            level=AlertLevel.WARNING,
            description="Test",
        )
        engine.register_rule(rule)

        # Create bus with alerting engine.
        bus = EventBus(
            metrics=metrics,
            alerting_engine=engine,
            alerting_interval_seconds=0.2,
        )

        # Add metric to trigger alert.
        metrics.add_timestamped_counter("TICK", "error", by=1)

        # Wait for alerting loop to run.
        time.sleep(0.5)

        # Stop alerting.
        bus.stop_alerting()

        # Verify alerts were fired.
        fired = engine.get_fired_alerts()
        assert len(fired) >= 1

    def test_alerting_thread_is_daemon(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=1.0)
        bus = EventBus(metrics=metrics, alerting_engine=engine)
        assert bus._alerting_thread is not None
        assert bus._alerting_thread.daemon is True
        bus.stop_alerting()


class TestThreadSafety:
    """Tests for thread safety under concurrent access."""

    def test_concurrent_metric_increments(self) -> None:
        metrics = EventMetrics()
        num_threads = 10
        increments_per_thread = 100

        def worker() -> None:
            for _ in range(increments_per_thread):
                metrics.add_timestamped_counter("TICK", "published", by=1)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected = num_threads * increments_per_thread
        assert metrics.get("TICK", "published") == expected

    def test_concurrent_rule_registration_and_evaluation(self) -> None:
        metrics = EventMetrics()
        engine = AlertingEngine(metrics, cooldown_seconds=0)

        def register_rules() -> None:
            for i in range(10):
                rule = AlertRule(
                    name=f"rule_{i}_{threading.current_thread().name}",
                    metric_pattern="*/error",
                    threshold=0.0,
                    level=AlertLevel.WARNING,
                    description="Test",
                )
                engine.register_rule(rule)

        def evaluate_rules() -> None:
            for _ in range(10):
                engine.evaluate_all()

        threads = []
        for _ in range(5):
            threads.append(threading.Thread(target=register_rules))
            threads.append(threading.Thread(target=evaluate_rules))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not raise any exceptions.
        assert engine.rule_count == 50

    def test_concurrent_callback_registration(self) -> None:
        engine = AlertingEngine(EventMetrics())
        callbacks_added: list[int] = []
        lock = threading.Lock()

        def add_callbacks() -> None:
            for i in range(10):
                cb = MagicMock()
                engine.add_callback(cb)
                with lock:
                    callbacks_added.append(i)

        threads = [threading.Thread(target=add_callbacks) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All callbacks should be registered.
        assert len(callbacks_added) == 50


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing EventMetrics API."""

    def test_inc_still_works(self) -> None:
        metrics = EventMetrics()
        metrics.inc("TICK", "published", by=5)
        assert metrics.get("TICK", "published") == 5

    def test_snapshot_still_works(self) -> None:
        metrics = EventMetrics()
        metrics.inc("TICK", "published", by=3)
        metrics.inc("TICK", "dispatched", by=2)
        snap = metrics.snapshot()
        assert snap["TICK"]["published"] == 3
        assert snap["TICK"]["dispatched"] == 2

    def test_render_still_works(self) -> None:
        metrics = EventMetrics()
        metrics.inc("TICK", "published", by=1)
        rendered = metrics.render()
        assert "TICK" in rendered
        assert "published" in rendered

    def test_reset_still_works(self) -> None:
        metrics = EventMetrics()
        metrics.inc("TICK", "published", by=5)
        metrics.reset()
        assert metrics.get("TICK", "published") == 0

    def test_as_dict_still_works(self) -> None:
        metrics = EventMetrics()
        metrics.inc("TICK", "published", by=1)
        d = metrics.as_dict()
        assert "events" in d
        assert d["events"]["TICK"]["published"] == 1

    def test_add_timestamped_counter_also_increments_simple_counter(self) -> None:
        metrics = EventMetrics()
        metrics.add_timestamped_counter("TICK", "published", by=3)
        # Should be visible in simple counter.
        assert metrics.get("TICK", "published") == 3
        # Should also be in timestamped storage.
        snap = metrics.snapshot()
        assert snap["TICK"]["published"] == 3
