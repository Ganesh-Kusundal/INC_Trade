"""Auth factory — token store and auth component creation."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from brokers_core.ports.token_store import TokenStorePort

from brokers_core.adapters.dhan.auth import DhanAuth


class AuthComponents(NamedTuple):
    """Auth-related components."""

    auth: DhanAuth
    token_store: TokenStorePort | None


def create_auth(
    access_token: str | None = None,
    client_id: str | None = None,
    pin: str | None = None,
    totp_secret: str | None = None,
    token_store: TokenStorePort | None = None,
    token_state_dir: Path | None = None,
) -> AuthComponents:
    """Create auth and token store components.

    Args:
        access_token: Pre-configured access token (skips TOTP if provided).
        client_id: Dhan client ID.
        pin: PIN for TOTP login.
        totp_secret: Secret for TOTP login.
        token_store: Optional externally-provided token store.
        token_state_dir: Directory for JSON token state persistence.

    Returns:
        AuthComponents namedtuple with auth and token_store.
    """
    if token_store is None and token_state_dir:
        token_state_dir.mkdir(parents=True, exist_ok=True)
        from brokers_core.infrastructure.storage.token_store import JsonTokenStateStore

        token_store = JsonTokenStateStore(token_state_dir / "dhan-token-state.json")

    auth = DhanAuth(
        access_token=access_token,
        client_id=client_id,
        pin=pin,
        totp_secret=totp_secret,
        token_store=token_store,
    )

    return AuthComponents(auth=auth, token_store=token_store)
