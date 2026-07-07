"""Common auth — backward-compatible re-export module.

The original god-file has been split into focused modules:
  - ``token_state.py``: TokenState, TokenSource, TokenStateStore, EnvTokenStateStore, JsonTokenStateStore
  - ``totp.py``: TotpGenerator, TotpCooldownGuard
  - ``auth_manager.py``: AuthManager

This module re-exports everything for backward compatibility.
New code should import from the specific sub-modules.
"""

from __future__ import annotations

# Re-export from split modules — preserves all existing import paths
from brokers.common.auth.auth_manager import AuthManager as AuthManager
from brokers.common.auth.token_state import (
    EnvTokenStateStore as EnvTokenStateStore,
    JsonTokenStateStore as JsonTokenStateStore,
    TokenSource as TokenSource,
    TokenState as TokenState,
    TokenStateStore as TokenStateStore,
)
from brokers.common.auth.totp import (
    TotpCooldownGuard as TotpCooldownGuard,
    TotpGenerator as TotpGenerator,
)


__all__ = [
    "AuthManager",
    "EnvTokenStateStore",
    "JsonTokenStateStore",
    "TokenSource",
    "TokenState",
    "TokenStateStore",
    "TotpCooldownGuard",
    "TotpGenerator",
]
