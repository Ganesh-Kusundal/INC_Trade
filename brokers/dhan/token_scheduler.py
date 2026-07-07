"""Dhan token refresh scheduler — backward-compatible alias.

Re-exports :class:`BackgroundTokenScheduler` from
``brokers.common.auth.token_scheduler`` for backward compatibility.
New code should import the generic class directly.
"""

from __future__ import annotations

from brokers.common.auth.token_scheduler import BackgroundTokenScheduler


class DhanTokenScheduler(BackgroundTokenScheduler):
    """Backward-compatible alias for :class:`BackgroundTokenScheduler`.

    .. deprecated::
        Use ``BackgroundTokenScheduler`` from ``brokers.common.auth.token_scheduler``.
    """


__all__ = ["DhanTokenScheduler"]
