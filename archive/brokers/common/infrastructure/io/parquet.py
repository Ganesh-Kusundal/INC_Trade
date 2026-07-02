"""Atomic I/O utilities.

All writes go to a sibling temp file, are fsync'd, then atomically renamed into
place so readers never observe a partial file.

Advisory file locking:
    ``FileLock`` provides cross-process advisory locks via ``fcntl.flock``
    on POSIX. Use this to prevent concurrent writers from clobbering each
    other's data during read-modify-write cycles.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


@contextmanager
def file_lock(path: Path, timeout: float = 30.0):
    """Acquire an advisory exclusive lock on a file.

    Creates a .lock sibling file and acquires an exclusive flock.
    Blocks until lock is acquired or timeout expires.

    Usage:
        with file_lock(parquet_path):
            # exclusive access to this file
            df = pd.read_parquet(parquet_path)
            df = transform(df)
            write_parquet(df, parquet_path)
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _temp_path(path: Path) -> Path:
    """Return a temp-file path next to the final destination."""
    return path.with_suffix(f"{path.suffix}.tmp")


def _fsync_and_replace(tmp_path: Path, final_path: Path) -> None:
    """Flush ``tmp_path`` to disk and atomically replace ``final_path``."""
    final_path.parent.mkdir(parents=True, exist_ok=True)

    with open(tmp_path, "rb") as fh:
        os.fsync(fh.fileno())

    try:
        dir_fd = os.open(final_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

    os.replace(tmp_path, final_path)


def atomic_parquet_write(path: Path, table: pa.Table, **write_options: Any) -> None:
    """Write a PyArrow Table to ``path`` atomically.

    Parameters
    ----------
    path : Path
        Destination Parquet file path.
    table : pa.Table
        Table to write.
    write_options : dict
        Extra options forwarded to ``pyarrow.parquet.write_table``.
    """
    tmp_path = _temp_path(path)
    try:
        pq.write_table(table, tmp_path, **write_options)
        _fsync_and_replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def atomic_text_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically as UTF-8 text."""
    tmp_path = _temp_path(path)
    try:
        tmp_path.write_text(content, encoding="utf-8")
        _fsync_and_replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def atomic_json_write(path: Path, data: Any) -> None:
    """Serialize ``data`` as JSON and write it to ``path`` atomically."""
    atomic_text_write(path, json.dumps(data, indent=2, default=str))
