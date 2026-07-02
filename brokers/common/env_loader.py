"""Shared .env file loader — single implementation used by all broker factories."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def load_env_file(path: Path) -> None:
    """Minimal .env parser — no python-dotenv dependency.

    Reads key=value pairs from the given file path and sets them
    as environment variables. Comments (lines starting with #) and
    blank lines are skipped. Values are stripped of surrounding quotes.

    This overwrites existing env vars so fresh tokens take effect.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value
