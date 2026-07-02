"""Token refresh scheduler — background thread for expired-token refresh only.

Runs a daemon thread that checks token validity at regular intervals.
TOTP generation is triggered only when the token is missing or expired —
never when a valid token is still within its JWT lifetime.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from brokers.common.auth import AuthManager, JsonTokenStateStore
from brokers.common.auth.token_persistence import TokenPersistence
from brokers.common.auth.token_policy import should_generate_token
from brokers.common.auth.totp_cooldown import TotpRateLimitError
from domain.constants import (
    DEFAULT_STOP_TIMEOUT_SECONDS,
    DHAN_TOKEN_REFRESH_BUFFER_SECONDS,
    DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS,
)
from infrastructure.lifecycle import HealthState, ManagedService, build_health

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS
_DEFAULT_BUFFER_SECONDS = DHAN_TOKEN_REFRESH_BUFFER_SECONDS


class TokenRefreshScheduler(ManagedService):
    """Background scheduler that refreshes broker tokens only when expired."""

    name: str = "dhan.token_refresh_scheduler"

    def __init__(
        self,
        auth: AuthManager,
        interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
        buffer_seconds: float = _DEFAULT_BUFFER_SECONDS,
        refresh_lock: threading.Lock | None = None,
        on_refresh: Callable[[str], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        token_store: JsonTokenStateStore | None = None,
        env_file: Path | None = None,
    ):
        self._auth = auth
        self._interval = interval_seconds
        self._buffer = buffer_seconds
        self._refresh_lock = refresh_lock or threading.Lock()
        self._on_refresh = on_refresh
        self._on_error = on_error
        self._token_store = token_store
        self._env_file = env_file
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._refresh_count = 0
        self._last_refresh_at: float | None = None
        self._last_error: str | None = None
        self._backoff_until: float | None = None
        self._backoff_seconds = 120

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.debug("Token refresh scheduler already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="token-refresh",
        )
        self._thread.start()
        logger.info(
            "Token refresh scheduler started (interval=%ds, expired-only)",
            self._interval,
        )

    def stop(self, timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout_seconds)
            if self._thread.is_alive():
                logger.warning(
                    "Token refresh scheduler did not stop within %.1fs; "
                    "leaving the daemon to be reaped at process exit",
                    timeout_seconds,
                )
            self._thread = None
        logger.info(
            "Token refresh scheduler stopped (refreshed %d times)",
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
                "interval_seconds": self._interval,
                "buffer_seconds": self._buffer,
            },
        )

    def refresh_now(self) -> bool:
        return self._do_refresh()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    @property
    def refresh_lock(self) -> threading.Lock:
        return self._refresh_lock

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._do_refresh()
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.error("Token refresh scheduler error: %s", exc)
                if self._on_error:
                    try:
                        self._on_error(exc)
                    except Exception as exc2:
                        logger.debug("token_refresh_error_callback_failed: %s", exc2)
            self._stop_event.wait(timeout=self._interval)

    def _do_refresh(self) -> bool:
        if self._backoff_until is not None and time.monotonic() < self._backoff_until:
            remaining = self._backoff_until - time.monotonic()
            logger.debug(
                "token_scheduler_backoff",
                extra={"remaining_seconds": round(remaining, 1)},
            )
            return False

        if not self._refresh_lock.acquire(blocking=False):
            logger.debug(
                "Token refresh already in progress (from HTTP handler); skipping scheduler refresh"
            )
            return False
        try:
            state = self._auth.state
            if state and state.is_valid():
                logger.debug("token valid, skipping generation")
                self._last_error = None
                return True

            if not should_generate_token(state, allow_proactive=False):
                return bool(state and state.is_valid())

            previous_token = state.access_token if state else None
            refreshed = self._auth.acquire()
            if refreshed and refreshed.is_valid():
                if refreshed.access_token != previous_token:
                    if self._token_store is not None:
                        TokenPersistence.save(refreshed, self._token_store, self._env_file)
                    if self._on_refresh:
                        self._on_refresh(refreshed.access_token)
                    self._refresh_count += 1
                    self._last_refresh_at = time.monotonic()
                    logger.info("Token refreshed via scheduler (count=%d)", self._refresh_count)
                self._last_error = None
                self._backoff_until = None
                return True

            self._last_error = "no valid token available"
            logger.warning("Token refresh check failed — no valid token available")
            return False
        except (RuntimeError, TotpRateLimitError) as exc:
            error_msg = str(exc)
            if "rate limit" in error_msg.lower() or "cooldown" in error_msg.lower():
                self._backoff_until = time.monotonic() + self._backoff_seconds
                self._backoff_seconds = min(self._backoff_seconds * 2, 600)
                self._last_error = f"Rate limited: {error_msg}"
                logger.warning(
                    "Token rate limited - backing off",
                    extra={"backoff_seconds": self._backoff_seconds},
                )
            else:
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Token refresh failed: %s", exc)
            if self._on_error:
                try:
                    self._on_error(exc)
                except Exception as exc2:
                    logger.debug("token_refresh_error_callback_failed: %s", exc2)
            return False
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Token refresh failed: %s", exc)
            if self._on_error:
                try:
                    self._on_error(exc)
                except Exception as exc2:
                    logger.debug("token_refresh_error_callback_failed: %s", exc2)
            return False
        finally:
            self._refresh_lock.release()
