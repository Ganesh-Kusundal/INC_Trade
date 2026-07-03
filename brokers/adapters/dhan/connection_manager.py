"""Dhan connection manager — token lifecycle, broadcast, and scheduler.

Extracted from DhanGateway to reduce the god object. Owns the token
lifecycle: acquisition, broadcast, refresh, and persistence.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from brokers.adapters.dhan.auth import DhanAuth
from brokers.adapters.dhan.token_broadcast import TokenBroadcast
from brokers.infrastructure.lifecycle import LifecycleManager
from brokers.infrastructure.storage.token_store import update_env_token
from brokers.infrastructure.token_broadcast import TokenManager
from brokers.ports.token_store import TokenStorePort
from brokers.resilience.token_scheduler import TokenRefreshScheduler

logger = logging.getLogger(__name__)


class DhanConnectionManager:
    """Manages Dhan token lifecycle, broadcast, refresh, and persistence.

    Handles:
    - Token acquisition via DhanAuth
    - Token broadcast to registered consumers (HTTP client, streams)
    - Background token refresh scheduler
    - Token persistence (JSON store + .env file)
    """

    def __init__(
        self,
        auth: DhanAuth,
        client_id: str,
        pin: str | None = None,
        totp_secret: str | None = None,
        token_store: TokenStorePort | None = None,
        env_path: Path | None = None,
        token_state_dir: Path | None = None,
        auto_refresh: bool = True,
        refresh_interval_seconds: int = 60,
        refresh_buffer_seconds: float = 300.0,
        lifecycle: LifecycleManager | None = None,
    ):
        self._auth = auth
        self._env_path = env_path
        self._token_state_dir = token_state_dir
        self._token_store = token_store
        self._refresh_lock = threading.Lock()

        # Token broadcast (legacy) and manager (new)
        self._broadcast = TokenBroadcast()
        token = auth.get_token()
        self._token_manager = TokenManager(initial_token=token or "")

        # Scheduler
        self._scheduler: TokenRefreshScheduler | None = None
        if auto_refresh and pin and totp_secret and token:
            self._scheduler = TokenRefreshScheduler(
                auth=auth,
                interval_seconds=refresh_interval_seconds,
                buffer_seconds=refresh_buffer_seconds,
                refresh_lock=self._refresh_lock,
                on_refresh=self._on_token_refreshed,
            )
            if lifecycle is not None:
                lifecycle.register(self._scheduler)  # type: ignore[arg-type]
            else:
                self._scheduler.start()

    # ── Consumer registration ──────────────────────────────────────────

    def register_consumer(self, update_fn: Callable[[str], None]) -> None:
        """Register a token consumer with both legacy and new broadcast."""
        self._broadcast.register_receiver(update_fn)
        self._token_manager.register_consumer(update_fn)

    # ── Token refresh for HTTP 401 handler ─────────────────────────────

    def refresh_token_for_http(self) -> str | None:
        """Refresh token for HTTP 401 handler. Called under refresh_lock.

        Returns the new token string, or None on failure.
        """
        try:
            token = self._auth.generate_token()
            if token:
                self._persist_token(token)
            return token
        except Exception as exc:
            logger.warning("http_401_token_refresh_failed", extra={"error": str(exc)})
            return None

    # ── Callback from scheduler ────────────────────────────────────────

    def _on_token_refreshed(self, new_token: str) -> None:
        """Callback when token is refreshed by scheduler."""
        self._persist_token(new_token)
        self._broadcast.broadcast(new_token)
        self._token_manager.broadcast_token(new_token)
        logger.info("token_refresh_broadcast_complete")

    # ── Persistence ────────────────────────────────────────────────────

    def persist_initial_token(self) -> None:
        """Persist the initial token if persistence is configured."""
        token = self._auth.get_token()
        if token:
            self._persist_token(token)

    def _persist_token(self, token: str) -> None:
        """Persist token to JSON store and/or .env file."""
        if self._token_store is not None:
            try:
                state = self._auth.state
                if state is not None:
                    self._token_store.save(asdict(state))
            except Exception as exc:
                logger.warning("token_state_persist_failed", extra={"error": str(exc)})

        if self._env_path is not None:
            try:
                update_env_token(self._env_path, token)
            except Exception as exc:
                logger.warning("env_token_persist_failed", extra={"error": str(exc)})

    # ── Metrics ────────────────────────────────────────────────────────

    def get_token_refresh_metrics(self) -> dict[str, int]:
        """Token refresh counters from broadcast + scheduler."""
        metrics = dict(self._broadcast.token_refresh_metrics)
        if self._scheduler is not None:
            sched = self._scheduler.health()
            if isinstance(sched, dict):
                metrics["scheduler_restarts"] = int(sched.get("restart_count", 0))
        return metrics

    # ── Lifecycle ──────────────────────────────────────────────────────

    def close(self) -> None:
        """Stop the scheduler."""
        if self._scheduler is not None:
            self._scheduler.stop()

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def scheduler(self) -> TokenRefreshScheduler | None:
        return self._scheduler

    @property
    def token_manager(self) -> TokenManager:
        return self._token_manager

    @property
    def broadcast(self) -> TokenBroadcast:
        return self._broadcast

    @property
    def auth(self) -> DhanAuth:
        return self._auth
