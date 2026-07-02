"""Development environment profile.

Relaxed validation, verbose logging, mock brokers allowed,
debug endpoints enabled.
"""

from __future__ import annotations

from config.profiles.base import BaseProfile


class DevProfile(BaseProfile):
    """Development environment configuration."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "dev"
        self._log_level = "DEBUG"
        self._debug_enabled = True
        self._mock_brokers_allowed = True
        self._strict_validation = False
        self._allow_live_orders_by_default = False
        self._encryption_required = False
        self._api_auth_required = False
        self._rate_limit_enabled = False
        self._cors_origins = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
