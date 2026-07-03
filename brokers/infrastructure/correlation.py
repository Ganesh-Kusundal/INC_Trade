"""Correlation ID management via contextvars.

Provides request-scoped correlation IDs for distributed tracing.
Every log record automatically includes the current correlation_id
via the CorrelationFilter in infrastructure.logging.
"""

from __future__ import annotations

import collections.abc
import contextlib
import contextvars
import uuid

_correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def generate_correlation_id() -> str:
    return uuid.uuid4().hex


def get_current_correlation_id() -> str:
    return _correlation_id_var.get()


def set_current_correlation_id(cid: str) -> contextvars.Token[str]:
    return _correlation_id_var.set(cid)


@contextlib.contextmanager
def with_correlation(correlation_id: str | None = None) -> collections.abc.Iterator[str]:
    cid = correlation_id or generate_correlation_id()
    token = _correlation_id_var.set(cid)
    try:
        yield cid
    finally:
        _correlation_id_var.reset(token)
