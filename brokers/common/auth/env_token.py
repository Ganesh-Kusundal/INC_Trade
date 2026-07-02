"""Atomic env-file token updates shared across brokers."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def update_env_token(
    env_path: Path,
    token: str,
    *,
    env_key: str = "DHAN_ACCESS_TOKEN",
) -> None:
    """Update *env_key* in the env file atomically."""
    if not env_path.exists():
        return

    try:
        import fcntl
    except Exception as exc:  # pragma: no cover - non-Unix fallback
        logger.warning("fcntl unavailable, env update unprotected: %s", exc)
        return

    fd: int | None = None
    tmp_path = env_path.with_suffix(f"{env_path.suffix}.tmp")
    prefix = f"{env_key}="

    try:
        fd = os.open(str(env_path), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)

        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as fh:
            content = fh.read()

        lines = content.splitlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(prefix):
                lines[i] = f"{prefix}{token}"
                updated = True
                break

        if not updated:
            if lines and not content.endswith("\n"):
                lines.append("")
            lines.append(f"{prefix}{token}")

        new_content = "\n".join(lines)
        if not new_content.endswith("\n"):
            new_content += "\n"

        tmp_path.write_text(new_content, encoding="utf-8")

        with open(tmp_path, "rb") as tmp_fh:
            os.fsync(tmp_fh.fileno())

        dir_fd = os.open(env_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        os.replace(tmp_path, env_path)

    except PermissionError:
        logger.info("Env file is read-only; token persisted to state store only.")
    except Exception as exc:
        logger.warning("Failed to update env token: %s", exc)
        if tmp_path.exists():
            tmp_path.unlink()
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception as exc:
                logger.debug("file_unlock_failed: %s", exc)
            try:
                os.close(fd)
            except Exception as exc:
                logger.debug("file_close_failed: %s", exc)
