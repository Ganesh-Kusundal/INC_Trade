"""Upstox auth — token management."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class UpstoxAuth:
    def __init__(self, access_token: str):
        self._access_token = access_token

    def get_token(self) -> str:
        return self._access_token

    def refresh_token(self) -> str:
        logger.warning("upstox_token_refresh_requires_oauth_flow")
        return self._access_token

    def is_authenticated(self) -> bool:
        return bool(self._access_token)
