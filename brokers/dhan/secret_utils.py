"""Shared secret-reading utilities for Dhan broker components."""

from __future__ import annotations

import os
from pathlib import Path


def read_secret(env_key: str, file_key: str) -> str | None:
    """Read a secret from an environment variable, falling back to a file.

    Parameters
    ----------
    env_key : str
        Name of the environment variable holding the secret value.
    file_key : str
        Name of the environment variable holding the path to a secret file.
        If the env var is empty or the file doesn't exist, returns None.

    Returns
    -------
    str or None
        The secret value, or None if not found.
    """
    val = os.environ.get(env_key, "")
    if val:
        return val
    file_path = os.environ.get(file_key, "")
    if file_path and Path(file_path).exists():
        return Path(file_path).read_text().strip()
    return None
