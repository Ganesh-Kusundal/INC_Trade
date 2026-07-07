"""Background token refresh scheduler — broker-agnostic.

Runs as a daemon thread and periodically checks if the token needs refreshing.
Implements exponential backoff on rate-limit errors (120s → 240s → 480s → 600s max).

This is the generic scheduler used by all brokers.  Broker-specific aliases
(e.g. ``DhanTokenScheduler``) re-export this class for backward compatibility.

Usage::

    from brokers.common.auth.token_scheduler import BackgroundTokenScheduler
    from brokers.common.auth.token_manager import AuthManager, JsonTokenStateStore

    manager = AuthManager(
        on_acquire=lambda: ...,
        on_refresh=lambda old: ...,
        store=JsonTokenStateStore("~/.token.json"),
    )
    scheduler = BackgroundTokenScheduler(manager)
    scheduler.start()
    # ... scheduler keeps the token alive ...
    scheduler.stop()
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from brokers.common.logging_helpers import log_debug, log_info, log_warning

if TYPE_CHECKING:
    from brokers.common.auth.token_manager import AuthManager

logger = logging.getLogger(__name__)


class BackgroundTokenScheduler:
    """Background thread that proactively refreshes authentication tokens.

    - Checks token validity every ``check_interval`` seconds (default 60s)
    - Refreshes when ``refresh_recommended()`` is True (within buffer of expiry)
    - On rate-limit errors: exponential backoff (120s → 240s → 480s → 600s max)
    - Thread-safe: uses a lock to prevent concurrent refreshes
    """

    _MIN_CHECK_INTERVAL = 30  # seconds
    _MAX_BACKOFF = 600  # 10 minutes
    _INITIAL_BACKOFF = 120  # 2 minutes

    def __init__(
        self,
        auth_manager: AuthManager,
        *,
        check_interval: int = 60,
        refresh_buffer_seconds: float = 300,
    ) -> None:
        self._manager = auth_manager
        self._check_interval = max(self._MIN_CHECK_INTERVAL, check_interval)
        self._refresh_buffer = refresh_buffer_seconds

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._refresh_lock = threading.Lock()
        self._start_lock = threading.Lock()  # Protects _running flag
        self._running = False

        self._backoff = self._INITIAL_BACKOFF
        self._refresh_count = 0
        self._error_count = 0
        self._last_error: str | None = None

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background refresh thread (thread-safe)."""
        with self._start_lock:
            if self._running:
                logger.warning("token_scheduler_already_running")
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="token-scheduler",
                daemon=True,
            )
            self._thread.start()
            self._running = True
            logger.info("token_scheduler_started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background thread (thread-safe)."""
        with self._start_lock:
            if not self._running:
                return
            self._stop_event.set()
            self._running = False
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        logger.info("token_scheduler_stopped")

    # ── Public properties ───────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        with self._start_lock:
            return self._running

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def current_backoff(self) -> int:
        return self._backoff

    # ── Manual refresh ──────────────────────────────────────────────

    def refresh_now(self) -> bool:
        """Manually trigger a token refresh. Returns True on success."""
        return self._do_refresh()

    # ── Internal ─────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main loop: check periodically and refresh when needed."""
        while not self._stop_event.is_set():
            try:
                state = self._manager.state
                if state is not None and state.refresh_recommended(self._refresh_buffer):
                    self._do_refresh()
            except Exception as exc:
                self._last_error = str(exc)
                self._error_count += 1
                logger.warning(
                    "token_scheduler_error",
                    extra={"error": str(exc)[:200], "backoff": self._backoff},
                )

            # Wait for check interval or stop
            self._stop_event.wait(self._check_interval)

    def _do_refresh(self) -> bool:
        """Perform a token refresh with backoff handling."""
        if not self._refresh_lock.acquire(blocking=False):
            # Another refresh is in progress
            log_debug("token_refresh_skipped_concurrent")
            return False

        try:
            self._manager.ensure_fresh()
            self._refresh_count += 1
            self._backoff = self._INITIAL_BACKOFF  # Reset backoff on success
            self._last_error = None
            log_info("token_refreshed", count=self._refresh_count)
            return True
        except Exception as exc:
            self._error_count += 1
            self._last_error = str(exc)

            # Wait current backoff, then increase for next time
            wait_time = self._backoff
            self._backoff = min(self._backoff * 2, self._MAX_BACKOFF)
            log_warning(
                "token_refresh_failed",
                error=str(exc)[:200],
                wait_seconds=wait_time,
                next_backoff=self._backoff,
            )

            # Wait before retry (respects stop event for clean shutdown)
            self._stop_event.wait(wait_time)

            return False
        finally:
            self._refresh_lock.release()


__all__ = ["BackgroundTokenScheduler"]
