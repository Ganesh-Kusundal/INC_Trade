"""Token refresh scheduler — background daemon for automatic token refresh.

Runs a daemon thread that periodically checks token validity and triggers
refresh when expired or about to expire. Handles rate-limit backoff.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Callable

from brokers.domain.exceptions import TokenRateLimitError

if TYPE_CHECKING:
    from brokers.adapters.dhan.auth import DhanAuth

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 60
_DEFAULT_BUFFER_SECONDS = 300.0
_DEFAULT_STOP_TIMEOUT_SECONDS = 10
_MAX_BACKOFF_SECONDS = 600


class TokenRefreshScheduler:
    """Background daemon for automatic token refresh.

    Periodically checks token validity and triggers refresh when needed.
    Uses a shared refresh_lock to coordinate with HTTP 401 handler.
    Implements exponential backoff on rate-limit errors.

    Args:
        auth: DhanAuth instance for token generation.
        interval_seconds: How often to check token validity.
        buffer_seconds: Refresh token if it expires within this window.
        refresh_lock: Shared lock to prevent concurrent refresh.
        on_refresh: Callback invoked with new token after successful refresh.
    """

    def __init__(
        self,
        auth: DhanAuth,
        interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
        buffer_seconds: float = _DEFAULT_BUFFER_SECONDS,
        refresh_lock: threading.Lock | None = None,
        on_refresh: Callable[[str], None] | None = None,
    ):
        self._auth = auth
        self._interval = interval_seconds
        self._buffer = buffer_seconds
        self._refresh_lock = refresh_lock
        self._on_refresh = on_refresh

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._refresh_count: int = 0
        self._error_count: int = 0
        self._backoff_until: float = 0.0
        self._backoff_seconds: float = 120.0

    def start(self) -> None:
        """Start the background refresh daemon."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("token_scheduler_already_running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="token-refresh",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "token_scheduler_started",
            extra={
                "interval_seconds": self._interval,
                "buffer_seconds": self._buffer,
            },
        )

    def stop(self, timeout_seconds: float = _DEFAULT_STOP_TIMEOUT_SECONDS) -> None:
        """Stop the background refresh daemon.

        Args:
            timeout_seconds: Max time to wait for thread to exit.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_seconds)
            if self._thread.is_alive():
                logger.warning("token_scheduler_stop_timeout")
            self._thread = None
        logger.info("token_scheduler_stopped")

    def refresh_now(self) -> bool:
        """Trigger an immediate token refresh.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        return self._do_refresh()

    @property
    def is_running(self) -> bool:
        """Check if the scheduler daemon is running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def refresh_count(self) -> int:
        """Number of successful refreshes."""
        return self._refresh_count

    @property
    def refresh_lock(self) -> threading.Lock | None:
        """The shared refresh lock."""
        return self._refresh_lock

    def health(self) -> dict:
        """Health status and metrics."""
        state = "STOPPED"
        if self.is_running:
            state = "DEGRADED" if self._backoff_until > time.monotonic() else "HEALTHY"

        return {
            "state": state,
            "refresh_count": self._refresh_count,
            "error_count": self._error_count,
            "interval_seconds": self._interval,
            "buffer_seconds": self._buffer,
            "is_running": self.is_running,
        }

    def _run(self) -> None:
        """Main daemon loop."""
        while not self._stop_event.is_set():
            try:
                self._do_refresh()
            except Exception as exc:
                logger.error(
                    "token_scheduler_unexpected_error",
                    extra={"error": str(exc)},
                )
            self._stop_event.wait(timeout=self._interval)

    def _do_refresh(self) -> bool:
        """Check token validity and refresh if needed.

        Returns:
            True if token is valid (or was refreshed), False on failure.
        """
        now = time.monotonic()
        if now < self._backoff_until:
            logger.debug("token_refresh_backoff_active")
            return False

        state = self._auth.state
        if state is not None and state.is_valid() and not state.refresh_recommended(self._buffer):
            return True

        if self._refresh_lock is not None:
            acquired = self._refresh_lock.acquire(timeout=0.1)
            if not acquired:
                logger.debug("token_refresh_lock_busy")
                return False
            try:
                return self._perform_refresh()
            finally:
                self._refresh_lock.release()
        else:
            return self._perform_refresh()

    def _perform_refresh(self) -> bool:
        """Actually perform the token refresh.

        Returns:
            True if successful, False otherwise.
        """
        try:
            token = self._auth.generate_token()
            self._refresh_count += 1
            self._backoff_seconds = 120.0

            if self._on_refresh is not None:
                try:
                    self._on_refresh(token)
                except Exception as exc:
                    logger.warning(
                        "token_refresh_callback_failed",
                        extra={"error": str(exc)},
                    )

            logger.info(
                "token_refreshed",
                extra={"refresh_count": self._refresh_count},
            )
            return True

        except TokenRateLimitError as exc:
            self._error_count += 1
            self._backoff_until = time.monotonic() + self._backoff_seconds
            self._backoff_seconds = min(self._backoff_seconds * 2, _MAX_BACKOFF_SECONDS)
            logger.warning(
                "token_refresh_rate_limited",
                extra={
                    "error": str(exc),
                    "backoff_seconds": self._backoff_seconds,
                },
            )
            return False

        except Exception as exc:
            self._error_count += 1
            logger.error(
                "token_refresh_failed",
                extra={"error": str(exc)},
            )
            return False
