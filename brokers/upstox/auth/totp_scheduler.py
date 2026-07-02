"""TOTP token refresh scheduler — background service for daily token refresh.

Runs a daemon thread that refreshes the Upstox token daily at a configured
time (default: 8:00 AM IST, before market open at 9:15 AM IST).

This service is a :class:`brokers.common.lifecycle.ManagedService`.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from brokers.upstox.auth.token_manager import UpstoxTokenManager
from infrastructure.lifecycle import HealthState, ManagedService, build_health

logger = logging.getLogger(__name__)


class TotpRefreshScheduler(ManagedService):
    """Background scheduler that refreshes TOTP tokens daily.

    Usage::

        token_manager = UpstoxTokenManager(settings)
        scheduler = TotpRefreshScheduler(
            token_manager,
            refresh_hour=8,
            refresh_minute=0,
        )
        lifecycle.register(scheduler)
        lifecycle.start_all()
    """

    name: str = "upstox.totp_refresh_scheduler"

    def __init__(
        self,
        token_manager: UpstoxTokenManager,
        refresh_hour: int = 8,
        refresh_minute: int = 0,
        on_refresh_success: Callable[[], None] | None = None,
        on_refresh_error: Callable[[Exception], None] | None = None,
    ):
        self._token_manager = token_manager
        self._refresh_hour = refresh_hour
        self._refresh_minute = refresh_minute
        self._on_success = on_refresh_success
        self._on_error = on_refresh_error
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._refresh_count = 0
        self._last_refresh_at: float | None = None
        self._last_error: str | None = None

    # ── ManagedService contract ──────────────────────────────────────────

    def start(self) -> None:
        """Start the background refresh thread. Idempotent."""
        if self._thread and self._thread.is_alive():
            logger.debug("TOTP refresh scheduler already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="upstox-totp-refresh",
        )
        self._thread.start()
        logger.info(
            "TOTP refresh scheduler started (daily at %02d:%02d IST)",
            self._refresh_hour,
            self._refresh_minute,
        )

    def stop(self, timeout_seconds: float = 30.0) -> None:
        """Stop the background refresh thread. Idempotent."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout_seconds)
            if self._thread.is_alive():
                logger.warning(
                    "TOTP refresh scheduler did not stop within %.1fs",
                    timeout_seconds,
                )
            self._thread = None
        logger.info(
            "TOTP refresh scheduler stopped (refreshed %d times)",
            self._refresh_count,
        )

    def health(self):  # type: ignore[override]
        running = self._thread is not None and self._thread.is_alive()
        if not running:
            state = HealthState.STOPPED
            detail = "not running"
        elif self._last_error is not None:
            state = HealthState.DEGRADED
            detail = f"last error: {self._last_error}"
        else:
            state = HealthState.HEALTHY
            detail = f"refreshed {self._refresh_count} times"

        return build_health(
            self.name,
            state,
            detail=detail,
            metrics={
                "refresh_count": self._refresh_count,
                "refresh_time": f"{self._refresh_hour:02d}:{self._refresh_minute:02d}",
            },
        )

    # ── Public helpers ───────────────────────────────────────────────────

    def refresh_now(self) -> bool:
        """Trigger an immediate token refresh. Returns True if successful."""
        return self._do_refresh()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    # ── Background loop ──────────────────────────────────────────────────

    def _run(self) -> None:
        """Main scheduler loop — check every 60 seconds if it's time to refresh."""
        ist = ZoneInfo("Asia/Kolkata")
        while not self._stop_event.is_set():
            try:
                now = datetime.now(ist)
                target_time = now.replace(
                    hour=self._refresh_hour,
                    minute=self._refresh_minute,
                    second=0,
                    microsecond=0,
                )

                # If target time has passed today, schedule for tomorrow
                if now >= target_time:
                    target_time += timedelta(days=1)

                wait_seconds = (target_time - now).total_seconds()

                # Sleep in 60-second increments to allow graceful shutdown
                while wait_seconds > 60 and not self._stop_event.is_set():
                    self._stop_event.wait(timeout=60)
                    wait_seconds -= 60

                if not self._stop_event.is_set() and wait_seconds > 0:
                    self._stop_event.wait(timeout=wait_seconds)

                # Time to refresh!
                if not self._stop_event.is_set():
                    self._do_refresh()

            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.error("TOTP scheduler error: %s", exc)
                if self._on_error:
                    try:
                        self._on_error(exc)
                    except Exception as exc2:
                        logger.debug("error_callback_failed: %s", exc2)

    def _do_refresh(self) -> bool:
        """Perform token refresh via TOTP or OAuth refresh grant when needed."""
        try:
            if self._token_manager.settings.is_totp:
                state = self._token_manager.current_state()
                now_ms = int(time.time() * 1000)
                try:
                    buffer_minutes = int(
                        getattr(self._token_manager.settings, "refresh_buffer_minutes", 30) or 30
                    )
                except (TypeError, ValueError):
                    buffer_minutes = 30
                buffer_ms = buffer_minutes * 60 * 1000
                exp_ms = 0
                if state is not None:
                    try:
                        exp_ms = int(getattr(state, "expires_at_ms", 0) or 0)
                    except (TypeError, ValueError):
                        exp_ms = 0
                if exp_ms > now_ms + buffer_ms:
                    logger.info(
                        "Upstox token still valid (expires=%d), skipping daily TOTP refresh",
                        state.expires_at_ms,
                    )
                    self._last_error = None
                    return True

            logger.info("Starting daily TOTP token refresh...")
            if self._token_manager.settings.is_totp:
                self._token_manager.refresh_totp()
            else:
                self._token_manager.force_refresh()

            self._refresh_count += 1
            self._last_refresh_at = time.monotonic()
            self._last_error = None

            logger.info("TOTP token refresh successful (count=%d)", self._refresh_count)

            if self._on_success:
                try:
                    self._on_success()
                except Exception as exc:
                    logger.debug("success_callback_failed: %s", exc)

            return True

        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.error("TOTP token refresh failed: %s", exc)

            if self._on_error:
                try:
                    self._on_error(exc)
                except Exception as exc2:
                    logger.debug("error_callback_failed: %s", exc2)

            return False
