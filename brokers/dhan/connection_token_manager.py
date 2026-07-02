"""ConnectionTokenManager — extracted token receiver and broadcast management.

Previously inlined in :class:`~brokers.dhan.connection.DhanConnection`, this
helper owns the token-receiver registry and broadcast logic that was
previously spread across DhanConnection's ``register_token_receiver()``,
``broadcast_token()``, ``TokenReceiverRef``, and token-refresh-metrics
properties.

Responsibilities
----------------
* Token-receiver registry with weak references (``TokenReceiverRef``)
* Idempotent registration (no duplicate receivers)
* Broadcast a new access token to all receivers
* Automatic cleanup of garbage-collected receivers
* Token refresh metrics for observability

Thread safety
-------------
Single-threaded usage expected (asyncio event loop thread).  The underlying
``list`` operations are not safe for concurrent iteration + mutation; the
caller is responsible for external synchronization.

Usage
-----
Created by ``DhanConnection`` at init time::

    self._token_manager = ConnectionTokenManager()
"""

from __future__ import annotations

import contextlib
import logging
import types
import weakref
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class TokenReceiverRef:
    """Weak-reference wrapper for token receivers to prevent memory leaks.

    Wraps a ``Callable[[str], None]`` in a ``weakref.ref`` (or
    ``weakref.WeakMethod`` for bound methods) so that receivers that
    go out of scope on the caller's side do not prevent garbage
    collection of the connection or its services.

    Equality checks compare the dereferenced targets, which enables
    idempotent registration: registering the same callable twice is
    a no-op.
    """

    def __init__(self, callback: Callable[[str], None]) -> None:
        if isinstance(callback, types.MethodType):
            self._ref = weakref.WeakMethod(callback)
            self._is_method = True
        else:
            try:
                self._ref = weakref.ref(callback)
                self._is_method = False
            except TypeError:
                self._ref = callback
                self._is_method = None

    def deref(self) -> Callable[[str], None] | None:
        """Return the wrapped callable, or None if the referent is dead."""
        if self._is_method is None:
            return self._ref  # type: ignore[return-value]
        return self._ref()

    def __eq__(self, other: Any) -> bool:
        target = self.deref()
        if target is None:
            return False
        if isinstance(other, TokenReceiverRef):
            return target == other.deref()
        return target == other

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        target = self.deref()
        return hash(target) if target is not None else hash(None)


class ConnectionTokenManager:
    """Manages token receivers and broadcast — extracted from DhanConnection.

    Usage::

        mgr = ConnectionTokenManager()

        # Register a receiver (idempotent)
        mgr.register_receiver(feed.update_token)

        # Broadcast a new token to all receivers
        count = mgr.broadcast("new-access-token")

        # Get refresh metrics for observability
        metrics = mgr.token_refresh_metrics
    """

    def __init__(self) -> None:
        self._token_receivers: list[TokenReceiverRef] = []

    # ── Receiver registry ───────────────────────────────────────────────

    def register_receiver(self, receiver: Callable[[str], None]) -> Callable[[str], None]:
        """Register a callable to be invoked on every token broadcast.

        Idempotent: registering the same callable twice is a no-op.
        Returns the receiver unchanged so the call site can be used in
        an expression.
        """
        if receiver is None:
            return receiver

        # Check if already registered (compare dereferenced targets)
        for ref in self._token_receivers:
            if ref == receiver:
                return receiver

        self._token_receivers.append(TokenReceiverRef(receiver))
        return receiver

    # ── Token broadcast ─────────────────────────────────────────────────

    def broadcast(self, new_token: str) -> int:
        """Push ``new_token`` to every registered receiver.

        Returns the number of receivers notified.  Failures in any one
        receiver are logged and isolated so a single broken subscriber
        cannot block the others.  Dead receivers (garbage-collected)
        are automatically cleaned up.
        """
        if not new_token:
            return 0

        delivered = 0
        for ref in list(self._token_receivers):
            receiver = ref.deref()
            if receiver is None:
                with contextlib.suppress(ValueError):
                    self._token_receivers.remove(ref)
                continue
            try:
                receiver(new_token)
                delivered += 1
            except Exception as exc:
                receiver_name = getattr(receiver, "__qualname__", repr(receiver))
                logger.warning(
                    "token_receiver_failed",
                    extra={"receiver": receiver_name, "error": str(exc)},
                )
        return delivered

    @property
    def receiver_count(self) -> int:
        """Return the number of live receivers."""
        # Clean up dead references first
        self._token_receivers = [
            ref for ref in self._token_receivers if ref.deref() is not None
        ]
        return len(self._token_receivers)

    # ── Observability ───────────────────────────────────────────────────

    @property
    def token_refresh_metrics(self) -> dict[str, int]:
        """Return token refresh metrics for observability.

        Returns dict with ``refresh_count`` and ``error_count`` keys.
        This is a default implementation; the actual metrics are
        collected by the token scheduler.
        """
        return {"refresh_count": 0, "error_count": 0}


__all__ = [
    "ConnectionTokenManager",
    "TokenReceiverRef",
]
