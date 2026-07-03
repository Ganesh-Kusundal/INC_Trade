"""JSON token state store — atomic writes with 0o600 permissions."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class JsonTokenStateStore:
    def __init__(self, path: Path | str | None) -> None:
        self._path = Path(path) if path else None
        self._lock = threading.RLock()

    @property
    def path(self) -> Path | None:
        return self._path

    def load(self) -> dict | None:
        if self._path is None or not self._path.exists():
            return None
        with self._lock:
            try:
                data = json.loads(self._path.read_text())
                return data if isinstance(data, dict) else None
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load token state from %s: %s", self._path, exc)
                return None

    def save(self, state: dict) -> None:
        if self._path is None:
            return
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._path.parent), suffix=".tmp"
            )
            try:
                os.write(fd, json.dumps(state, indent=2).encode())
                os.fchmod(fd, 0o600)
                os.close(fd)
                os.replace(tmp_path, str(self._path))
            except Exception:
                os.close(fd) if not os.get_inheritable(fd) else None
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

    def clear(self) -> None:
        if self._path is None or not self._path.exists():
            return
        with self._lock:
            try:
                self._path.unlink()
            except OSError as exc:
                logger.warning("Failed to clear token state at %s: %s", self._path, exc)
