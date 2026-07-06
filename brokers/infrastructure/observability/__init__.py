"""Observability layer -- health checks, audit logging, metrics, alerting, and tracing.

This package provides:
- :class:`HealthCheck`, :class:`CheckResult`, :class:`HealthResult` -- health check primitives
- :class:`BrokerConnectivityHealthCheck` -- per-broker REST + WebSocket health
- :class:`AuditLogger`, :class:`AuditEvent` -- structured audit events with correlation ID
- :class:`EventMetrics` -- thread-safe event counters with Prometheus exposition
- :class:`AlertingEngine`, :class:`AlertRule` -- threshold-based alerting with dedup + cooldown
- :func:`trace_operation`, :func:`trace_event_handler`, :class:`TraceContext` -- tracing decorators

Usage::

    from brokers.infrastructure.observability import (
        HealthCheck,
        AuditLogger,
        EventMetrics,
        AlertingEngine,
    )
"""

from __future__ import annotations

from brokers.infrastructure.observability.alerting import (
    Alert,
    AlertingEngine,
    AlertLevel,
    AlertRule,
    create_default_alert_rules,
)
from brokers.infrastructure.observability.audit import (
    ALERTING_RULES,
    FAILURE_TAXONOMY,
    METRICS_CATALOG,
    AuditEvent,
    AuditLogger,
    DegradedModeEvent,
    ExtensionResolveEvent,
    HistoricalChunkEvent,
    HistoricalMergeConflictEvent,
    QuotaEvent,
    RoutingDecisionEvent,
    StreamFailoverEvent,
    StreamStateChangeEvent,
    emit_degraded_mode,
    emit_extension_resolve,
    emit_historical_chunk,
    emit_merge_conflict,
    emit_quota_event,
    emit_routing_decision,
    emit_stream_failover,
    emit_stream_state_change,
)
from brokers.infrastructure.observability.event_metrics import (
    EventMetrics,
    TimestampedCounter,
)
from brokers.infrastructure.observability.health_check import (
    BrokerConnectivityHealthCheck,
    CheckResult,
    HealthCheck,
    HealthRegistry,
    HealthResult,
    health_registry,
    register_broker_health_check,
)
from brokers.infrastructure.observability.opentelemetry_setup import (
    get_tracer,
    otel_available,
    setup_telemetry,
)
from brokers.infrastructure.observability.tracing import (
    TraceContext,
    trace_event_handler,
    trace_operation,
)

__all__ = [
    # Health checks
    "BrokerConnectivityHealthCheck",
    "CheckResult",
    "HealthCheck",
    "HealthRegistry",
    "HealthResult",
    "health_registry",
    "register_broker_health_check",
    # Audit
    "ALERTING_RULES",
    "AuditEvent",
    "AuditLogger",
    "DegradedModeEvent",
    "FAILURE_TAXONOMY",
    "ExtensionResolveEvent",
    "HistoricalChunkEvent",
    "HistoricalMergeConflictEvent",
    "METRICS_CATALOG",
    "QuotaEvent",
    "RoutingDecisionEvent",
    "StreamFailoverEvent",
    "StreamStateChangeEvent",
    "emit_degraded_mode",
    "emit_extension_resolve",
    "emit_historical_chunk",
    "emit_merge_conflict",
    "emit_quota_event",
    "emit_routing_decision",
    "emit_stream_failover",
    "emit_stream_state_change",
    # Event metrics
    "EventMetrics",
    "TimestampedCounter",
    # Alerting
    "Alert",
    "AlertLevel",
    "AlertRule",
    "AlertingEngine",
    "create_default_alert_rules",
    # Tracing
    "TraceContext",
    "get_tracer",
    "otel_available",
    "setup_telemetry",
    "trace_event_handler",
    "trace_operation",
]
