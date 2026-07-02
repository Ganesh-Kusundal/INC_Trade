"""Central configuration schema for TradeXV2.

Defines typed defaults for all environment variables used across the system.
Operators should set values in .env.local; this module provides the schema
and defaults so every consumer has a single source of truth.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class AppConfig(BaseModel):
    """Central application configuration with env-var loading.

    All fields map to environment variables. Use ``AppConfig.from_env()``
    to load from the current environment, or construct directly for testing.
    """

    # ── Core ────────────────────────────────────────────────
    app_env: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"
    debug: bool = False
    redis_url: str | None = None

    # ── API Server ──────────────────────────────────────────
    api_host: str = "127.0.0.1"
    api_port: int = 8080
    observability_port: int = 8765
    cors_origins: list[str] = ["http://localhost:5173"]

    # ── Rate Limiting ───────────────────────────────────────
    rate_limit_max_requests: int = 0
    rate_limit_window_seconds: float = 60.0

    model_config = {"env_prefix": "TRADEX_", "env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid log level '{v}'. Must be one of: {sorted(_VALID_LOG_LEVELS)}"
            )
        return upper

    @field_validator("api_port", "observability_port")
    @classmethod
    def _validate_port(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"Port must be > 0, got {v}")
        return v

    @classmethod
    def from_env(cls) -> AppConfig:
        """Load configuration from environment variables.

        Reads env vars with ``TRADEX_`` prefix first, then falls back to
        legacy names (APP_ENV, XV2_LOG_LEVEL, REDIS_URL, etc.) for backward
        compatibility.
        """
        # Build kwargs from env, preferring TRADEX_ prefixed then legacy
        kwargs: dict[str, object] = {}

        # app_env: TRADEX_APP_ENV → APP_ENV
        kwargs["app_env"] = os.environ.get(
            "TRADEX_APP_ENV", os.environ.get("APP_ENV", "dev")
        )

        # log_level: TRADEX_LOG_LEVEL → XV2_LOG_LEVEL
        kwargs["log_level"] = os.environ.get(
            "TRADEX_LOG_LEVEL", os.environ.get("XV2_LOG_LEVEL", "INFO")
        )

        # debug: TRADEX_DEBUG → TRADEXV2_DEBUG
        debug_raw = os.environ.get(
            "TRADEX_DEBUG", os.environ.get("TRADEXV2_DEBUG", "")
        )
        kwargs["debug"] = debug_raw.lower() in ("1", "true", "yes") if debug_raw else False

        # redis_url: TRADEX_REDIS_URL → REDIS_URL
        kwargs["redis_url"] = os.environ.get(
            "TRADEX_REDIS_URL", os.environ.get("REDIS_URL")
        ) or None

        # api_host: TRADEX_API_HOST → API_HOST
        kwargs["api_host"] = os.environ.get(
            "TRADEX_API_HOST", os.environ.get("API_HOST", "127.0.0.1")
        )

        # api_port: TRADEX_API_PORT → API_PORT
        api_port_raw = os.environ.get(
            "TRADEX_API_PORT", os.environ.get("API_PORT", "8080")
        )
        kwargs["api_port"] = int(api_port_raw)

        # observability_port
        obs_raw = os.environ.get("TRADEX_OBSERVABILITY_PORT", "8765")
        kwargs["observability_port"] = int(obs_raw)

        # cors_origins: comma-separated
        cors_raw = os.environ.get("TRADEX_CORS_ORIGINS", "")
        if cors_raw:
            kwargs["cors_origins"] = [o.strip() for o in cors_raw.split(",") if o.strip()]

        # rate_limit_max_requests
        rl_raw = os.environ.get("TRADEX_RATE_LIMIT_MAX_REQUESTS", "0")
        kwargs["rate_limit_max_requests"] = int(rl_raw)

        # rate_limit_window_seconds
        rw_raw = os.environ.get("TRADEX_RATE_LIMIT_WINDOW_SECONDS", "60.0")
        kwargs["rate_limit_window_seconds"] = float(rw_raw)

        return cls(**kwargs)


@dataclass(frozen=True)
class DhanConfig:
    """Dhan broker configuration."""

    client_id: str = ""
    access_token: str = ""
    environment: str = "LIVE"
    rest_base_url: str = ""
    pin: str = ""
    totp_secret: str = ""
    token_state_file: str = "runtime/dhan-token-state.json"
    refresh_buffer_minutes: int = 10
    allow_live_orders: bool = False

    # Sandbox
    sandbox_client_id: str = ""
    sandbox_access_token: str = ""
    sandbox_environment: str = "SANDBOX"
    sandbox_rest_base_url: str = "https://sandbox.dhan.co/v2"


@dataclass(frozen=True)
class UpstoxConfig:
    """Upstox broker configuration."""

    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""
    analytics_token: str = ""
    environment: str = "LIVE"
    auth_mode: str = "STATIC"
    redirect_uri: str = "http://127.0.0.1:18080/callback"
    token_state_file: str = "runtime/upstox-token-state.json"
    analytics_only: bool = False
    allow_live_orders: bool = False
    mobile: str = ""
    pin: str = ""
    totp_secret: str = ""
    totp_refresh_hour: int = 8
    totp_refresh_minute: int = 0

    # Sandbox
    sandbox_client_id: str = ""
    sandbox_client_secret: str = ""
    sandbox_access_token: str = ""
    sandbox_environment: str = "SANDBOX"


@dataclass(frozen=True)
class ApiConfig:
    """API server configuration."""

    auth_mode: str = "none"
    api_key: str = ""


@dataclass(frozen=True)
class TradingConfig:
    """Trading runtime configuration."""

    orchestrator_dry_run: bool = True
    orchestrator_min_confidence: float = 0.7
    enable_intelligent_gateway: bool = False
    skip_parity_gate: bool = False
    smart_routing: bool = True  # Enable intelligent routing by default
    primary_broker: str = "dhan"


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "")
    if not val:
        return default
    return val.lower() in ("1", "true", "yes")


def _get_int(key: str, default: int = 0) -> int:
    val = os.environ.get(key, "")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_float(key: str, default: float = 0.0) -> float:
    val = os.environ.get(key, "")
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def load_dhan_config() -> DhanConfig:
    """Load Dhan configuration from environment variables."""
    return DhanConfig(
        client_id=os.environ.get("DHAN_CLIENT_ID", ""),
        access_token=os.environ.get("DHAN_ACCESS_TOKEN", ""),
        environment=os.environ.get("DHAN_ENVIRONMENT", "LIVE"),
        rest_base_url=os.environ.get("DHAN_REST_BASE_URL", ""),
        pin=os.environ.get("DHAN_PIN", ""),
        totp_secret=os.environ.get("DHAN_TOTP_SECRET", ""),
        token_state_file=os.environ.get("DHAN_TOKEN_STATE_FILE", "runtime/dhan-token-state.json"),
        refresh_buffer_minutes=_get_int("DHAN_REFRESH_BUFFER_MINUTES", 10),
        allow_live_orders=_get_bool("DHAN_ALLOW_LIVE_ORDERS"),
        sandbox_client_id=os.environ.get("DHAN_SANDBOX_CLIENT_ID", ""),
        sandbox_access_token=os.environ.get("DHAN_SANDBOX_ACCESS_TOKEN", ""),
        sandbox_environment=os.environ.get("DHAN_SANDBOX_ENVIRONMENT", "SANDBOX"),
        sandbox_rest_base_url=os.environ.get(
            "DHAN_SANDBOX_REST_BASE_URL", "https://sandbox.dhan.co/v2"
        ),
    )


def load_upstox_config() -> UpstoxConfig:
    """Load Upstox configuration from environment variables."""
    return UpstoxConfig(
        client_id=os.environ.get("UPSTOX_CLIENT_ID", ""),
        client_secret=os.environ.get("UPSTOX_CLIENT_SECRET", ""),
        access_token=os.environ.get("UPSTOX_ACCESS_TOKEN", ""),
        analytics_token=os.environ.get("UPSTOX_ANALYTICS_TOKEN", ""),
        environment=os.environ.get("UPSTOX_ENVIRONMENT", "LIVE"),
        auth_mode=os.environ.get("UPSTOX_AUTH_MODE", "STATIC"),
        redirect_uri=os.environ.get("UPSTOX_REDIRECT_URI", "http://127.0.0.1:18080/callback"),
        token_state_file=os.environ.get(
            "UPSTOX_TOKEN_STATE_FILE", "runtime/upstox-token-state.json"
        ),
        analytics_only=_get_bool("UPSTOX_ANALYTICS_ONLY"),
        allow_live_orders=_get_bool("UPSTOX_ALLOW_LIVE_ORDERS"),
        mobile=os.environ.get("UPSTOX_MOBILE", ""),
        pin=os.environ.get("UPSTOX_PIN", ""),
        totp_secret=os.environ.get("UPSTOX_TOTP_SECRET", ""),
        totp_refresh_hour=_get_int("UPSTOX_TOTP_REFRESH_HOUR", 8),
        totp_refresh_minute=_get_int("UPSTOX_TOTP_REFRESH_MINUTE", 0),
        sandbox_client_id=os.environ.get("UPSTOX_SANDBOX_CLIENT_ID", ""),
        sandbox_client_secret=os.environ.get("UPSTOX_SANDBOX_CLIENT_SECRET", ""),
        sandbox_access_token=os.environ.get("UPSTOX_SANDBOX_ACCESS_TOKEN", ""),
        sandbox_environment=os.environ.get("UPSTOX_SANDBOX_ENVIRONMENT", "SANDBOX"),
    )


def load_api_config() -> ApiConfig:
    """Load API server configuration from environment variables."""
    return ApiConfig(
        auth_mode=os.environ.get("AUTH_MODE", "none"),
        api_key=os.environ.get("API_KEY", ""),
    )


def load_trading_config() -> TradingConfig:
    """Load trading runtime configuration from environment variables."""
    return TradingConfig(
        orchestrator_dry_run=_get_bool("ORCHESTRATOR_DRY_RUN", True),
        orchestrator_min_confidence=_get_float("ORCHESTRATOR_MIN_CONFIDENCE", 0.7),
        enable_intelligent_gateway=_get_bool("ENABLE_INTELLIGENT_GATEWAY"),
        skip_parity_gate=_get_bool("SKIP_PARITY_GATE"),
        smart_routing=_get_bool("TRADEX_SMART_ROUTING", True),
        primary_broker=os.environ.get("TRADEX_PRIMARY_BROKER", "dhan"),
    )
