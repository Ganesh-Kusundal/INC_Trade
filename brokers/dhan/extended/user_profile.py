"""Dhan user profile — retrieve user account profile data.

API: GET /userprofile — get user profile
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class UserProfile:
    """Dhan user profile data."""

    client_id: str = ""
    token_valid: bool = False
    active_segments: list[str] = field(default_factory=list)
    ddpi_status: str = ""
    mtm_status: str = ""
    p_o_a_status: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserProfile:
        segments = data.get("activeSegments", [])
        seg_list: list[str] = list(segments) if isinstance(segments, list) else []
        return cls(
            client_id=str(data.get("dhanClientId", "")),
            token_valid=bool(data.get("tokenValid", False)),
            active_segments=seg_list,
            ddpi_status=str(data.get("ddpiStatus", "")),
            mtm_status=str(data.get("mtmStatus", "")),
            p_o_a_status=str(data.get("poaStatus", "")),
        )


class DhanUserProfile:
    """User profile retrieval for Dhan.

    Usage::

        profile = DhanUserProfile(client=dhan_client)
        user = profile.get()
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get(self) -> UserProfile:
        """Get the current user profile."""
        data = self._client.get("/userprofile")
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return UserProfile.from_dict(raw if isinstance(raw, dict) else {})


__all__ = ["DhanUserProfile", "UserProfile"]
