"""Client factory — HTTP client and connection manager creation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from brokers_core.infrastructure.lifecycle import LifecycleManager
from brokers_core.ports.token_store import TokenStorePort

from brokers_core.adapters.dhan.auth import DhanAuth
from brokers_core.adapters.dhan.connection_manager import DhanConnectionManager
from brokers_core.adapters.dhan.http_client import create_dhan_http_client


class ClientComponents(NamedTuple):
    """Client-related components."""

    http_client: Any
    connection_manager: DhanConnectionManager


def create_http_client(
    client_id: str,
    access_token: str,
    token_refresh_fn: Any,
) -> Any:
    """Create HTTP client with 401 auto-retry.

    Args:
        client_id: Dhan client ID.
        access_token: Current access token.
        token_refresh_fn: Function to refresh token on 401.

    Returns:
        HTTP client instance.
    """
    return create_dhan_http_client(
        client_id=client_id,
        access_token=access_token,
        token_refresh_fn=token_refresh_fn,
    )


def create_connection_manager(
    auth: DhanAuth,
    client_id: str,
    pin: str | None,
    totp_secret: str | None,
    token_store: TokenStorePort | None,
    env_path: Path | None,
    token_state_dir: Path | None,
    auto_refresh: bool,
    refresh_interval_seconds: int,
    refresh_buffer_seconds: float,
    lifecycle: LifecycleManager | None,
) -> DhanConnectionManager:
    """Create connection manager with token lifecycle.

    Args:
        auth: DhanAuth instance.
        client_id: Dhan client ID.
        pin: PIN for TOTP login.
        totp_secret: Secret for TOTP login.
        token_store: Token store for persistence.
        env_path: Path to .env file for token persistence.
        token_state_dir: Directory for JSON token state persistence.
        auto_refresh: Enable background token refresh scheduler.
        refresh_interval_seconds: How often to check token validity.
        refresh_buffer_seconds: Refresh if token expires within this window.
        lifecycle: Optional lifecycle manager to register scheduler with.

    Returns:
        DhanConnectionManager instance.
    """
    return DhanConnectionManager(
        auth=auth,
        client_id=client_id,
        pin=pin,
        totp_secret=totp_secret,
        token_store=token_store,
        env_path=env_path,
        token_state_dir=token_state_dir,
        auto_refresh=auto_refresh,
        refresh_interval_seconds=refresh_interval_seconds,
        refresh_buffer_seconds=refresh_buffer_seconds,
        lifecycle=lifecycle,
    )


def create_client_components(
    auth: DhanAuth,
    token_store: TokenStorePort | None,
    client_id: str,
    pin: str | None,
    totp_secret: str | None,
    env_path: Path | None,
    token_state_dir: Path | None,
    auto_refresh: bool,
    refresh_interval_seconds: int,
    refresh_buffer_seconds: float,
    lifecycle: LifecycleManager | None,
) -> ClientComponents:
    """Create HTTP client and connection manager.

    Args:
        auth: DhanAuth instance.
        token_store: Token store for persistence.
        client_id: Dhan client ID.
        pin: PIN for TOTP login.
        totp_secret: Secret for TOTP login.
        env_path: Path to .env file for token persistence.
        token_state_dir: Directory for JSON token state persistence.
        auto_refresh: Enable background token refresh scheduler.
        refresh_interval_seconds: How often to check token validity.
        refresh_buffer_seconds: Refresh if token expires within this window.
        lifecycle: Optional lifecycle manager to register scheduler with.

    Returns:
        ClientComponents namedtuple with http_client and connection_manager.
    """
    conn_mgr = create_connection_manager(
        auth=auth,
        client_id=client_id,
        pin=pin,
        totp_secret=totp_secret,
        token_store=token_store,
        env_path=env_path,
        token_state_dir=token_state_dir,
        auto_refresh=auto_refresh,
        refresh_interval_seconds=refresh_interval_seconds,
        refresh_buffer_seconds=refresh_buffer_seconds,
        lifecycle=lifecycle,
    )

    token = auth.get_token()
    http_client = create_http_client(
        client_id=client_id,
        access_token=token,
        token_refresh_fn=conn_mgr.refresh_token_for_http,
    )

    return ClientComponents(http_client=http_client, connection_manager=conn_mgr)
