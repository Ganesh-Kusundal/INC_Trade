"""BrokerFactory — creates configured BrokerGateway instances with AuthManager.

Implements BrokerProviderFactory for polymorphic factory pattern.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from brokers.common.auth import AuthManager, JsonTokenStateStore, TokenSource, TokenState
from brokers.common.factory import BrokerProviderFactory
from brokers.common.gateway import MarketDataGateway
from brokers.dhan.account_registry import AccountConnectionRegistry
from brokers.dhan.connection import DhanConnection
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.settings import DhanConnectionSettings, DhanSettingsLoader
from brokers.dhan.token_scheduler import TokenRefreshScheduler

logger = logging.getLogger(__name__)


class BrokerFactory(BrokerProviderFactory):
    def create(
        self,
        *,
        env_path: Path | None = None,
        load_instruments: bool = True,
        event_bus: Any | None = None,
        risk_manager: Any | None = None,
        lifecycle: Any | None = None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
        reconciliation_service: object | None = None,
    ) -> MarketDataGateway:
        settings = DhanSettingsLoader.from_env(env_path=env_path)
        cid = settings.client_id
        resolved_env = env_path or Path(".env.local")

        return AccountConnectionRegistry.get_or_create(
            "dhan",
            cid,
            lambda: self._build_gateway(
                settings=settings,
                env_path=resolved_env,
                load_instruments=load_instruments,
                event_bus=event_bus,
                risk_manager=risk_manager,
                lifecycle=lifecycle,
                backfill_callback=backfill_callback,
                reconciliation_service=reconciliation_service,
            ),
        )

    def _build_gateway(
        self,
        *,
        settings: DhanConnectionSettings,
        env_path: Path,
        load_instruments: bool,
        event_bus: Any | None,
        risk_manager: Any | None,
        lifecycle: Any | None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None,
        reconciliation_service: object | None,
    ) -> MarketDataGateway:
        cid = settings.client_id

        # ── Auth & token ───────────────────────────────────────────
        auth, token = self._create_auth(settings, env_path)

        # ── Per-instance refresh lock shared between the HTTP 401 handler and
        # the scheduler.  Created here (the natural owner) rather than inside
        # a helper so it does not need to be threaded through return values.
        refresh_lock = threading.Lock()

        # ── HTTP client ────────────────────────────────────────────
        client = self._create_http_client(
            settings, auth, cid, token, env_path, refresh_lock
        )

        # ── Connection + Gateway ───────────────────────────────────
        gateway = self._create_connection_and_gateway(
            client,
            auth,
            settings,
            event_bus,
            risk_manager,
            reconciliation_service,
            backfill_callback,
            lifecycle,
        )

        # Register extension factories so brokers.common can find them

        if load_instruments:
            gateway.load_instruments()

        # ── WebSocket auto-wiring ──────────────────────────────────
        self._wire_websocket_services(gateway, client, token, lifecycle, event_bus)

        # ── Token refresh scheduler ────────────────────────────────
        self._setup_token_refresh_scheduler(
            gateway,
            auth,
            client,
            settings,
            env_path,
            lifecycle,
            refresh_lock,
        )

        # ── Health check registration ──────────────────────────────
        from brokers.common.observability.health_check import register_broker_health_check

        register_broker_health_check("dhan", gateway)

        return gateway

    # ── Bootstrapper helpers ──────────────────────────────────────────────

    def _create_auth(
        self,
        settings: DhanConnectionSettings,
        env_file: Path,
    ) -> tuple[AuthManager, str]:
        """Create AuthManager and acquire an access token."""
        cid = settings.client_id
        token_state_dir = settings.resolved_token_state_dir
        token_state_dir.mkdir(parents=True, exist_ok=True)
        token_store = JsonTokenStateStore(token_state_dir / "dhan-token-state.json")

        def _generate_token() -> str | None:
            return _generate_totp_token(settings)

        auth = AuthManager(
            client_id=cid,
            token_store=token_store,
            token_source=TokenSource.TOTP,
            on_acquire=_generate_token,
            on_refresh=_generate_token,
            token_lifetime_seconds=settings.token_lifetime_seconds,
        )

        token = settings.access_token
        if not token:
            state = auth.acquire()
            if not state or not state.is_valid():
                fresh = _generate_totp_token(settings)
                if fresh:
                    from datetime import datetime

                    now = datetime.now()
                    state = TokenState(
                        access_token=fresh,
                        source=TokenSource.TOTP,
                        issued_at=now,
                        expires_at=_next_token_expiry(now, settings.token_lifetime_seconds),
                    )
                    auth._state = state
                    if auth._store:
                        auth._store.save(state)
                else:
                    state = None

            if not state or not state.access_token:
                from brokers.dhan.exceptions import ConfigurationError

                raise ConfigurationError("DHAN_ACCESS_TOKEN not configured and TOTP refresh failed")

            token = state.access_token
            if env_file.exists():
                _update_env_token(env_file, token)

        return auth, token

    def _create_http_client(
        self,
        settings: DhanConnectionSettings,
        auth: AuthManager,
        cid: str,
        token: str,
        env_file: Path,
        refresh_lock: threading.Lock,
    ) -> DhanHttpClient:
        """Create DhanHttpClient with standardized resilience patterns.

        Uses the Dhan resilience package for:
          - Per-category circuit breakers (orders, market_data, portfolio, admin)
          - Rate limiter with token bucket algorithm
          - Retry executor integration (via common resilience module)

        Maintains backward compatibility with existing read/write/admin
        circuit breaker naming used by the HTTP client and connection.
        """
        from brokers.dhan.config import DhanResilienceConfig, DEFAULT_CONFIG
        from brokers.dhan.config_loader import DhanConfigLoader
        from brokers.dhan.resilience import (
            create_circuit_breakers,
            create_rate_limiter,
        )

        # Load resilience configuration from settings or use defaults
        resilience_config = settings.resilience_config
        if resilience_config is None:
            # Try to load from environment
            resilience_config = DhanConfigLoader.load_from_environment()
            if resilience_config.to_dict() == DEFAULT_CONFIG.to_dict():
                # No custom config, use defaults
                resilience_config = DEFAULT_CONFIG

        # Create standardized circuit breakers with config-based thresholds
        # If resilience_config has custom circuit breaker settings, use them
        if resilience_config.circuit_breaker.orders_failure_threshold != 3 or \
           resilience_config.circuit_breaker.default_failure_threshold != 5:
            # Use custom thresholds
            from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
            cbs = {
                "orders": CircuitBreaker(
                    "dhan-orders",
                    CircuitBreakerConfig(
                        failure_threshold=resilience_config.circuit_breaker.orders_failure_threshold,
                        success_threshold=resilience_config.circuit_breaker.success_threshold,
                        open_duration_ms=resilience_config.circuit_breaker.recovery_timeout_ms,
                    ),
                ),
                "market_data": CircuitBreaker(
                    "dhan-market-data",
                    CircuitBreakerConfig(
                        failure_threshold=resilience_config.circuit_breaker.default_failure_threshold,
                        success_threshold=resilience_config.circuit_breaker.success_threshold,
                        open_duration_ms=resilience_config.circuit_breaker.recovery_timeout_ms,
                    ),
                ),
                "portfolio": CircuitBreaker(
                    "dhan-portfolio",
                    CircuitBreakerConfig(
                        failure_threshold=resilience_config.circuit_breaker.default_failure_threshold,
                        success_threshold=resilience_config.circuit_breaker.success_threshold,
                        open_duration_ms=resilience_config.circuit_breaker.recovery_timeout_ms,
                    ),
                ),
                "admin": CircuitBreaker(
                    "dhan-admin",
                    CircuitBreakerConfig(
                        failure_threshold=resilience_config.circuit_breaker.default_failure_threshold,
                        success_threshold=resilience_config.circuit_breaker.success_threshold,
                        open_duration_ms=resilience_config.circuit_breaker.recovery_timeout_ms,
                    ),
                ),
            }
        else:
            # Use default circuit breakers
            cbs = create_circuit_breakers()

        # Map new categories to legacy names for backward compat:
        #   orders -> write_circuit_breaker
        #   market_data -> read_circuit_breaker
        #   portfolio + admin -> admin_circuit_breaker
        cb_orders = cbs["orders"]
        cb_market_data = cbs["market_data"]
        cbs["portfolio"]
        cb_admin = cbs["admin"]

        # Create rate limiter with config-based settings
        # Note: create_rate_limiter() uses hardcoded values from resilience/rate_limiter.py
        # For now, we'll use the default rate limiter
        rate_limiter = create_rate_limiter()

        return DhanHttpClient(
            client_id=cid,
            access_token=token,
            base_url=settings.base_url,
            timeout=settings.http_timeout,
            enable_retry=settings.enable_retry,
            token_refresh_fn=lambda: _refresh_via_auth(auth, env_file, refresh_lock),
            # Pass resilience configuration
            config=resilience_config,
            # Legacy naming for backward compatibility with http_client.py
            read_circuit_breaker=cb_market_data,
            write_circuit_breaker=cb_orders,
            admin_circuit_breaker=cb_admin,
            # Store for observability
            _rate_limiter=rate_limiter,
            _circuit_breakers=cbs,
        )

    def _create_connection_and_gateway(
        self,
        client: DhanHttpClient,
        auth: AuthManager,
        settings: DhanConnectionSettings,
        event_bus: Any | None,
        risk_manager: Any | None,
        reconciliation_service: object | None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None,
        lifecycle: Any | None,
    ) -> BrokerGateway:
        """Create DhanConnection + BrokerGateway."""
        connection = DhanConnection(
            client=client,
            event_bus=event_bus,
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
            lifecycle=lifecycle,
            allow_live_orders=settings.allow_live_orders,
        )
        connection._auth = auth  # Store auth manager on connection
        from brokers.dhan.session_manager import DhanSessionManager

        connection._session_manager = DhanSessionManager(connection, auth)
        return BrokerGateway(connection)

    def _wire_websocket_services(
        self,
        gateway: BrokerGateway,
        client: DhanHttpClient,
        token: str,
        lifecycle: Any | None,
        event_bus: Any | None,
    ) -> None:
        """Auto-create and register WebSocket services when lifecycle is provided."""
        if lifecycle is None or event_bus is None:
            return

        def access_token_fn():
            return client.access_token

        gateway._conn.create_market_feed(
            access_token=token,
            instruments=[],
            access_token_fn=access_token_fn,
        )
        gateway._conn.create_order_stream(
            access_token=token,
            access_token_fn=access_token_fn,
        )

        logger.info(
            "websocket_wired",
            extra={
                "market_feed": "dhan.market_feed",
                "order_stream": "dhan.order_stream",
                "depth_20": "on_demand",
                "depth_200": "on_demand",
            },
        )

    def _setup_token_refresh_scheduler(
        self,
        gateway: BrokerGateway,
        auth: AuthManager,
        client: DhanHttpClient,
        settings: DhanConnectionSettings,
        env_file: Path,
        lifecycle: Any | None,
        refresh_lock: threading.Lock,
    ) -> None:
        """Create and register the token refresh scheduler."""

        def _on_token_refresh(new_token: str) -> None:
            client.update_token(new_token)
            if env_file.exists():
                _update_env_token(env_file, new_token)
            delivered = gateway._conn.broadcast_token(new_token)
            logger.info(
                "dhan_token_refreshed",
                extra={
                    "token_suffix": new_token[-6:] if new_token else "",
                    "receivers": delivered,
                },
            )

        scheduler = TokenRefreshScheduler(
            auth=auth,
            interval_seconds=settings.scheduler_interval_seconds,
            buffer_seconds=settings.refresh_buffer_seconds,
            refresh_lock=refresh_lock,
            on_refresh=_on_token_refresh,
        )
        if lifecycle is not None:
            lifecycle.register(scheduler)
            gateway._conn.token_scheduler = scheduler
        else:
            import atexit

            scheduler.start()
            gateway._conn.token_scheduler = scheduler
            atexit.register(scheduler.stop)
            logger.warning(
                "token_scheduler_started_without_lifecycle",
                extra={"hint": "registered atexit stop handler"},
            )


def _refresh_via_auth(
    auth: AuthManager,
    env_file: Path,
    refresh_lock: threading.Lock,
) -> str | None:
    """Refresh token via AuthManager and persist to .env.local.

    Uses the lock shared with the scheduler to prevent concurrent
    refresh from the HTTP 401 handler and the background scheduler.
    If a refresh is already in progress, waits up to 5 seconds for it
    to complete rather than silently skipping — the in-flight refresh
    may produce a valid token.
    """
    acquired = refresh_lock.acquire(timeout=5.0)
    if not acquired:
        logger.debug("Token refresh timed out waiting for in-flight refresh")
        return None
    try:
        state = auth.force_refresh()
        if state and state.access_token:
            _update_env_token(env_file, state.access_token)
            return state.access_token
        state = auth.acquire()
        if state and state.access_token:
            _update_env_token(env_file, state.access_token)
            return state.access_token
        return None
    finally:
        refresh_lock.release()


def _next_token_expiry(now: Any, lifetime_seconds: int) -> Any:
    """Compute token expiry aligned to the next trading session end.

    Dhan tokens expire at the start of the next trading day (~06:00 IST /
    00:30 UTC).  If the current time is before today's 00:30 UTC, the
    expiry is today's 00:30; otherwise tomorrow's.  Falls back to a
    simple timedelta if the calculation fails.
    """
    from datetime import datetime, timedelta, timezone

    try:
        utc_now = datetime.now(timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
        session_end_today = utc_now.replace(hour=0, minute=30, second=0, microsecond=0)
        if utc_now < session_end_today:
            return session_end_today
        return session_end_today + timedelta(days=1)
    except (ValueError, TypeError, AttributeError) as exc:
        logger.warning("token_expiry_fallback", extra={"error": str(exc)})
        return now + timedelta(seconds=lifetime_seconds)


def _generate_totp_token(settings: DhanConnectionSettings | None = None) -> str | None:
    """Generate a fresh access token via TOTP. Returns None on failure.

    Raises RuntimeError with descriptive message if Dhan's rate limit
    is hit ("Token can be generated once every 2 minutes").

    Uses secrets from *settings* if provided, otherwise falls back to
    environment variables ``DHAN_PIN`` / ``DHAN_TOTP_SECRET``.
    """
    if settings and settings.has_totp:
        pin = settings.pin
        totp_secret = settings.totp_secret
        token_url = settings.generate_token_url
    else:
        pin = _read_secret("DHAN_PIN", "DHAN_PIN_FILE")
        totp_secret = _read_secret("DHAN_TOTP_SECRET", "DHAN_TOTP_SECRET_FILE")
        from brokers.dhan.settings import _GENERATE_TOKEN_URL

        token_url = _GENERATE_TOKEN_URL
    if not pin or not totp_secret:
        return None
    try:
        import pyotp
        import requests as _requests

        totp_code = pyotp.TOTP(totp_secret).now()
        client_id = settings.client_id if settings else os.environ.get("DHAN_CLIENT_ID", "")
        params = {"dhanClientId": client_id, "pin": pin, "totp": totp_code}
        url = f"{token_url}?{urlencode(params)}"
        resp = _requests.post(url, timeout=15)

        # Parse response body regardless of status code
        try:
            body = resp.json()
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("totp_response_parse_failed", extra={"error": str(exc)})
            body = {}

        # Check for rate limit error (even on HTTP 200)
        message = body.get("message", "")
        status = body.get("status", "")
        if "once every 2 minutes" in message or status == "error":
            error_msg = f"Dhan token rate limit: {message}"
            logger.warning(error_msg)
            raise RuntimeError(error_msg)

        if resp.status_code != 200:
            logger.warning("TOTP token generation failed: HTTP %d", resp.status_code)
            return None

        data = body.get("data", body)
        result: str = data.get("accessToken") or data.get("access_token") or ""
        return result or None
    except RuntimeError:
        # Re-raise rate limit errors
        raise
    except Exception as exc:
        logger.warning("TOTP token generation failed: %s", exc)
        return None


from brokers.dhan.secret_utils import read_secret as _read_secret


def _update_env_token(env_path: Path, token: str) -> None:
    """Update DHAN_ACCESS_TOKEN in the env file atomically.

    Uses ``fcntl.flock`` for cross-process exclusion and a temp-file +
    ``os.replace`` so readers never see a partially-written file. If the
    token key is missing, it is appended while preserving all other keys,
    comments, and blank lines.
    """
    if not env_path.exists():
        return

    try:
        import fcntl
    except Exception as exc:  # pragma: no cover - non-Unix fallback
        logger.warning("fcntl unavailable, env update unprotected: %s", exc)
        return

    fd: int | None = None
    tmp_path = env_path.with_suffix(f"{env_path.suffix}.tmp")
    try:
        # Hold an exclusive lock on the env file while we read and replace it.
        fd = os.open(str(env_path), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)

        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as fh:
            content = fh.read()

        lines = content.splitlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("DHAN_ACCESS_TOKEN="):
                lines[i] = f"DHAN_ACCESS_TOKEN={token}"
                updated = True
                break
        if not updated:
            # Preserve a trailing blank line when appending if the file ends
            # without a newline; otherwise just append the new key.
            if lines and not content.endswith("\n"):
                lines.append("")
            lines.append(f"DHAN_ACCESS_TOKEN={token}")

        new_content = "\n".join(lines)
        if not new_content.endswith("\n"):
            new_content += "\n"

        tmp_path.write_text(new_content, encoding="utf-8")
        # fsync temp file contents before the atomic rename.
        with open(tmp_path, "rb") as tmp_fh:
            os.fsync(tmp_fh.fileno())
        # fsync the directory so the rename is durable.
        dir_fd = os.open(env_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        os.replace(tmp_path, env_path)
    except PermissionError:
        # Env file is read-only (e.g. credentials managed externally). Persist
        # the new token via the JsonTokenStateStore instead and continue.
        logger.info("Env file is read-only; token persisted to state store only.")
    except Exception as exc:
        logger.warning("Failed to update env token: %s", exc)
        if tmp_path.exists():
            tmp_path.unlink()
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception as exc:
                logger.debug("file_unlock_failed: %s", exc)
            try:
                os.close(fd)
            except Exception as exc:
                logger.debug("file_close_failed: %s", exc)
