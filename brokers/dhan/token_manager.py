"""Token Management Utilities for Dhan broker.

Provides TOTP token generation, env file updates, and secret reading
utilities used by the Dhan broker factory and token scheduler.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brokers.dhan.settings import DhanConnectionSettings

logger = logging.getLogger(__name__)


def generate_totp_token(settings: DhanConnectionSettings | None = None) -> str | None:
    """Generate a fresh access token via TOTP (delegates to DhanTotpClient)."""
    from brokers.dhan.totp_client import DhanTotpClient

    return DhanTotpClient(settings).generate()


def read_secret(env_key: str, file_key: str) -> str | None:
    """Read a secret from environment variable or file."""
    val = os.environ.get(env_key, "")
    if val:
        return val

    file_path = os.environ.get(file_key, "")
    if file_path and Path(file_path).exists():
        return Path(file_path).read_text().strip()

    return None
