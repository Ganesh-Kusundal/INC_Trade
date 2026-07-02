"""Production environment profile.

Maximum strictness, real brokers only, no debug endpoints,
encryption required.
"""

from __future__ import annotations

from config.profiles.base import BaseProfile


class ProdProfile(BaseProfile):
    """Production environment configuration."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "prod"
        self._log_level = "WARNING"
        self._debug_enabled = False
        self._mock_brokers_allowed = False
        self._strict_validation = True
        self._allow_live_orders_by_default = False
        self._encryption_required = True
        self._api_auth_required = True
        self._rate_limit_enabled = True
        self._rate_limit_per_minute = 60
        self._cors_origins = [
            "https://app.tradexv2.com",
        ]
        self._observability_enabled = True
        self._metrics_endpoint = None  # Set via env var in production
