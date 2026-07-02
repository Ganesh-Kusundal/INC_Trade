"""Cached singleton for the central AppConfig.

Usage::

    from config.defaults import get_config, reset_config

    cfg = get_config()       # loads once, cached
    reset_config()           # clear cache (for tests)
"""

from __future__ import annotations

from config.schema import AppConfig

DEFAULT_CONFIG: dict[str, object] = {
    "app_env": "dev",
    "log_level": "INFO",
    "debug": False,
    "redis_url": None,
    "api_host": "127.0.0.1",
    "api_port": 8080,
    "observability_port": 8765,
    "cors_origins": ["http://localhost:5173"],
    "rate_limit_max_requests": 0,
    "rate_limit_window_seconds": 60.0,
}

_cached: AppConfig | None = None


def get_config() -> AppConfig:
    """Return the cached AppConfig, loading from env on first call."""
    global _cached
    if _cached is None:
        _cached = AppConfig.from_env()
    return _cached


def reset_config() -> None:
    """Clear the cached config so the next get_config() reloads from env."""
    global _cached
    _cached = None
