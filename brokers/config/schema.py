"""Configuration schema — typed defaults for all environment variables.

Provides frozen dataclasses for Dhan, Upstox, API, and Trading config.
All fields map to environment variables with broker-specific prefixes.

Usage::

    from brokers.config.schema import load_dhan_config, load_upstox_config

    dhan = load_dhan_config()
    upstox = load_upstox_config()
"""

from __future__ import annotations

import os
from dataclasses import dataclass


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

    host: str = "127.0.0.1"
    port: int = 8080
    observability_port: int = 8765
    auth_mode: str = "none"
    api_key: str = ""
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)


@dataclass(frozen=True)
class TradingConfig:
    """Trading runtime configuration."""

    orchestrator_dry_run: bool = True
    orchestrator_min_confidence: float = 0.7
    enable_intelligent_gateway: bool = False
    skip_parity_gate: bool = False
    smart_routing: bool = True
    primary_broker: str = "dhan"


@dataclass(frozen=True)
class AppConfig:
    """Central application configuration with env-var loading."""

    app_env: str = "dev"
    log_level: str = "INFO"
    debug: bool = False
    redis_url: str | None = None

    @classmethod
    def from_env(cls) -> AppConfig:
        """Load configuration from environment variables."""
        debug_raw = os.environ.get("TRADEX_DEBUG", os.environ.get("TRADEXV2_DEBUG", ""))
        return cls(
            app_env=os.environ.get("TRADEX_APP_ENV", os.environ.get("APP_ENV", "dev")),
            log_level=os.environ.get("TRADEX_LOG_LEVEL", os.environ.get("XV2_LOG_LEVEL", "INFO")),
            debug=debug_raw.lower() in ("1", "true", "yes") if debug_raw else False,
            redis_url=os.environ.get("TRADEX_REDIS_URL", os.environ.get("REDIS_URL")) or None,
        )


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
        sandbox_rest_base_url=os.environ.get("DHAN_SANDBOX_REST_BASE_URL", "https://sandbox.dhan.co/v2"),
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
        token_state_file=os.environ.get("UPSTOX_TOKEN_STATE_FILE", "runtime/upstox-token-state.json"),
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
    cors_raw = os.environ.get("TRADEX_CORS_ORIGINS", "")
    cors = tuple(o.strip() for o in cors_raw.split(",") if o.strip()) if cors_raw else ()
    return ApiConfig(
        host=os.environ.get("TRADEX_API_HOST", os.environ.get("API_HOST", "127.0.0.1")),
        port=_get_int("TRADEX_API_PORT", 8080),
        observability_port=_get_int("TRADEX_OBSERVABILITY_PORT", 8765),
        auth_mode=os.environ.get("AUTH_MODE", "none"),
        api_key=os.environ.get("API_KEY", ""),
        cors_origins=cors or ("http://localhost:5173",),
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


__all__ = [
    "ApiConfig",
    "AppConfig",
    "DhanConfig",
    "TradingConfig",
    "UpstoxConfig",
    "load_api_config",
    "load_dhan_config",
    "load_trading_config",
    "load_upstox_config",
]
