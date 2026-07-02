"""Tests for structured audit emitters."""

import logging

from brokers.common.models import OperationKind, RouteDecision
from brokers.common.observability.audit import (
    ALERTING_RULES,
    FAILURE_TAXONOMY,
    METRICS_CATALOG,
    emit_extension_resolve,
    emit_historical_chunk,
    emit_quota_event,
    emit_routing_decision,
    emit_stream_state_change,
)


class TestAuditEmitters:
    def test_emit_routing_decision(self, caplog):
        decision = RouteDecision(
            operation=OperationKind.PLACE_ORDER,
            primary_broker="dhan",
            trace_id="audit-1",
            policy_version="1.0.0",
            reason_codes=("mode:fixed",),
        )
        with caplog.at_level(logging.INFO, logger="broker.audit"):
            emit_routing_decision(decision)
        assert any("routing.decision" in r.message for r in caplog.records)

    def test_emit_quota_event(self, caplog):
        with caplog.at_level(logging.INFO, logger="broker.audit"):
            emit_quota_event("dhan", "orders", "EXECUTION_CRITICAL", "acquire", wait_ms=1.2)
        assert any("quota.event" in r.message for r in caplog.records)

    def test_emit_historical_chunk(self, caplog):
        with caplog.at_level(logging.INFO, logger="broker.audit"):
            emit_historical_chunk(
                request_id="r1",
                chunk_id="c1",
                broker_id="dhan",
                from_date="2025-01-01",
                to_date="2025-01-31",
                timeframe="1D",
                event_type="complete",
                bar_count=20,
            )
        assert any("historical.chunk" in r.message for r in caplog.records)

    def test_emit_stream_state_change(self, caplog):
        with caplog.at_level(logging.INFO, logger="broker.audit"):
            emit_stream_state_change(
                session_id="s1",
                broker_id="upstox",
                stream_kind="market",
                from_state="CONNECTING",
                to_state="CONNECTED",
                reason="session_opened",
            )
        assert any("stream.session.state_change" in r.message for r in caplog.records)

    def test_emit_extension_resolve(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="broker.audit"):
            emit_extension_resolve("dhan", "NewsProvider", hit=False, alternatives=["upstox"])
        assert any("extension.resolve" in r.message for r in caplog.records)

    def test_metrics_catalog_defined(self):
        assert "quota_utilization_ratio" in METRICS_CATALOG

    def test_alerting_rules_defined(self):
        assert len(ALERTING_RULES) >= 5

    def test_failure_taxonomy_complete(self):
        assert "quota_exhausted" in FAILURE_TAXONOMY
        assert "stream_stale" in FAILURE_TAXONOMY
