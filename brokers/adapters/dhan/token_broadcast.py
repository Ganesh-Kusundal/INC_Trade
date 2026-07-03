"""Token broadcast — notify consumers when tokens are refreshed.

Uses weak references to prevent memory leaks when receivers are garbage collected.
Supports idempotent registration (same receiver won't be added twice).
"""

from __future__ import annotations

import logging
import weakref
from typing import Any, Callable

logger = logging.getLogger(__name__)

TokenReceiver = Callable[[str], None]


class TokenReceiverRef:
    """Weak reference wrapper for token receivers.

    Uses WeakMethod for bound methods to prevent memory leaks.
    Uses strong reference for other callables (functions, lambdas, callable instances)
    since they are typically short-lived or module-level.
    Implements __eq__ and __hash__ for idempotent registration.
    """

    def __init__(self, receiver: TokenReceiver) -> None:
        self._receiver: TokenReceiver | None = None
        self._weak_method: weakref.WeakMethod[TokenReceiver] | None = None

        if hasattr(receiver, "__self__") and hasattr(receiver, "__func__"):
            try:
                self._weak_method = weakref.WeakMethod(receiver)
            except TypeError:
                self._receiver = receiver
        else:
            self._receiver = receiver

    def deref(self) -> TokenReceiver | None:
        """Dereference the weak reference. Returns None if collected."""
        if self._weak_method is not None:
            return self._weak_method()
        return self._receiver

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TokenReceiverRef):
            return NotImplemented
        self_target = self.deref()
        other_target = other.deref()
        if self_target is None and other_target is None:
            return False
        return self_target == other_target

    def __hash__(self) -> int:
        target = self.deref()
        return hash(target) if target is not None else id(self)


class TokenBroadcast:
    """Broadcast token updates to registered receivers.

    Usage::

        broadcast = TokenBroadcast()
        broadcast.register_receiver(http_client.update_token)
        broadcast.register_receiver(streaming.update_token)

        # After token refresh:
        delivered = broadcast.broadcast("new-token-value")
    """

    def __init__(self) -> None:
        self._token_receivers: list[TokenReceiverRef] = []
        self._refresh_count: int = 0
        self._error_count: int = 0

    def register_receiver(self, receiver: TokenReceiver) -> TokenReceiver:
        """Register a receiver to be notified on token refresh.

        Idempotent — same receiver won't be added twice.

        Args:
            receiver: Callable that accepts a token string.

        Returns:
            The registered receiver (for chaining).
        """
        ref = TokenReceiverRef(receiver)
        for existing in self._token_receivers:
            if existing == ref:
                return receiver
        self._token_receivers.append(ref)
        logger.debug(
            "token_receiver_registered", extra={"count": len(self._token_receivers)}
        )
        return receiver

    def unregister_receiver(self, receiver: TokenReceiver) -> bool:
        """Unregister a receiver.

        Args:
            receiver: The receiver to remove.

        Returns:
            True if the receiver was found and removed.
        """
        ref = TokenReceiverRef(receiver)
        for i, existing in enumerate(self._token_receivers):
            if existing == ref:
                self._token_receivers.pop(i)
                return True
        return False

    def broadcast(self, new_token: str) -> int:
        """Broadcast a new token to all registered receivers.

        Dead references are automatically cleaned up.
        Per-receiver exceptions are isolated (one failure doesn't stop others).

        Args:
            new_token: The new token value to broadcast.

        Returns:
            Number of receivers successfully notified.
        """
        delivered = 0
        dead_refs = []

        for ref in list(self._token_receivers):
            receiver = ref.deref()
            if receiver is None:
                dead_refs.append(ref)
                continue
            try:
                receiver(new_token)
                delivered += 1
            except Exception as exc:
                self._error_count += 1
                logger.warning(
                    "token_receiver_failed",
                    extra={"error": str(exc), "receiver": type(receiver).__name__},
                )

        for ref in dead_refs:
            with _suppress_value_error():
                self._token_receivers.remove(ref)

        self._refresh_count += 1
        if delivered > 0:
            logger.info("token_broadcast_complete", extra={"delivered": delivered})
        return delivered

    @property
    def receiver_count(self) -> int:
        """Number of active (non-collected) receivers."""
        self._cleanup_dead_refs()
        return len(self._token_receivers)

    @property
    def token_refresh_metrics(self) -> dict[str, int]:
        """Metrics about token refresh activity."""
        return {
            "refresh_count": self._refresh_count,
            "error_count": self._error_count,
            "receiver_count": self.receiver_count,
        }

    def _cleanup_dead_refs(self) -> None:
        """Remove references to garbage-collected receivers."""
        self._token_receivers = [
            ref for ref in self._token_receivers if ref.deref() is not None
        ]


class _suppress_value_error:
    """Context manager to suppress ValueError during list.remove()."""

    def __enter__(self) -> None:
        pass

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        return exc_type is ValueError
