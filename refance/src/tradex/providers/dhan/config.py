"""Dhan-specific configuration.

All Dhan configuration lives here — never in the core framework.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from tradex.core.config import ProviderConfig, RateLimitConfig


@dataclass
class DhanConfig(ProviderConfig):
    """Dhan broker configuration."""

    name: str = "dhan"
    client_id: str = ""
    access_token: str = ""
    base_url: str = "https://api.dhan.co"
    data_url: str = "https://api.dhan.co"
    ws_url: str = "wss://stream.dhan.co"
    instrument_master_url: str = "https://images.dhan.co/api-data/api-scrip-master.csv"

    def __post_init__(self) -> None:
        # Load from environment if not provided
        if not self.client_id:
            self.client_id = os.environ.get("DHAN_CLIENT_ID", "")
        if not self.access_token:
            self.access_token = os.environ.get("DHAN_ACCESS_TOKEN", "")

        # Validate required credentials
        if not self.client_id:
            from tradex.core.errors import ConfigurationError

            raise ConfigurationError(
                "Dhan client_id required. Provide via constructor or DHAN_CLIENT_ID env var.",
                code="CONFIG_ERROR",
            )
        if not self.access_token:
            from tradex.core.errors import ConfigurationError

            raise ConfigurationError(
                "Dhan access_token required. Provide via constructor or DHAN_ACCESS_TOKEN env var.",
                code="CONFIG_ERROR",
            )

        # Set Dhan-specific rate limits
        if not self.rate_limits:
            self.rate_limits = {
                "order": RateLimitConfig(
                    per_second=10, per_minute=250, per_hour=1000, per_day=7000, burst=10
                ),
                "data": RateLimitConfig(
                    per_second=5, per_minute=300, per_hour=18000, per_day=100000, burst=5
                ),
                "quote": RateLimitConfig(
                    per_second=1, per_minute=60, per_hour=3600, per_day=86400, burst=1
                ),
                "non_trading": RateLimitConfig(
                    per_second=20, per_minute=1200, per_hour=72000, per_day=86400, burst=20
                ),
            }
