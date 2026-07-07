"""Dhan authentication provider — broker-specific auth logic."""

from __future__ import annotations

from typing import Optional

import httpx

from tradex.broker.auth import AuthManager, TokenInfo
from tradex.broker.provider import AuthProvider
from tradex.broker.session import SessionManager, SessionStatus
from tradex.core.errors import AuthenticationError, map_provider_error
from tradex.core.logging_config import get_logger
from tradex.domain.account import AccountProfile
from tradex.providers.dhan.config import DhanConfig
from tradex.providers.dhan.http_client import DhanHTTPClient

logger = get_logger("providers.dhan.auth")


class DhanAuthProvider(AuthProvider):
    """Dhan-specific authentication.

    Handles token verification and profile retrieval via the shared
    HTTP client.
    """

    def __init__(
        self,
        config: DhanConfig,
        auth_manager: AuthManager,
        session: SessionManager,
        http_client: Optional[DhanHTTPClient] = None,
    ) -> None:
        self._config = config
        self._auth = auth_manager
        self._session = session
        self._http_client = http_client or DhanHTTPClient(config, auth_manager)

    async def connect(self) -> None:
        """Authenticate with Dhan using client_id and access_token."""
        # Pre-set token from config so the shared HTTP client can use it
        token = TokenInfo(
            access_token=self._config.access_token,
            expires_at=0,  # Dhan tokens are long-lived; set 0 to avoid expiry checks
        )
        await self._auth.set_token(token)

        # Verify the token by fetching profile via shared client
        await self.get_profile()
        await self._session.transition(SessionStatus.CONNECTED)

        logger.info("dhan_auth_success", client_id=self._config.client_id)

    async def disconnect(self) -> None:
        """Disconnect and clean up."""
        await self._auth.invalidate("Disconnected")
        await self._session.transition(SessionStatus.DISCONNECTED)

    async def refresh_token(self) -> None:
        """Refresh the access token.

        Dhan tokens are typically long-lived. This method
        regenerates a new token if needed.
        """
        try:
            # Try to auto-generate a new token via Dhan's OAuth flow
            new_token = await self._http_client.generate_token(client_id=self._config.client_id)

            if new_token:
                updated_token = TokenInfo(
                    access_token=new_token,
                    expires_at=0,  # Dhan tokens are long-lived
                )
                await self._auth.set_token(updated_token)
                logger.info("dhan_token_refresh_success", client_id=self._config.client_id)
                return
            else:
                raise AuthenticationError(
                    "Token generation failed: No token returned from Dhan",
                    code="DH-902",
                )
        except Exception as e:
            # Handle various refresh error scenarios
            if "rate limit" in str(e).lower():
                raise AuthenticationError(
                    f"Token refresh rate limit exceeded: {str(e)}",
                    code="DH-904",
                    retryable=True,
                )
            elif "invalid" in str(e).lower() or "unauthorized" in str(e).lower():
                raise AuthenticationError(
                    f"Token refresh authentication failed: {str(e)}",
                    code="DH-903",
                    retryable=False,
                )
            else:
                # Generic token refresh error
                raise AuthenticationError(
                    f"Token refresh failed: {str(e)}",
                    code="DH-908",
                    retryable=True,
                ) from e

    async def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._auth.is_authenticated

    async def get_profile(self) -> AccountProfile:
        """Fetch account profile from Dhan."""
        try:
            data = await self._http_client.get("/v2/profile")
            return AccountProfile.from_dhan(data.get("data", {}))
        except httpx.HTTPError as e:
            raise map_provider_error(
                code="DH-909",
                message=f"HTTP error: {e}",
                provider="dhan",
            ) from e
