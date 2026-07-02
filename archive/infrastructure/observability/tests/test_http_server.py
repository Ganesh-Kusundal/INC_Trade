"""Tests for infrastructure.observability.http_server — render_prometheus_metrics."""

from __future__ import annotations

from infrastructure.lifecycle.lifecycle import HealthState
from infrastructure.observability.http_server import (
    _escape_label_value,
    render_prometheus_metrics,
)


class TestEscapeLabelValue:
    def test_simple_string(self):
        assert _escape_label_value("hello") == "hello"

    def test_escape_backslash(self):
        assert _escape_label_value("a\\b") == "a\\\\b"

    def test_escape_quotes(self):
        assert _escape_label_value('a"b') == 'a\\"b'

    def test_escape_newline(self):
        assert _escape_label_value("a\nb") == "a\\nb"


class TestRenderPrometheusMetrics:
    def test_empty_metrics(self):
        result = render_prometheus_metrics({}, {})
        assert "tradexv2_events_total" in result
        assert "tradexv2_service_health" in result

    def test_event_counters(self):
        event_metrics = {"ORDER": {"placed": 10, "rejected": 2}}
        result = render_prometheus_metrics(event_metrics, {})
        assert 'event_type="ORDER"' in result
        assert 'outcome="placed"' in result
        assert "10" in result

    def test_service_health_healthy(self):
        lifecycle = {"broker": {"state": HealthState.HEALTHY}}
        result = render_prometheus_metrics({}, lifecycle)
        assert 'service="broker"' in result
        assert "2" in result

    def test_service_health_unhealthy(self):
        lifecycle = {"broker": {"state": HealthState.UNHEALTHY}}
        result = render_prometheus_metrics({}, lifecycle)
        assert "4" in result

    def test_extra_gauges(self):
        extra = {"daily_pnl": 1500.5, "kill_switch_active": 0.0}
        result = render_prometheus_metrics({}, {}, extra_gauges=extra)
        assert "tradexv2_daily_pnl 1500.5" in result
        assert "tradexv2_kill_switch_active 0.0" in result

    def test_extra_gauges_non_numeric_skipped(self):
        extra = {"valid": 1.0, "invalid": "not_a_number"}
        result = render_prometheus_metrics({}, {}, extra_gauges=extra)
        assert "tradexv2_valid 1.0" in result
        assert "invalid" not in result

    def test_label_escape_in_metrics(self):
        event_metrics = {"ORDER\nINJECTED": {"ok": 1}}
        result = render_prometheus_metrics(event_metrics, {})
        assert "ORDER\\nINJECTED" in result

    def test_multiple_events(self):
        event_metrics = {"A": {"x": 1}, "B": {"y": 2}}
        result = render_prometheus_metrics(event_metrics, {})
        assert 'event_type="A"' in result
        assert 'event_type="B"' in result

    def test_multiple_services(self):
        lifecycle = {
            "svc1": {"state": HealthState.HEALTHY},
            "svc2": {"state": HealthState.DEGRADED},
        }
        result = render_prometheus_metrics({}, lifecycle)
        assert 'service="svc1"' in result
        assert 'service="svc2"' in result

    def test_output_ends_with_newline(self):
        result = render_prometheus_metrics({}, {})
        assert result.endswith("\n")
