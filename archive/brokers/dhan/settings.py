"""Dhan connection settings — dataclass + loader, mirroring UpstoxConnectionSettings pattern.

Centralizes all Dhan broker configuration into a single frozen dataclass,
loaded from environment variables or .env files via :class:`DhanSettingsLoader`.

Usage::

    from brokers.dhan.settings import DhanSettingsLoader

    settings = DhanSettingsLoader.from_env(env_path=Path(".env.local"))
    client = DhanHttpClient(
        client_id=settings.client_id,
        access_token=settings.access_token,
        base_url=settings.base_url,
        timeout=settings.http_timeout,
    )
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from brokers.common.settings import BrokerSettings, SettingsLoaderBase
from brokers.dhan.config import DhanResilienceConfig
from domain.constants.auth import (
    DHAN_TOKEN_LIFETIME_SECONDS,
    DHAN_TOKEN_REFRESH_BUFFER_SECONDS,
    DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS,
)
from config.endpoints import Dhan

logger = logging.getLogger(__name__)

DHAN_PREFIX = "DHAN"

# Canonical Dhan endpoints — imported from central registry.
_BASE_URL = Dhan.REST_BASE
_GENERATE_TOKEN_URL = Dhan.GENERATE_TOKEN_URL

# Default lifetimes — imported from domain.constants.auth


@dataclass(frozen=True)
class DhanConnectionSettings(BrokerSettings):
    """Resolved Dhan connection settings.

    Centralised configuration for Dhan broker connections, loaded from
    environment variables (or a .properties file).  All fields have
    sensible defaults so only ``client_id`` is truly required.

    Inherits common fields from :class:`BrokerSettings`:
    ``client_id``, ``access_token``, ``http_timeout``, ``enable_retry``,
    ``pool_connections``, ``pool_maxsize``.
    """

    # Dhan-specific fields
    environment: str = "LIVE"
    base_url: str = _BASE_URL
    pin: str = ""
    totp_secret: str = ""
    token_lifetime_seconds: int = DHAN_TOKEN_LIFETIME_SECONDS
    scheduler_interval_seconds: int = DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS
    refresh_buffer_seconds: int = DHAN_TOKEN_REFRESH_BUFFER_SECONDS
    allow_live_orders: bool = False
    token_state_dir: str = ""
    
    # Resilience configuration
    resilience_config: DhanResilienceConfig | None = None

    # ── Derived properties ────────────────────────────────────────────

    @property
    def resolved_token_state_dir(self) -> Path:
        """Absolute path to the token state directory.

        Uses ``token_state_dir`` if set (via env or constructor), otherwise
        derives an absolute path from the project root so the directory is
        stable regardless of CWD.
        """
        if self.token_state_dir:
            return Path(self.token_state_dir)
        # brokers/dhan/settings.py → brokers/dhan → brokers → project root (Trade_XV2/)
        return Path(__file__).resolve().parents[2] / "runtime"

    @property
    def is_sandbox(self) -> bool:
        """Check if environment is SANDBOX."""
        return self.environment.upper() == "SANDBOX"

    @property
    def is_live(self) -> bool:
        """Check if environment is LIVE."""
        return self.environment.upper() == "LIVE"

    @property
    def has_access_token(self) -> bool:
        return bool(self.access_token)

    @property
    def has_totp(self) -> bool:
        return bool(self.pin) and bool(self.totp_secret)

    @property
    def generate_token_url(self) -> str:
        return _GENERATE_TOKEN_URL


class DhanSettingsLoader(SettingsLoaderBase):
    """Load :class:`DhanConnectionSettings` from env vars or .properties files.

    Mirrors the :class:`brokers.upstox.auth.config.UpstoxSettingsLoader` pattern
    so that every broker factory follows the same configuration lifecycle.

    Inherits env var accessors (``_get``, ``_get_int``, ``_get_float``,
    ``_get_bool``) and value parsers (``_parse_int``, ``_parse_float``,
    ``_parse_bool``) from :class:`SettingsLoaderBase` instead of duplicating them.
    """

    PREFIX = DHAN_PREFIX
    VALID_ENVIRONMENTS = ("LIVE", "SANDBOX")

    @classmethod
    def from_env(
        cls,
        *,
        env_path: Path | None = None,
        prefix: str = PREFIX,
    ) -> DhanConnectionSettings:
        """Load settings from environment variables, optionally seeding from *env_path*.

        Args:
            env_path: Optional path to a ``.env`` file.  If provided it is
                      loaded before reading env vars so the env file acts as
                      a fallback or override (whichever takes precedence in
                      :func:`os.environ`).
            prefix:   Environment variable prefix (default ``DHAN``).

        Returns:
            A frozen :class:`DhanConnectionSettings` instance.
        """
        cls._load_default_env(env_path)

        from config.secrets_manager import SecretsManager

        secrets = SecretsManager()

        # Support SANDBOX environment override
        environment = cls._get(prefix, "ENVIRONMENT", default="LIVE").upper()
        if environment not in cls.VALID_ENVIRONMENTS:
            raise ValueError(
                f"DHAN_ENVIRONMENT must be one of {cls.VALID_ENVIRONMENTS}, got {environment!r}"
            )
        is_sandbox = environment == "SANDBOX"

        client_id = (
            cls._get(prefix, "SANDBOX_CLIENT_ID") if is_sandbox else cls._get(prefix, "CLIENT_ID")
        )
        if not client_id:
            raise ValueError("DHAN_CLIENT_ID is required")

        access_token = (
            cls._get(prefix, "SANDBOX_ACCESS_TOKEN")
            if is_sandbox
            else cls._get(prefix, "ACCESS_TOKEN")
        )

        pin = cls._get(prefix, "PIN", default="") or secrets.get_dhan_pin()
        totp_secret = cls._get(prefix, "TOTP_SECRET", default="") or secrets.get_dhan_totp_secret()

        # Auto-switch base_url for sandbox environment
        if is_sandbox:
            base_url = (
                cls._get(prefix, "SANDBOX_REST_BASE_URL")
                or cls._get(prefix, "BASE_URL")
                or Dhan.sandbox()
            )
        else:
            base_url = cls._get(prefix, "BASE_URL", default=_BASE_URL)

        # Load resilience configuration from environment
        resilience_config = cls._load_resilience_config(prefix, env_path)

        return DhanConnectionSettings(
            client_id=client_id,
            access_token=access_token,
            environment=environment,
            base_url=base_url,
            http_timeout=cls._get_float(prefix, "HTTP_TIMEOUT", default=15.0),
            enable_retry=cls._get_bool(prefix, "ENABLE_RETRY", default=True),
            pool_connections=cls._get_int(prefix, "POOL_CONNECTIONS", default=50),
            pool_maxsize=cls._get_int(prefix, "POOL_MAXSIZE", default=100),
            pin=pin,
            totp_secret=totp_secret,
            token_lifetime_seconds=cls._get_int(
                prefix, "TOKEN_LIFETIME_SECONDS", default=DHAN_TOKEN_LIFETIME_SECONDS
            ),
            scheduler_interval_seconds=cls._get_int(
                prefix, "SCHEDULER_INTERVAL_SECONDS", default=DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS
            ),
            refresh_buffer_seconds=cls._get_int(
                prefix, "REFRESH_BUFFER_SECONDS", default=DHAN_TOKEN_REFRESH_BUFFER_SECONDS
            ),
            allow_live_orders=cls._get_bool(prefix, "ALLOW_LIVE_ORDERS", default=False),
            token_state_dir=cls._get(prefix, "TOKEN_STATE_DIR", default=""),
            resilience_config=resilience_config,
        )

    @classmethod
    def _load_resilience_config(
        cls, prefix: str, env_path: Path | None = None
    ) -> DhanResilienceConfig | None:
        """Load resilience configuration from environment variables.

        Checks for DHAN_RESILIENCE_* environment variables. If none are found,
        returns None to use the default configuration in the HTTP client.

        Args:
            prefix: The broker prefix (e.g., "DHAN").
            env_path: Optional path to .env file.

        Returns:
            DhanResilienceConfig if any resilience env vars are set, else None.
        """
        from brokers.dhan.config_loader import DhanConfigLoader, ENV_PREFIX

        # Check if any resilience env vars are set
        resilience_prefix = ENV_PREFIX
        has_resilience_vars = any(
            key.startswith(resilience_prefix) 
            for key in os.environ.keys()
        )

        if has_resilience_vars:
            return DhanConfigLoader.load_from_environment(resilience_prefix)

        # Check .env file for resilience config
        if env_path and env_path.exists():
            try:
                from brokers.dhan.config_loader import load_from_env_file
                config = load_from_env_file(env_path)
                # Check if config has any non-default values
                if config.to_dict() != DhanResilienceConfig().to_dict():
                    return config
            except Exception:
                pass

        return None

    @classmethod
    def from_dict(cls, values: dict[str, str], *, prefix: str = PREFIX) -> DhanConnectionSettings:
        """Load settings from a flat dictionary (used for testing / .properties)."""

        def _val(key: str) -> str:
            return values.get(f"{prefix}.{key}", "")

        client_id = _val("clientId") or _val("client_id")
        if not client_id:
            raise ValueError("dhan.clientId is required")
        return DhanConnectionSettings(
            client_id=client_id,
            access_token=_val("accessToken") or _val("access_token"),
            base_url=_val("baseUrl") or _val("base_url") or _BASE_URL,
            http_timeout=cls._parse_float(_val("httpTimeout"), 15.0),
            enable_retry=cls._parse_bool(_val("enableRetry"), True),
            pool_connections=cls._parse_int(_val("poolConnections"), 50),
            pool_maxsize=cls._parse_int(_val("poolMaxsize"), 100),
            pin=_val("pin"),
            totp_secret=_val("totpSecret") or _val("totp_secret"),
            token_lifetime_seconds=cls._parse_int(
                _val("tokenLifetimeSeconds"), DHAN_TOKEN_LIFETIME_SECONDS
            ),
            scheduler_interval_seconds=cls._parse_int(
                _val("schedulerIntervalSeconds"), DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS
            ),
            refresh_buffer_seconds=cls._parse_int(
                _val("refreshBufferSeconds"), DHAN_TOKEN_REFRESH_BUFFER_SECONDS
            ),
            allow_live_orders=cls._parse_bool(_val("allowLiveOrders"), False),
        )
