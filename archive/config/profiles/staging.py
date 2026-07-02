"""Staging environment profile.

Strict validation, real brokers, debug endpoints enabled for testing.
"""

from __future__ import annotations

from config.profiles.base import BaseProfile


class StagingProfile(BaseProfile):
    """Staging environment configuration."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "staging"
        self._log_level = "INFO"
        self._debug_enabled = True
        self._mock_brokers_allowed = False
        self._strict_validation = True
        self._allow_live_orders_by_default = False
        self._encryption_required = True
        self._api_auth_required = True
        self._rate_limit_enabled = True
        self._rate_limit_per_minute = 120
        self._cors_origins = [
            "https://staging.tradexv2.com",
            "http://localhost:5173",  # Allow local dev against staging
        ]
        self._observability_enabled = True
        self._metrics_endpoint = "http://localhost:9090/metrics"
