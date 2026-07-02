"""Correlation ID framework for distributed tracing.

Re-exports from :mod:`domain.correlation` for backward compatibility.
The canonical implementation lives in domain — infrastructure adds
only the ``with_correlation`` context manager helper.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator

from domain.correlation import (  # noqa: F401
    generate_correlation_id,
    get_current_correlation_id,
    set_current_correlation_id,
)


@contextlib.contextmanager
def with_correlation(cid: str | None = None) -> Generator[str | None, None, None]:
    """Context manager that sets a correlation ID for the duration of the block."""
    if cid is None:
        cid = generate_correlation_id()
    previous = get_current_correlation_id()
    set_current_correlation_id(cid)
    try:
        yield cid
    finally:
        set_current_correlation_id(previous)
