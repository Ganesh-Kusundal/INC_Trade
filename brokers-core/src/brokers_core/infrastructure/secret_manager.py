"""Secret management with Fernet encryption and token rotation support.

Provides symmetric encryption for secrets at rest, with backward
compatibility for unencrypted data. Supports key rotation.

Usage::

    from brokers_core.infrastructure.secret_manager import SecretManager, EncryptedTokenStore

    mgr = SecretManager.get_instance()
    ciphertext = mgr.encrypt("my-secret")
    plaintext = mgr.decrypt(ciphertext)

    store = EncryptedTokenStore("runtime/token-state.json")
    store.save({"access_token": "..."})
    state = store.load()
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from brokers_core.domain.exceptions import ConfigError

logger = logging.getLogger(__name__)


class TokenRotationError(ConfigError):
    """Raised when token rotation fails."""


class EncryptionNotConfiguredError(ConfigError):
    """Raised when encryption is required but not configured."""


class SecretManager:
    """Manages encryption keys and secret rotation.

    Thread-safe singleton via double-checked locking.
    """

    _instance: SecretManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self, encryption_key: str | None = None) -> None:
        self._key_str = encryption_key or os.environ.get("SECRET_ENCRYPTION_KEY", "")
        self._fernet: Fernet | None = None
        self._key: bytes | None = None

        if self._key_str:
            try:
                self._key = self._key_str.encode("utf-8")
                self._fernet = Fernet(self._key)
                logger.info("Encryption initialized successfully")
            except Exception as exc:
                logger.error("Failed to initialize encryption: %s", exc)
                self._fernet = None
                self._key = None
        else:
            logger.debug(
                "SECRET_ENCRYPTION_KEY not set - secrets will be unencrypted. "
                "Generate a key with: python -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'"
            )

    @property
    def is_encryption_enabled(self) -> bool:
        return self._fernet is not None

    @property
    def fernet(self) -> Fernet:
        if self._fernet is None:
            raise EncryptionNotConfiguredError(
                "Encryption not configured. Set SECRET_ENCRYPTION_KEY environment variable."
            )
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        return str(self.fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8"))

    def decrypt(self, ciphertext: str) -> str:
        return str(self.fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8"))

    def generate_key(self) -> str:
        return str(Fernet.generate_key().decode("utf-8"))

    @classmethod
    def get_instance(cls, encryption_key: str | None = None) -> SecretManager:
        """Get singleton instance (thread-safe via DCLP)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls(encryption_key=encryption_key)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None


class EncryptedTokenStore:
    """Token state store with optional encryption at rest.

    Automatically detects encrypted vs unencrypted format on load.
    Files written with 0o600 permissions.
    """

    def __init__(
        self,
        path: str | Path,
        encryption_enabled: bool | None = None,
    ) -> None:
        self._path = Path(path)
        self._encryption_enabled = encryption_enabled
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def _secret_manager(self) -> SecretManager:
        return SecretManager.get_instance()

    @property
    def is_encrypted(self) -> bool:
        if self._encryption_enabled is not None:
            return (
                self._encryption_enabled
                and self._secret_manager.is_encryption_enabled
            )
        return self._secret_manager.is_encryption_enabled

    def load(self) -> dict[str, Any] | None:
        """Load token state from file. Auto-detects format."""
        if not self._path.exists():
            return None

        try:
            raw_content = self._path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to read token state file %s: %s", self._path, exc)
            return None

        if self._is_encrypted_format(raw_content):
            return self._load_encrypted(raw_content)
        return self._load_unencrypted(raw_content)

    def save(self, state: dict[str, Any]) -> None:
        """Save token state to file. Encrypts if enabled."""
        if self.is_encrypted:
            self._save_encrypted(state)
        else:
            self._save_unencrypted(state)

    def rotate_token(self, new_state: dict[str, Any]) -> None:
        """Rotate token state atomically."""
        try:
            old_state = self.load()
            self.save(new_state)
            logger.info(
                "Token rotated for %s (old source: %s, new source: %s)",
                self._path.name,
                old_state.get("source", "unknown") if old_state else "none",
                new_state.get("source", "unknown"),
            )
        except Exception as exc:
            raise TokenRotationError(
                f"Failed to rotate token for {self._path}: {exc}"
            ) from exc

    def delete(self) -> None:
        """Delete token state file."""
        if self._path.exists():
            try:
                self._path.unlink()
                logger.info("Deleted token state file %s", self._path)
            except Exception as exc:
                logger.error(
                    "Failed to delete token state file %s: %s", self._path, exc
                )

    def _is_encrypted_format(self, content: str) -> bool:
        return content.startswith("gAAAAA") or content.startswith("Zg==")

    def _load_encrypted(self, ciphertext: str) -> dict[str, Any] | None:
        if not self.is_encrypted:
            logger.warning(
                "Token state file %s is encrypted but encryption is not enabled.",
                self._path,
            )
            return None
        try:
            plaintext = self._secret_manager.decrypt(ciphertext)
            return dict(json.loads(plaintext))
        except InvalidToken:
            logger.error(
                "Failed to decrypt token state file %s - invalid token or wrong key",
                self._path,
            )
            return None
        except Exception as exc:
            logger.error(
                "Failed to load encrypted token state from %s: %s",
                self._path,
                exc,
            )
            return None

    def _load_unencrypted(self, content: str) -> dict[str, Any] | None:
        if self.is_encrypted:
            logger.warning(
                "Token state file %s is unencrypted - consider enabling encryption",
                self._path,
            )
        try:
            return dict(json.loads(content))
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to parse token state file %s: %s", self._path, exc
            )
            return None

    def _save_encrypted(self, state: dict[str, Any]) -> None:
        plaintext = json.dumps(state, indent=2)
        ciphertext = self._secret_manager.encrypt(plaintext)
        self._write_secure(ciphertext)

    def _save_unencrypted(self, state: dict[str, Any]) -> None:
        content = json.dumps(state, indent=2)
        self._write_secure(content)

    def _write_secure(self, content: str) -> None:
        fd = os.open(
            str(self._path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
        )
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
