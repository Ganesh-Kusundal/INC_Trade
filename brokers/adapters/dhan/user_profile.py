"""Dhan User Profile adapter."""

from __future__ import annotations

import logging

from brokers.ports.http_client_port import HttpClientPort

logger = logging.getLogger(__name__)


class DhanUserProfile:
    """User Profile adapter for Dhan."""

    def __init__(self, client: HttpClientPort) -> None:
        self._client = client

    def get_profile(self) -> dict:
        """Fetch user profile information."""
        logger.info("fetching_user_profile")
        return self._client.get("/profile")

    def update_profile(self, data: dict) -> dict:
        """Update user profile information."""
        logger.info("updating_user_profile")
        return self._client.put("/profile", json=data)
