"""Secret management with encryption and token rotation support.

Provides Fernet symmetric encryption for token state files at rest,
with backward compatibility for unencrypted tokens. Supports token
rotation without application restart.

Usage::

    from infrastructure.security.secret_manager import EncryptedTokenStore

    # Initialize with encryption key from environment
    store = EncryptedTokenStore("runtime/dhan-token-state.json")

    # Save token (automatically encrypts if key is available)
    store.save(token_state)

    # Load token (automatically decrypts if encrypted)
    token_state = store.load()

    # Rotate token
    store.rotate_token(new_token_state)
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from domain.exceptions import TradeXV2Error

logger = logging.getLogger(__name__)


class TokenRotationError(TradeXV2Error):
    """Raised when token rotation fails."""


class EncryptionNotConfiguredError(TradeXV2Error):
    """Raised when encryption is required but not configured."""


class SecretManager:
    """Manages encryption keys and secret rotation.

    Provides centralized access to encryption keys and supports
    key rotation for enhanced security.
    """

    _instance: SecretManager | None = None
    _fernet: Fernet | None = None
    _key: bytes | None = None
    _instance_lock = threading.Lock()

    def __init__(self, encryption_key: str | None = None) -> None:
        """Initialize secret manager.

        Args:
            encryption_key: Fernet key (base64-encoded). If not provided,
                loaded from SECRET_ENCRYPTION_KEY env var.
        """
        self._key_str = encryption_key or os.environ.get("SECRET_ENCRYPTION_KEY", "")

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
            logger.warning(
                "SECRET_ENCRYPTION_KEY not set - token state files will be unencrypted. "
                "Generate a key with: python -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'"
            )

    @property
    def is_encryption_enabled(self) -> bool:
        """Check if encryption is enabled."""
        return self._fernet is not None

    @property
    def fernet(self) -> Fernet:
        """Get Fernet instance for encryption/decryption.

        Returns:
            Fernet instance.

        Raises:
            EncryptionNotConfiguredError: If encryption is not configured.
        """
        if self._fernet is None:
            raise EncryptionNotConfiguredError(
                "Encryption not configured. Set SECRET_ENCRYPTION_KEY environment variable."
            )
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string value.

        Args:
            plaintext: String to encrypt.

        Returns:
            Base64-encoded encrypted string.

        Raises:
            EncryptionNotConfiguredError: If encryption is not configured.
        """
        return self.fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a string value.

        Args:
            ciphertext: Base64-encoded encrypted string.

        Returns:
            Decrypted plaintext string.

        Raises:
            EncryptionNotConfiguredError: If encryption is not configured.
            InvalidToken: If decryption fails.
        """
        return self.fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")

    def generate_key(self) -> str:
        """Generate a new encryption key.

        Returns:
            Base64-encoded Fernet key.
        """
        return Fernet.generate_key().decode("utf-8")

    def rotate_key(self, old_ciphertext: str, new_key: str | None = None) -> str:
        """Re-encrypt data with a new key.

        Args:
            old_ciphertext: Data encrypted with old key.
            new_key: New encryption key. If None, generates new key.

        Returns:
            Data re-encrypted with new key.
        """
        # Decrypt with old key
        old_fernet = Fernet(self._key_str.encode("utf-8"))
        plaintext = old_fernet.decrypt(old_ciphertext.encode("utf-8")).decode("utf-8")

        # Generate or use new key
        if new_key is None:
            new_key = self.generate_key()

        # Encrypt with new key
        new_fernet = Fernet(new_key.encode("utf-8"))
        return new_fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    @classmethod
    def get_instance(cls, encryption_key: str | None = None) -> SecretManager:
        """Get singleton instance of SecretManager.

        Thread-safe via double-checked locking pattern.

        Args:
            encryption_key: Optional encryption key.

        Returns:
            SecretManager instance.
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls(encryption_key=encryption_key)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for testing)."""
        cls._instance = None


class EncryptedTokenStore:
    """Token state store with optional encryption at rest.

    Wraps token state persistence with automatic encryption/decryption.
    Backward compatible with unencrypted token files (issues warning).

    Args:
        path: Path to token state file.
        encryption_enabled: If True, encrypt tokens. If None, uses
            SecretManager default (based on env var).
    """

    def __init__(
        self,
        path: str | Path,
        encryption_enabled: bool | None = None,
    ) -> None:
        """Initialize token store.

        Args:
            path: Path to token state file.
            encryption_enabled: Override encryption setting. If None,
                uses SecretManager default.
        """
        self._path = Path(path)
        self._encryption_enabled = encryption_enabled

        # Ensure parent directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def _secret_manager(self) -> SecretManager:
        """Get secret manager instance."""
        return SecretManager.get_instance()

    @property
    def is_encrypted(self) -> bool:
        """Check if this store uses encryption."""
        if self._encryption_enabled is not None:
            return self._encryption_enabled and self._secret_manager.is_encryption_enabled
        return self._secret_manager.is_encryption_enabled

    def load(self) -> dict[str, Any] | None:
        """Load token state from file.

        Automatically detects encrypted vs unencrypted format.

        Returns:
            Token state dict or None if file doesn't exist.
        """
        if not self._path.exists():
            return None

        try:
            raw_content = self._path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to read token state file %s: %s", self._path, exc)
            return None

        # Try to detect if content is encrypted
        if self._is_encrypted_format(raw_content):
            return self._load_encrypted(raw_content)
        else:
            return self._load_unencrypted(raw_content)

    def save(self, state: dict[str, Any]) -> None:
        """Save token state to file.

        Automatically encrypts if encryption is enabled.

        Args:
            state: Token state dict to save.
        """
        if self.is_encrypted:
            self._save_encrypted(state)
        else:
            self._save_unencrypted(state)

    def rotate_token(self, new_state: dict[str, Any]) -> None:
        """Rotate token state atomically.

        Saves new token state and logs rotation event.

        Args:
            new_state: New token state dict.

        Raises:
            TokenRotationError: If rotation fails.
        """
        try:
            old_state = self.load()

            # Save new state
            self.save(new_state)

            # Log rotation
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

    def _is_encrypted_format(self, content: str) -> bool:
        """Detect if content is in encrypted format.

        Encrypted content starts with b'eyJ' (base64 of Fernet header).

        Args:
            content: File content to check.

        Returns:
            True if content appears to be encrypted.
        """
        # Encrypted Fernet tokens start with specific base64 pattern
        return content.startswith("gAAAAA") or content.startswith("Zg==")

    def _load_encrypted(self, ciphertext: str) -> dict[str, Any] | None:
        """Load and decrypt encrypted token state.

        Args:
            ciphertext: Encrypted content.

        Returns:
            Decrypted token state dict or None on failure.
        """
        if not self.is_encrypted:
            logger.warning(
                "Token state file %s is encrypted but encryption is not enabled. "
                "Set SECRET_ENCRYPTION_KEY to decrypt.",
                self._path,
            )
            return None

        try:
            plaintext = self._secret_manager.decrypt(ciphertext)
            return json.loads(plaintext)
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
        """Load unencrypted token state.

        Args:
            content: JSON content.

        Returns:
            Token state dict or None on failure.
        """
        if self.is_encrypted:
            logger.warning(
                "Token state file %s is unencrypted - consider enabling encryption",
                self._path,
            )

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to parse token state file %s: %s",
                self._path,
                exc,
            )
            return None

    def _save_encrypted(self, state: dict[str, Any]) -> None:
        """Encrypt and save token state.

        Args:
            state: Token state dict to encrypt and save.
        """
        try:
            plaintext = json.dumps(state, indent=2)
            ciphertext = self._secret_manager.encrypt(plaintext)

            # Write with secure permissions
            self._path.write_text(ciphertext, encoding="utf-8")
            self._set_secure_permissions()

        except Exception as exc:
            logger.error(
                "Failed to save encrypted token state to %s: %s",
                self._path,
                exc,
            )
            raise

    def _save_unencrypted(self, state: dict[str, Any]) -> None:
        """Save unencrypted token state.

        Args:
            state: Token state dict to save.
        """
        try:
            content = json.dumps(state, indent=2)
            self._path.write_text(content, encoding="utf-8")
            self._set_secure_permissions()

        except Exception as exc:
            logger.error(
                "Failed to save token state to %s: %s",
                self._path,
                exc,
            )
            raise

    def _set_secure_permissions(self) -> None:
        """Set file permissions to owner read/write only."""
        try:
            os.chmod(self._path, 0o600)
        except OSError as exc:
            logger.warning(
                "Failed to set secure permissions on %s: %s",
                self._path,
                exc,
            )

    def delete(self) -> None:
        """Delete token state file."""
        if self._path.exists():
            try:
                self._path.unlink()
                logger.info("Deleted token state file %s", self._path)
            except Exception as exc:
                logger.error(
                    "Failed to delete token state file %s: %s",
                    self._path,
                    exc,
                )
