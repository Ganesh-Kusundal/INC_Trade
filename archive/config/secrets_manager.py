"""Secrets manager — unified access to credentials from env and files."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class SecretsManager:
    """Read secrets from environment variables or gitignored files.

    Supports the file-based layout documented in ``config/CONFIG.md`` and
    provides a single interface that can be extended to Vault/AWS SM later.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self._root = project_root or Path.cwd()

    def get_env(self, key: str, default: str = "") -> str:
        return os.environ.get(key, default)

    def get_file(self, relative_path: str, *, strip: bool = True) -> str:
        path = self._root / relative_path
        if not path.exists():
            return ""
        value = path.read_text(encoding="utf-8")
        return value.strip() if strip else value

    def get_env_or_file(self, key: str, file_key: str, default: str = "") -> str:
        value = self.get_env(key, default).strip()
        if value:
            return value
        file_path = self.get_env(file_key, "").strip()
        if file_path:
            path = Path(file_path)
            if not path.is_absolute():
                path = self._root / path
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
        return default

    def get_dhan_totp_secret(self) -> str:
        """Get Dhan TOTP secret from env var or file."""
        return self.get_env_or_file("DHAN_TOTP_SECRET", "DHAN_TOTP_SECRET_FILE")

    def get_dhan_pin(self) -> str:
        """Get Dhan PIN from env var or file."""
        return self.get_env_or_file("DHAN_PIN", "DHAN_PIN_FILE")

    def get_upstox_pin(self) -> str:
        """Get Upstox PIN from env var or file."""
        return self.get_env_or_file("UPSTOX_PIN", "UPSTOX_PIN_FILE")

    def get_upstox_totp_secret(self) -> str:
        """Get Upstox TOTP secret from env var or file."""
        return self.get_env_or_file("UPSTOX_TOTP_SECRET", "UPSTOX_TOTP_SECRET_FILE")

    def get_api_key(self) -> str:
        return self.get_env("API_KEY")

    def require(self, key: str) -> str:
        value = self.get_env(key)
        if not value:
            raise ValueError(f"Required secret {key} is not set")
        return value
