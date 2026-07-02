"""Tests for infrastructure.observability.alerting — AlertingEngine coverage."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infrastructure.observability.alerting import (
    AlertingEngine,
    AlertLevel,
    AlertRule,
)
from infrastructure.observability.event_metrics import EventMetrics


@pytest.fixture
def metrics():
    return EventMetrics()


@pytest.fixture
def engine(metrics):
    return AlertingEngine(metrics, cooldown_seconds=0.01)


class TestAlertRule:
    def test_creation(self):
        rule = AlertRule(
            name="test_rule",
            metric_pattern="ORDER/*",
            threshold=10.0,
            level=AlertLevel.WARNING,
            description="Test rule",
        )
        assert rule.name == "test_rule"
        assert rule.threshold == 10.0
        assert rule.level == AlertLevel.WARNING

    def test_has_required_fields(self):
        rule = AlertRule(
            name="test",
            metric_pattern="*",
            threshold=1.0,
            level=AlertLevel.INFO,
            description="desc",
        )
        assert rule.name == "test"
        assert rule.metric_pattern == "*"
        assert rule.threshold == 1.0


class TestAlertLevel:
    def test_values(self):
        assert AlertLevel.INFO == "INFO"
        assert AlertLevel.WARNING == "WARNING"
        assert AlertLevel.CRITICAL == "CRITICAL"


class TestAlertingEngine:
    def test_register_rule(self, engine):
        rule = AlertRule(
            name="rule1",
            metric_pattern="ORDER/*",
            threshold=5.0,
            level=AlertLevel.WARNING,
            description="desc",
        )
        engine.register_rule(rule)
        assert engine.rule_count == 1

    def test_register_empty_name_raises(self, engine):
        rule = AlertRule(
            name="",
            metric_pattern="*",
            threshold=1.0,
            level=AlertLevel.INFO,
            description="desc",
        )
        with pytest.raises(ValueError, match="empty"):
            engine.register_rule(rule)

    def test_register_negative_threshold_raises(self, engine):
        rule = AlertRule(
            name="bad",
            metric_pattern="*",
            threshold=-1.0,
            level=AlertLevel.INFO,
            description="desc",
        )
        with pytest.raises(ValueError, match="negative"):
            engine.register_rule(rule)

    def test_unregister_rule(self, engine):
        rule = AlertRule(
            name="rule1",
            metric_pattern="*",
            threshold=1.0,
            level=AlertLevel.INFO,
            description="desc",
        )
        engine.register_rule(rule)
        assert engine.unregister_rule("rule1") is True
        assert engine.rule_count == 0

    def test_unregister_nonexistent_returns_false(self, engine):
        assert engine.unregister_rule("nonexistent") is False

    def test_add_callback(self, engine):
        cb = MagicMock()
        engine.add_callback(cb)
        assert len(engine._callbacks) == 1

    def test_remove_callback(self, engine):
        cb = MagicMock()
        engine.add_callback(cb)
        assert engine.remove_callback(cb) is True
        assert len(engine._callbacks) == 0

    def test_remove_nonexistent_callback_returns_false(self, engine):
        assert engine.remove_callback(MagicMock()) is False

    def test_evaluate_fires_alert_when_threshold_exceeded(self, engine, metrics):
        rule = AlertRule(
            name="high_errors",
            metric_pattern="ORDER/*",
            threshold=5.0,
            level=AlertLevel.CRITICAL,
            description="Too many errors",
        )
        engine.register_rule(rule)
        metrics.inc("ORDER", "error", 10)
        alerts = engine.evaluate_all()
        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.CRITICAL

    def test_evaluate_no_alert_when_below_threshold(self, engine, metrics):
        rule = AlertRule(
            name="low_errors",
            metric_pattern="ORDER/*",
            threshold=100.0,
            level=AlertLevel.WARNING,
            description="desc",
        )
        engine.register_rule(rule)
        metrics.inc("ORDER", "error", 5)
        alerts = engine.evaluate_all()
        assert len(alerts) == 0

    def test_deduplication_within_cooldown(self, engine, metrics):
        rule = AlertRule(
            name="dedup_test",
            metric_pattern="ORDER/*",
            threshold=1.0,
            level=AlertLevel.WARNING,
            description="desc",
        )
        engine.register_rule(rule)
        metrics.inc("ORDER", "error", 5)
        alerts1 = engine.evaluate_all()
        alerts2 = engine.evaluate_all()
        assert len(alerts1) == 1
        assert len(alerts2) == 0

    def test_callback_invoked_on_alert(self, engine, metrics):
        cb = MagicMock()
        engine.add_callback(cb)
        rule = AlertRule(
            name="cb_test",
            metric_pattern="ORDER/*",
            threshold=1.0,
            level=AlertLevel.WARNING,
            description="desc",
        )
        engine.register_rule(rule)
        metrics.inc("ORDER", "error", 5)
        engine.evaluate_all()
        cb.assert_called_once()

    def test_rule_level_callback(self, engine, metrics):
        cb = MagicMock()
        rule = AlertRule(
            name="rule_cb",
            metric_pattern="ORDER/*",
            threshold=1.0,
            level=AlertLevel.WARNING,
            description="desc",
            callback=cb,
        )
        engine.register_rule(rule)
        metrics.inc("ORDER", "error", 5)
        engine.evaluate_all()
        cb.assert_called_once()

    def test_pattern_matching(self, engine, metrics):
        rule = AlertRule(
            name="pattern",
            metric_pattern="ORDER/error",
            threshold=1.0,
            level=AlertLevel.WARNING,
            description="desc",
        )
        engine.register_rule(rule)
        metrics.inc("ORDER", "error", 5)
        alerts = engine.evaluate_all()
        assert len(alerts) == 1

    def test_pattern_no_match(self, engine, metrics):
        rule = AlertRule(
            name="no_match",
            metric_pattern="ORDER/error",
            threshold=1.0,
            level=AlertLevel.WARNING,
            description="desc",
        )
        engine.register_rule(rule)
        metrics.inc("TICK", "handler_error", 5)
        alerts = engine.evaluate_all()
        assert len(alerts) == 0

    def test_wildcard_pattern(self, engine, metrics):
        rule = AlertRule(
            name="wildcard",
            metric_pattern="*/handler_error",
            threshold=1.0,
            level=AlertLevel.WARNING,
            description="desc",
        )
        engine.register_rule(rule)
        metrics.inc("TICK", "handler_error", 5)
        alerts = engine.evaluate_all()
        assert len(alerts) == 1

    def test_properties(self, engine, metrics):
        assert engine.metrics is metrics
        assert engine.cooldown_seconds == 0.01

    def test_clear_fired_alerts(self, engine, metrics):
        rule = AlertRule(
            name="clear_test",
            metric_pattern="ORDER/*",
            threshold=1.0,
            level=AlertLevel.WARNING,
            description="desc",
        )
        engine.register_rule(rule)
        metrics.inc("ORDER", "error", 5)
        engine.evaluate_all()
        assert len(engine._fired_alerts) == 1
        engine.clear_fired_alerts()
        assert len(engine._fired_alerts) == 0
