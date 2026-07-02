"""Dhan auth — token management."""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


class DhanAuth:
    def __init__(self, access_token: str, client_id: str):
        self._access_token = access_token
        self._client_id = client_id

    def get_token(self) -> str:
        return self._access_token

    def refresh_token(self) -> str:
        logger.warning("dhan_token_refresh_not_supported")
        return self._access_token

    def is_authenticated(self) -> bool:
        return bool(self._access_token)
