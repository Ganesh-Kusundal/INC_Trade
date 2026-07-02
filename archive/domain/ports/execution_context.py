"""Context flags for execution submission — shared across broker adapters and OMS."""
from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Generator

_oms_managed_submit: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_oms_managed_submit", default=False,
)


def is_oms_managed_submit() -> bool:
    """True when the current call chain is inside an OMS submit_fn."""
    return _oms_managed_submit.get()


@contextlib.contextmanager
def oms_managed() -> Generator[None, None, None]:
    """Mark the enclosed broker call as OMS-managed.

    Broker adapters check :func:`is_oms_managed_submit` to suppress
    duplicate event publishing — the OMS publishes its own lifecycle
    events after the submit_fn returns.
    """
    token = _oms_managed_submit.set(True)
    try:
        yield
    finally:
        _oms_managed_submit.reset(token)
