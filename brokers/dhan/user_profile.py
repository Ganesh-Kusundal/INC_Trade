"""User Profile adapter — fetch user profile and configurations."""

from __future__ import annotations

import logging

from brokers.dhan.domain import UserProfile
from brokers.dhan.exceptions import UserProfileError
from brokers.dhan.http_client import DhanHttpClient

logger = logging.getLogger(__name__)


class UserProfileAdapter:
    """Adapter for Dhan User Profile API (v2.2+)."""

    def __init__(self, client: DhanHttpClient):
        self._client = client

    def get_profile(self) -> UserProfile:
        """Get user profile information.

        Returns:
            UserProfile with user details and configurations

        Raises:
            UserProfileError: If API call fails
        """
        try:
            data = self._client.get("/userprofile")
        except Exception as exc:
            raise UserProfileError(f"Failed to fetch user profile: {exc}") from exc

        profile_data = data.get("data", data)
        profile = self._parse_profile(profile_data)

        logger.info(
            "user_profile_fetched",
            extra={
                "token_valid": profile.token_valid,
                "active_segments_count": len(profile.active_segments),
                "ddpi_status": profile.ddpi_status,
            },
        )
        return profile

    def _parse_profile(self, data: dict) -> UserProfile:
        """Parse user profile from API response."""
        return UserProfile(
            token_valid=data.get("tokenValid", False),
            active_segments=data.get("activeSegments", []),
            ddpi_status=data.get("ddpiStatus", ""),
            mtf_enabled=data.get("mtfEnabled", False),
            data_api_subscription=data.get("dataApiSubscription", ""),
            user_configurations=data.get("userConfigurations", {}),
        )
