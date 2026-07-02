"""Correlation ID resolution (REF-05 extraction).

Consolidates three near-identical implementations of correlation ID
resolution that previously lived in:

- ``brokers.dhan.gateway.DhanGateway._resolve_correlation_id()``
- ``brokers.upstox.gateway`` (inline)
- ``brokers.common.submission_pipeline.resolve_correlation_id()``
"""

from __future__ import annotations


def resolve_correlation_id(correlation_id: str | None = None) -> str | None:
    """Resolve a correlation ID for order tracing.

    If *correlation_id* is provided returns it as-is.  Otherwise attempts
    to read the current thread's active correlation ID from
    ``infrastructure.correlation`` (optional dependency — returns None if
    the module is not available).
    """
    if correlation_id is not None:
        return correlation_id
    try:
        from infrastructure.correlation import get_current_correlation_id

        return get_current_correlation_id()
    except ImportError:
        return None
