"""Token encryption for secure persistence."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Optional


class TokenEncryptor:
    """HMAC-signed base64 encryption for token storage.
    
    Uses HMAC-SHA256 for integrity and base64 for encoding.
    Not encryption in the cryptographic sense (no confidentiality),
    but prevents token tampering and casual exposure.
    
    For real confidentiality, use Fernet from cryptography lib.
    """
    
    def __init__(self, key: Optional[str] = None) -> None:
        """Initialize with an optional encryption key.
        
        If no key is provided, encrypt/decrypt are pass-through.
        """
        self._key = key.encode() if key else None
    
    @classmethod
    def from_env(cls, env_var: str = "TRADEX_STORAGE_KEY") -> TokenEncryptor:
        """Create from environment variable."""
        import os
        key = os.environ.get(env_var)
        return cls(key=key)
    
    def encrypt(self, data: str) -> str:
        """Encrypt a string value."""
        if not self._key:
            return data
        
        raw = data.encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        
        signature = hmac.new(self._key, encoded.encode(), hashlib.sha256).hexdigest()
        return f"{signature}:{encoded}"
    
    def decrypt(self, data: str) -> str:
        """Decrypt a string value."""
        if not self._key:
            return data
        
        if ":" not in data:
            raise ValueError("Invalid encrypted format")
        
        signature, encoded = data.split(":", 1)
        
        expected = hmac.new(self._key, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Token integrity check failed")
        
        return base64.b64decode(encoded.encode()).decode("utf-8")
    
    @property
    def is_enabled(self) -> bool:
        """Whether encryption is active."""
        return self._key is not None