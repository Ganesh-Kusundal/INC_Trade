"""Correlation ID — domain-level context propagation.

This is a thin ``ContextVar`` wrapper used by ``DomainEvent.now()``
for automatic end-to-end tracing.  The infrastructure layer
(``infrastructure.correlation``) re-exports everything from here
plus additional helpers (``with_correlation`` context manager).

Why in domain
-------------
``DomainEvent`` is a domain value object.  Its ``now()`` factory
needs to read the current correlation ID without importing from
infrastructure.  Placing the ContextVar here keeps the dependency
arrow clean: domain ← infrastructure (never the reverse).
"""

from __future__ import annotations

import contextvars
import uuid
from datetime import datetime, timezone

_correlation_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def generate_correlation_id() -> str:
    """Generate a unique correlation ID (``{timestamp_ms}-{uuid_short}``)."""
    ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    short = uuid.uuid4().hex[:12]
    return f"{ts_ms}-{short}"


def get_current_correlation_id() -> str | None:
    """Return the correlation ID active on the current context, or ``None``."""
    return _correlation_var.get()


def set_current_correlation_id(cid: str | None) -> None:
    """Set the correlation ID for the current context."""
    _correlation_var.set(cid)
