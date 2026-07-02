"""Single Dhan TOTP token generation client."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from brokers.common.auth.totp_cooldown import TotpCooldownGuard, TotpRateLimitError

if TYPE_CHECKING:
    from brokers.dhan.settings import DhanConnectionSettings

logger = logging.getLogger(__name__)


class DhanTotpClient:
    """Generate Dhan access tokens via TOTP with shared rate-limit guard."""

    def __init__(
        self,
        settings: DhanConnectionSettings | None = None,
        cooldown: TotpCooldownGuard | None = None,
    ) -> None:
        self._settings = settings
        self._cooldown = cooldown or TotpCooldownGuard.for_broker("dhan")

    def generate(self) -> str | None:
        """Generate a fresh access token. Returns None on failure.

        Raises ``TotpRateLimitError`` when local or broker cooldown applies.
        """
        self._cooldown.check_allowed()

        pin, totp_secret, token_url, client_id = self._resolve_credentials()
        if not pin or not totp_secret:
            return None

        self._cooldown.record_attempt()
        try:
            import pyotp
            import requests as _requests

            totp_code = pyotp.TOTP(totp_secret).now()
            payload = {"dhanClientId": client_id, "pin": pin, "totp": totp_code}
            resp = _requests.post(token_url, data=payload, timeout=15)

            try:
                body = resp.json()
            except Exception:
                body = {}

            message = body.get("message", "")
            status = body.get("status", "")
            if "once every 2 minutes" in message:
                self._cooldown.record_rate_limited()
                error_msg = f"Dhan token rate limit: {message}"
                logger.warning(error_msg)
                raise TotpRateLimitError(error_msg)

            if status == "error":
                logger.warning("TOTP token generation failed: %s", message or "unknown")
                return None

            if resp.status_code != 200:
                logger.warning("TOTP token generation failed: HTTP %d", resp.status_code)
                return None

            data = body.get("data", body)
            result: str = data.get("accessToken") or data.get("access_token") or ""
            if result:
                self._cooldown.record_success()
                return result
            return None
        except TotpRateLimitError:
            raise
        except Exception as exc:
            logger.warning("TOTP token generation failed: %s", exc)
            return None

    def _resolve_credentials(self) -> tuple[str | None, str | None, str, str]:
        if self._settings and self._settings.has_totp:
            return (
                self._settings.pin,
                self._settings.totp_secret,
                self._settings.generate_token_url,
                self._settings.client_id,
            )
        pin = _read_secret("DHAN_PIN", "DHAN_PIN_FILE")
        totp_secret = _read_secret("DHAN_TOTP_SECRET", "DHAN_TOTP_SECRET_FILE")
        from brokers.dhan.settings import _GENERATE_TOKEN_URL

        client_id = os.environ.get("DHAN_CLIENT_ID", "")
        return pin, totp_secret, _GENERATE_TOKEN_URL, client_id


from brokers.dhan.secret_utils import read_secret as _read_secret
