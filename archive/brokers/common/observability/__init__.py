"""Observability layer — structured audit events and metrics for multi-broker operations.

This module provides:
- Structured audit event emission for routing, historical fetches, merges, quota, and streams
- Metrics catalog for Prometheus export
- Observability hooks used by coordinators and orchestrators
- Broker health checks for the centralized infrastructure health registry

All audit events are emitted as structured logs with consistent field names
so they can be queried, aggregated, and alerted on.
"""

from brokers.common.observability.audit import (
    emit_historical_chunk,
    emit_merge_conflict,
    emit_quota_event,
    emit_routing_decision,
    emit_stream_state_change,
)
from brokers.common.observability.health_check import (
    BrokerConnectivityHealthCheck,
    register_broker_health_check,
)
from infrastructure.observability import EventMetrics

__all__ = [
    "BrokerConnectivityHealthCheck",
    "EventMetrics",
    "emit_historical_chunk",
    "emit_merge_conflict",
    "emit_quota_event",
    "emit_routing_decision",
    "emit_stream_state_change",
    "register_broker_health_check",
]
