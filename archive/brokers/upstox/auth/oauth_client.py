"""Low-level OAuth 2.0 client for Upstox.

Mirrors Trade_J ``UpstoxOAuthClient``. No SDK dependency — uses ``requests``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests

from .exceptions import UpstoxAuthError


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    refresh_token: str | None
    expires_in_seconds: int
    issued_at_ms: int


class UpstoxOAuthClient:
    """Upstox OAuth 2.0 client supporting:

    * code exchange (``grant_type=authorization_code``)
    * refresh grant (``grant_type=refresh_token``)
    * profile fetch for token expiry introspection
    * read-only token validation (market-status ping)
    * V3 token-request trigger (push/WhatsApp approval)
    """

    def __init__(self, base_url: str, *, timeout_seconds: int = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._session = requests.Session()

    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> TokenResponse:
        body = urlencode(
            {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            }
        )
        return self._post_token(body)

    def refresh_token(
        self, refresh_token: str, client_id: str, client_secret: str
    ) -> TokenResponse:
        body = urlencode(
            {
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            }
        )
        return self._post_token(body)

    def fetch_profile(self, access_token: str) -> int:
        """Hit ``/user/profile`` to retrieve ``data.token_expiry``.

        Returns epoch ms, or -1 if unavailable.
        """
        try:
            resp = self._session.get(
                f"{self._base_url}/v2/user/profile",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            )
        except (requests.RequestException, Exception):
            return -1
        if resp.status_code != 200:
            return -1
        try:
            payload = resp.json()
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            token_expiry = data.get("token_expiry")
            if not token_expiry:
                return -1
            from datetime import datetime

            dt = datetime.fromisoformat(token_expiry.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except (ValueError, TypeError, json.JSONDecodeError):
            return -1

    def validate_read_only_token(self, token: str) -> bool:
        try:
            resp = self._session.get(
                f"{self._base_url}/v2/market/status/NSE",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            )
            return resp.status_code == 200
        except (requests.RequestException, Exception):
            return False

    def trigger_token_request(self, client_id: str, client_secret: str) -> dict[str, Any]:
        """Triggers Upstox's V3 push/WhatsApp approval flow.

        Upstox sends a push/WhatsApp; on approval, the new token is delivered
        to the configured notifier webhook.
        """
        url = f"{self._base_url}/v3/login/auth/token/request/{client_id}"
        try:
            resp = self._session.post(
                url,
                json={"client_secret": client_secret},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise UpstoxAuthError(f"Token request API call failed: {exc}") from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            raise UpstoxAuthError(f"Token request API returned {resp.status_code}: {resp.text}")
        try:
            payload = resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise UpstoxAuthError("Token request API returned non-JSON body") from exc

        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        return {
            "status": payload.get("status", "unknown") if isinstance(payload, dict) else "unknown",
            "authorizationExpiry": data.get("authorization_expiry"),
            "notifierUrl": data.get("notifier_url"),
        }

    def _post_token(self, body: str) -> TokenResponse:
        url = f"{self._base_url}/v2/login/authorization/token"
        try:
            resp = self._session.post(
                url,
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise UpstoxAuthError(f"Token request failed: {exc}") from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            raise UpstoxAuthError(f"Token endpoint returned {resp.status_code}: {resp.text}")
        try:
            payload = resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise UpstoxAuthError("Token endpoint returned non-JSON body") from exc

        return TokenResponse(
            access_token=payload.get("access_token", ""),
            refresh_token=payload.get("refresh_token"),
            expires_in_seconds=int(payload.get("expires_in", 86400)),
            issued_at_ms=int(time.time() * 1000),
        )
