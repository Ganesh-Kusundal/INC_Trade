"""Token metadata — provider-agnostic token representation."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class TokenInfo:
    """Token metadata."""

    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0  # Unix timestamp
    issued_at: float = 0.0
    token_type: str = "Bearer"
    scope: str = ""

    @property
    def is_expired(self) -> bool:
        if self.expires_at <= 0:
            return False
        return time.time() >= self.expires_at

    @property
    def expires_in(self) -> float:
        """Seconds until expiry. Negative if already expired."""
        if self.expires_at <= 0:
            return float("inf")
        return self.expires_at - time.time()

    @property
    def needs_refresh(self) -> bool:
        """Whether token should be refreshed (within 5 min of expiry)."""
        if self.expires_at <= 0:
            return False
        return self.expires_in < 300  # 5 minutes
