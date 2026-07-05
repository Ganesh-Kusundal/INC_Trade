"""Secrets manager — unified access to credentials from env, files, and encrypted store.

Resolution order: environment variable -> file path -> encrypted store -> default.

Usage::

    from inc_trade.config.secrets_manager import SecretsManager

    sm = SecretsManager()
    token = sm.get("DHAN_ACCESS_TOKEN")
    pin = sm.require("DHAN_PIN")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class SecretsManager:
    """Unified credential access abstraction over env + file + encrypted store."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._root = project_root or Path.cwd()

    def get(self, key: str, default: str = "") -> str:
        """Get a secret by env var name, with file-path fallback."""
        value = os.environ.get(key, "").strip()
        if value:
            return value

        file_key = f"{key}_FILE"
        file_path = os.environ.get(file_key, "").strip()
        if file_path:
            path = Path(file_path)
            if not path.is_absolute():
                path = self._root / path
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()

        return default

    def require(self, key: str) -> str:
        """Get a required secret. Raises ValueError if not set."""
        value = self.get(key)
        if not value:
            raise ValueError(f"Required secret {key} is not set")
        return value

    def has(self, key: str) -> bool:
        """Check if a secret is available."""
        return bool(self.get(key))

    def get_dhan_totp_secret(self) -> str:
        return self.get("DHAN_TOTP_SECRET")

    def get_dhan_pin(self) -> str:
        return self.get("DHAN_PIN")

    def get_upstox_pin(self) -> str:
        return self.get("UPSTOX_PIN")

    def get_upstox_totp_secret(self) -> str:
        return self.get("UPSTOX_TOTP_SECRET")

    def get_api_key(self) -> str:
        return self.get("API_KEY")
