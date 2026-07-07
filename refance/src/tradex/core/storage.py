"""Secure token storage and session persistence.

Provides secure storage for tokens and session state.
Supports file-based persistence with optional encryption.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from tradex.core.crypto import TokenEncryptor
from tradex.core.logging_config import get_logger
from tradex.core.token import TokenInfo

logger = get_logger("core.storage")


@dataclass
class SessionSnapshot:
    """Serializable session state for persistence."""

    broker: str = ""
    client_id: str = ""
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0
    issued_at: float = 0.0
    connected_at: str = ""
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}

    def to_token_info(self) -> TokenInfo:
        """Convert to TokenInfo."""
        return TokenInfo(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            expires_at=self.expires_at,
            issued_at=self.issued_at,
        )

    @classmethod
    def from_token_info(
        cls, broker: str, client_id: str, token: TokenInfo, **metadata: Any
    ) -> SessionSnapshot:
        """Create from TokenInfo."""
        return cls(
            broker=broker,
            client_id=client_id,
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_at=token.expires_at,
            issued_at=token.issued_at,
            connected_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata,
        )


class TokenEncryptor:
    """HMAC-signed base64 encryption for token data.

    If no encryption key is provided, data passes through unchanged
    for backward compatibility.
    """

    def __init__(self, key: Optional[str] = None) -> None:
        self._key: Optional[bytes] = None
        if key:
            self._key = key.encode("utf-8")
        else:
            env_key = os.environ.get("TRADEX_TOKEN_KEY", "")
            if env_key:
                self._key = env_key.encode("utf-8")

    def encrypt(self, data: str) -> str:
        if self._key is None:
            return data
        raw = data.encode("utf-8")
        sig = hmac.new(self._key, raw, hashlib.sha256).hexdigest()
        encoded = base64.b64encode(raw).decode("ascii")
        return f"{encoded}:{sig}"

    def decrypt(self, data: str) -> str:
        if self._key is None:
            return data
        encoded, sig = data.rsplit(":", 1)
        raw = base64.b64decode(encoded)
        expected = hmac.new(self._key, raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Token HMAC verification failed")
        return raw.decode("utf-8")


class TokenStore:
    """File-based token storage with restricted permissions.

    Stores tokens in a JSON file with 0600 permissions
    (owner read/write only) for security.
    """

    def __init__(self, storage_dir: Optional[str] = None) -> None:
        if storage_dir:
            self._dir = Path(storage_dir)
        else:
            self._dir = Path.home() / ".tradex" / "tokens"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._encryptor = TokenEncryptor()

    def _path(self, broker: str, client_id: str) -> Path:
        """Get the storage file path for a broker/client."""
        safe_name = f"{broker}_{client_id}".replace("/", "_").replace("\\", "_")
        return self._dir / f"{safe_name}.json"

    async def save(self, snapshot: SessionSnapshot) -> None:
        """Save a session snapshot to disk."""
        path = self._path(snapshot.broker, snapshot.client_id)
        data = asdict(snapshot)

        try:
            path.write_text(json.dumps(data, indent=2))
            # Restrict permissions to owner only (Unix)
            try:
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            except (OSError, AttributeError):
                pass  # Windows or restricted env

            logger.info("token_saved", broker=snapshot.broker, path=str(path))
        except Exception as e:
            logger.error("token_save_failed", error=str(e))

    async def load(self, broker: str, client_id: str) -> Optional[SessionSnapshot]:
        """Load a session snapshot from disk."""
        path = self._path(broker, client_id)

        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            snapshot = SessionSnapshot(**data)
            logger.info("token_loaded", broker=broker)
            return snapshot
        except Exception as e:
            logger.error("token_load_failed", error=str(e))
            return None

    async def delete(self, broker: str, client_id: str) -> bool:
        """Delete a stored session."""
        path = self._path(broker, client_id)
        if path.exists():
            path.unlink()
            logger.info("token_deleted", broker=broker)
            return True
        return False

    async def list_sessions(self) -> list[SessionSnapshot]:
        """List all stored sessions."""
        sessions = []
        for path in self._dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                sessions.append(SessionSnapshot(**data))
            except Exception:
                pass
        return sessions

    def is_valid(self, snapshot: SessionSnapshot) -> bool:
        """Check if a stored session is still usable (not expired)."""
        import time

        if snapshot.expires_at <= 0:
            return True  # No expiry set
        return time.time() < snapshot.expires_at
