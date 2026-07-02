"""Credential resolution with environment file and file-based secret fallback.

Each broker has a canonical env file location. Secrets can be provided
either as environment variables or as file paths (Kubernetes-style),
with env var taking precedence.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CANONICAL_ENV_FILES: dict[str, str | None] = {
    "dhan": ".env.local",
    "upstox": ".env.upstox",
    "paper": None,
}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class CredentialResolver:
    def __init__(self, project_root: Path | None = None):
        self._project_root = project_root or _PROJECT_ROOT

    def resolve_env_path(self, broker: str) -> Path | None:
        filename = CANONICAL_ENV_FILES.get(broker)
        if filename is None:
            return None
        return self._project_root / filename

    def load_broker_env(self, broker: str) -> bool:
        path = self.resolve_env_path(broker)
        if path is None or not path.exists():
            return False
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value
        logger.info("Loaded env file for broker=%s path=%s", broker, path)
        return True


def read_secret(env_key: str, file_key: str | None = None) -> str:
    value = os.environ.get(env_key, "")
    if value:
        return value
    if file_key:
        file_path = os.environ.get(file_key, "")
        if file_path and Path(file_path).is_file():
            return Path(file_path).read_text().strip()
    return ""
