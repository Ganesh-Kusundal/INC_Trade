"""Auth port — token management interface.

Broker adapters implement this to handle authentication lifecycle:
initial login, token retrieval, and automatic refresh.
"""

from __future__ import annotations

from typing import Protocol


class AuthPort(Protocol):
    def get_token(self) -> str: ...
    def refresh_token(self) -> str: ...
    def is_authenticated(self) -> bool: ...
