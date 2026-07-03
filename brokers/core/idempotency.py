"""Backward-compatible alias — use brokers.core.correlation_gate."""

from brokers.core.correlation_gate import CorrelationGate, IdempotencyCache

__all__ = ["CorrelationGate", "IdempotencyCache"]
