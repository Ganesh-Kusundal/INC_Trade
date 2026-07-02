"""Authentication and token lifecycle constants.

All constants governing token refresh intervals, buffers, and cooldown periods
for broker authentication systems.
"""

from __future__ import annotations

# ── Auth / token lifecycle ─────────────────────────────────────────────────

#: Recommended buffer before a token is "about to expire" (seconds).
#: ``TokenState.refresh_recommended`` and ``AuthManager.ensure_valid``
#: both default to this.
TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS: float = 300.0

#: Actual buffer used by the Dhan ``TokenRefreshScheduler`` (seconds).
#: Larger than the common default because Dhan access tokens have a
#: 24h lifetime and we want to refresh well before the next market open.
#: **REQUIRES DOMAIN VERIFICATION** — must match Dhan token-policy docs.
DHAN_TOKEN_REFRESH_BUFFER_SECONDS: float = 600.0

#: Dhan token-scheduler poll interval (seconds).
DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS: int = 20 * 60  # 1_200

#: Dhan access-token lifetime (seconds).
DHAN_TOKEN_LIFETIME_SECONDS: int = 24 * 60 * 60  # 86_400

#: Seconds a successful refresh must hold before another refresh is allowed.
#: Prevents token-storm on flaky networks. Used by Dhan http_client.
DHAN_REFRESH_COOLDOWN_SECONDS: int = 60

#: Clock-skew tolerance for token expiry (seconds).
TOKEN_CLOCK_SKEW_SECONDS: float = 30.0

__all__ = [
    "DHAN_REFRESH_COOLDOWN_SECONDS",
    "DHAN_TOKEN_LIFETIME_SECONDS",
    "DHAN_TOKEN_REFRESH_BUFFER_SECONDS",
    "DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS",
    "TOKEN_CLOCK_SKEW_SECONDS",
    "TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS",
]
