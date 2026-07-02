"""Token generation policy — validate before generate."""

from __future__ import annotations

from brokers.common.auth.token import TokenState


def should_generate_token(
    state: TokenState | None,
    *,
    broker_rejected: bool = False,
    allow_proactive: bool = False,
    buffer_seconds: float = 0,
) -> bool:
    """Return True when a new token must be generated.

    Generation is allowed only when the token is missing, expired, broker-rejected,
    or (optionally) within a proactive refresh buffer. Dhan TOTP callers should
    keep ``allow_proactive=False`` so valid working tokens are never regenerated.
    """
    if broker_rejected:
        return True
    if state is None or not state.access_token:
        return True
    if not state.is_valid():
        return True
    return bool(allow_proactive and state.refresh_recommended(buffer_seconds))
