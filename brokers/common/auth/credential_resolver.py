"""Credential resolver — loads broker credentials from env files and variables.

Provides a unified way to load credentials for any broker:
  - Reads from environment variables first
  - Falls back to .env files (e.g. .env.dhan, .env.upstox)
  - Validates required fields are present

Usage::

    creds = CredentialResolver.for_dhan()
    print(creds.client_id, creds.access_token)

    creds = CredentialResolver.for_upstox()
    print(creds.client_id, creds.api_key)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from brokers.common.logging_helpers import log_debug as _log_debug, log_warning as _log_warning

logger = logging.getLogger(__name__)


# ── Credential data classes ────────────────────────────────────────────────


@dataclass(frozen=True)
class DhanCredentials:
    """Dhan API credentials."""

    client_id: str
    access_token: str
    pin: str = ""
    totp_secret: str = ""
    base_url: str = "https://api.dhan.co/v2"

    @property
    def has_totp(self) -> bool:
        return bool(self.totp_secret and self.pin)


@dataclass(frozen=True)
class UpstoxCredentials:
    """Upstox API credentials.

    ``client_id`` is resolved from ``UPSTOX_CLIENT_ID`` first, falling back
    to ``UPSTOX_API_KEY`` (they are the same value — the API key doubles as
    the OAuth client_id).
    """

    client_id: str
    access_token: str = ""
    api_key: str = ""
    api_secret: str = ""
    redirect_uri: str = "http://127.0.0.1:18080/callback"
    base_url: str = "https://api.upstox.com"
    username: str = ""
    mobile: str = ""
    pin: str = ""
    password: str = ""
    totp_secret: str = ""

    @property
    def has_totp(self) -> bool:
        """Whether TOTP-based session login is possible."""
        return bool(self.totp_secret and self.pin and self.mobile)

    @property
    def has_oauth(self) -> bool:
        """Whether the full OAuth authorization code flow is possible."""
        return bool(self.api_key and self.api_secret and self.redirect_uri)

    @property
    def has_session_auth(self) -> bool:
        """Whether fully automated (no-browser) login is possible.

        Requires username (mobile), pin, TOTP secret, and OAuth
        app credentials (api_key + api_secret + redirect_uri).
        Note: upstox-totp uses PIN as password fallback.
        """
        return bool(
            self.username
            and self.pin
            and self.totp_secret
            and self.has_oauth
        )


# ── Credential resolver ────────────────────────────────────────────────────


class CredentialResolver:
    """Loads broker credentials from environment variables and .env files.

    Resolution order:
    1. Environment variables (highest priority)
    2. .env file in project root (e.g. .env.dhan, .env.upstox)
    3. Global .env file (e.g. ~/.config/inc_trade/.env.dhan)
    """

    _ENV_FILE_MAP = {
        "dhan": [".env.dhan", ".env.local"],
        "upstox": [".env.upstox", ".env.local"],
    }

    @classmethod
    def for_dhan(cls, env_file: str | Path | None = None) -> DhanCredentials:
        """Load Dhan credentials from env or .env file."""
        env = cls._load_env("dhan", env_file)

        client_id = env.get("DHAN_CLIENT_ID", "")
        access_token = env.get("DHAN_ACCESS_TOKEN", "")
        pin = env.get("DHAN_PIN", "")
        totp_secret = env.get("DHAN_TOTP_SECRET", "")
        base_url = env.get("DHAN_BASE_URL", "https://api.dhan.co/v2")

        cls._validate_dhan(client_id, access_token, totp_secret, pin)

        return DhanCredentials(
            client_id=client_id,
            access_token=access_token,
            pin=pin,
            totp_secret=totp_secret,
            base_url=base_url,
        )

    @classmethod
    def for_upstox(cls, env_file: str | Path | None = None) -> UpstoxCredentials:
        """Load Upstox credentials from env or .env file.

        ``UPSTOX_API_KEY`` is aliased as ``client_id`` when ``UPSTOX_CLIENT_ID``
        is not explicitly set — the API key is the OAuth client_id.
        """
        env = cls._load_env("upstox", env_file)

        api_key = env.get("UPSTOX_API_KEY", "")
        # UPSTOX_CLIENT_ID takes precedence; fall back to UPSTOX_API_KEY
        client_id = env.get("UPSTOX_CLIENT_ID", "") or api_key
        access_token = env.get("UPSTOX_ACCESS_TOKEN", "")
        api_secret = env.get("UPSTOX_API_SECRET", "")
        redirect_uri = env.get("UPSTOX_REDIRECT_URI", "http://127.0.0.1:18080/callback")
        base_url = env.get("UPSTOX_BASE_URL", "https://api.upstox.com")
        username = env.get("UPSTOX_USERNAME", "") or env.get("UPSTOX_MOBILE", "")  # UPSTOX_MOBILE aliases UPSTOX_USERNAME
        mobile = env.get("UPSTOX_MOBILE", "") or username
        pin = env.get("UPSTOX_PIN", "")
        pin_code = env.get("UPSTOX_PIN_CODE", "") or pin  # UPSTOX_PIN_CODE aliases UPSTOX_PIN
        password = env.get("UPSTOX_PASSWORD", "")
        totp_secret = env.get("UPSTOX_TOTP_SECRET", "")

        cls._validate_upstox(client_id, access_token, api_key, api_secret, redirect_uri)

        return UpstoxCredentials(
            client_id=client_id,
            access_token=access_token,
            api_key=api_key,
            api_secret=api_secret,
            redirect_uri=redirect_uri,
            base_url=base_url,
            username=username,
            mobile=mobile,
            pin=pin_code,
            password=password,
            totp_secret=totp_secret,
        )

    # ── Internal ─────────────────────────────────────────────────────────

    @classmethod
    def _load_env(cls, broker: str, env_file: str | Path | None) -> dict[str, str]:
        """Load environment variables for a broker.

        Merges os.environ with any .env file contents (env file is lower priority).
        """
        result: dict[str, str] = {}

        # 1. Load .env file (lower priority)
        file_paths: list[Path] = []
        if env_file is not None:
            file_paths.append(Path(env_file))
        else:
            for name in cls._ENV_FILE_MAP.get(broker, []):
                file_paths.append(Path(name))
            # Also check home directory
            home_env = Path.home() / ".config" / "inc_trade" / f".env.{broker}"
            file_paths.append(home_env)

        for path in file_paths:
            if path.exists():
                result.update(cls._parse_env_file(path))
                _log_debug("loaded_env_file", path=str(path), broker=broker)
                break

        # 2. Override with actual environment variables (higher priority)
        for key in result:
            env_val = os.environ.get(key)
            if env_val:
                result[key] = env_val

        # 3. Also include env vars not in the .env file
        prefix = f"{broker.upper()}_"
        for key, val in os.environ.items():
            if key.startswith(prefix) and key not in result:
                result[key] = val

        return result

    @staticmethod
    def _parse_env_file(path: Path) -> dict[str, str]:
        """Parse a .env file into a dict. Handles KEY=VALUE format."""
        result: dict[str, str] = {}
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                # Remove surrounding quotes
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                result[key] = val
        except OSError as exc:
            _log_warning("env_file_parse_failed", path=str(path), error=str(exc))
        return result

    @staticmethod
    def _validate_dhan(
        client_id: str,
        access_token: str,
        totp_secret: str,
        pin: str,
    ) -> None:
        """Validate that minimum Dhan credentials are present."""
        if not client_id:
            raise ValueError("DHAN_CLIENT_ID is required")
        if not access_token and not (totp_secret and pin):
            raise ValueError(
                "Either DHAN_ACCESS_TOKEN or (DHAN_TOTP_SECRET + DHAN_PIN) must be set"
            )

    @staticmethod
    def _validate_upstox(
        client_id: str,
        access_token: str,
        api_key: str,
        api_secret: str,
        redirect_uri: str,
    ) -> None:
        """Validate that minimum Upstox credentials are present.

        Valid auth paths (any one is sufficient):
        1. ``UPSTOX_ACCESS_TOKEN`` — static token (manual refresh)
        2. ``UPSTOX_API_KEY`` + ``UPSTOX_API_SECRET`` + ``UPSTOX_REDIRECT_URI``
           — full OAuth authorization code flow (recommended)
        """
        if not client_id and not api_key:
            raise ValueError(
                "UPSTOX_API_KEY (or UPSTOX_CLIENT_ID) is required"
            )
        has_static = bool(access_token)
        has_oauth = bool(api_key and api_secret and redirect_uri)
        if not has_static and not has_oauth:
            raise ValueError(
                "Either UPSTOX_ACCESS_TOKEN or "
                "(UPSTOX_API_KEY + UPSTOX_API_SECRET + UPSTOX_REDIRECT_URI) must be set"
            )


__all__ = [
    "CredentialResolver",
    "DhanCredentials",
    "UpstoxCredentials",
]
