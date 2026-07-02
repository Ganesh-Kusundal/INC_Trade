"""Dhan auth — token management."""

from __future__ import annotations

import logging
import requests


logger = logging.getLogger(__name__)


class DhanAuth:
    def __init__(
        self,
        access_token: str | None = None,
        client_id: str | None = None,
        pin: str | None = None,
        totp_secret: str | None = None,
    ):
        self._client_id = client_id or ""
        self._pin = pin
        self._totp_secret = totp_secret
        self._access_token = access_token or ""

        if not self._access_token and self._pin and self._totp_secret:
            self._access_token = self.generate_token()

    def get_token(self) -> str:
        return self._access_token

    def generate_token(self) -> str:
        if not self._pin or not self._totp_secret:
            raise ValueError("pin and totp_secret are required to generate token")
        
        import pyotp
        from urllib.parse import urlencode
        from brokers.adapters.dhan.config import ENDPOINTS

        totp_code = pyotp.TOTP(self._totp_secret).now()
        payload = {"dhanClientId": self._client_id, "pin": self._pin, "totp": totp_code}
        url = ENDPOINTS['generate_token']
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(f"Token generation failed: HTTP {resp.status_code}")
        
        body = resp.json()
        data = body.get("data", body)
        token = data.get("accessToken") or data.get("access_token") or ""
        if not token:
            raise RuntimeError(f"Token generation failed: no token in response: {body}")
        
        return token

    def refresh_token(self) -> str:
        if self._pin and self._totp_secret:
            try:
                self._access_token = self.generate_token()
                logger.info("dhan_token_regenerated_successfully")
            except Exception as exc:
                logger.error("dhan_token_regeneration_failed", extra={"error": str(exc)})
        else:
            logger.warning("dhan_token_refresh_not_supported_without_totp_credentials")
        return self._access_token

    def is_authenticated(self) -> bool:
        return bool(self._access_token)
