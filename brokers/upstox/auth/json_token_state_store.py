"""Token state file store.

Mirrors Trade_J ``JsonTokenStateStore`` — atomic JSON file persistence
for the OAuth token lifecycle. No encryption (file is local; users are
expected to set OS-level file permissions).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class JsonTokenStateStore:
    """JSON file-backed token state store with atomic writes."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict | None:
        with self._lock:
            if not self._path.exists():
                return None
            try:
                text = self._path.read_text()
                if not text.strip():
                    return None
                return json.loads(text)
            except (OSError, json.JSONDecodeError):
                return None

    def save(self, state: dict) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(self._path.parent), prefix=self._path.name + ".", suffix=".tmp"
            )
            try:
                # Set secure file permissions before writing
                os.fchmod(tmp_fd, 0o600)
                with os.fdopen(tmp_fd, "w") as fp:
                    json.dump(state, fp, indent=2)
                os.replace(tmp_path, self._path)
            except (OSError, ValueError):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
                raise

    def clear(self) -> None:
        with self._lock:
            if self._path.exists():
                self._path.unlink()
