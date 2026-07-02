"""PKCE utility for OAuth 2.0 authorization code flow.

Mirrors Trade_J ``UpstoxPkceUtil``.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class PkcePair:
    code_verifier: str
    code_challenge: str


class UpstoxPkceUtil:
    """Generates a random PKCE pair and the SHA-256 code challenge."""

    CODE_VERIFIER_BYTE_LENGTH = 32

    @classmethod
    def generate(cls) -> PkcePair:
        verifier_bytes = secrets.token_bytes(cls.CODE_VERIFIER_BYTE_LENGTH)
        verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode("ascii")
        challenge = cls.compute_challenge(verifier)
        return PkcePair(code_verifier=verifier, code_challenge=challenge)

    @staticmethod
    def compute_challenge(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
