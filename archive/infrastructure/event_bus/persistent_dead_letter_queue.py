"""SQLite-backed dead-letter queue for durable handler failure capture."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from domain.constants import DEAD_LETTER_QUEUE_MAX_SIZE
from infrastructure.event_bus.dead_letter_queue import DeadLetter, DeadLetterQueue
from infrastructure.event_bus.event_bus import DomainEvent

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path("runtime/dead_letter.sqlite")


class PersistentDeadLetterQueue(DeadLetterQueue):
    """In-memory DLQ with SQLite write-through persistence.

    Tests and dry-runs can still use plain :class:`DeadLetterQueue`.
    Production paths should use :func:`create_default_dead_letter_queue`.
    """

    def __init__(
        self,
        max_size: int = DEAD_LETTER_QUEUE_MAX_SIZE,
        on_drop=None,
        *,
        db_path: str | Path | None = None,
    ) -> None:
        super().__init__(max_size=max_size, on_drop=on_drop)
        self._db_path = Path(db_path) if db_path is not None else _DEFAULT_DB_PATH
        self._db_lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db_lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dead_letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    event_id TEXT,
                    symbol TEXT,
                    source TEXT,
                    handler_id TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    failed_at TEXT NOT NULL,
                    traceback TEXT,
                    payload_json TEXT
                )
                """
            )
            conn.commit()

    def push(self, dead_letter: DeadLetter) -> bool:
        accepted = super().push(dead_letter)
        self._persist(dead_letter)
        return accepted

    def _persist(self, dead_letter: DeadLetter) -> None:
        try:
            payload = {
                "event_type": dead_letter.event.event_type,
                "event_id": dead_letter.event.event_id,
                "symbol": dead_letter.event.symbol,
                "source": dead_letter.event.source,
                "timestamp": dead_letter.event.timestamp.isoformat(),
            }
            with self._db_lock, sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO dead_letters (
                        event_type, event_id, symbol, source,
                        handler_id, error_type, error_message,
                        failed_at, traceback, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dead_letter.event.event_type,
                        dead_letter.event.event_id,
                        dead_letter.event.symbol,
                        dead_letter.event.source,
                        dead_letter.handler_id,
                        dead_letter.error_type,
                        dead_letter.error_message,
                        dead_letter.failed_at.isoformat(),
                        dead_letter.traceback,
                        json.dumps(payload),
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("dead_letter_persist_failed: %s", exc)

    def load_recent(self, limit: int = 100) -> list[DeadLetter]:
        """Load the most recent persisted dead letters (newest first)."""
        rows: list[tuple[Any, ...]] = []
        try:
            with self._db_lock, sqlite3.connect(self._db_path) as conn:
                cur = conn.execute(
                    """
                    SELECT event_type, event_id, symbol, source,
                           handler_id, error_type, error_message,
                           failed_at, traceback
                    FROM dead_letters
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
        except Exception as exc:
            logger.debug("dead_letter_load_failed: %s", exc)
            return []

        loaded: list[DeadLetter] = []
        for row in rows:
            try:
                failed_at = datetime.fromisoformat(row[7])
                event = DomainEvent(
                    event_type=row[0],
                    event_id=row[1] or "",
                    symbol=row[2] or "",
                    source=row[3] or "",
                    timestamp=failed_at,
                    payload={},
                )
                loaded.append(
                    DeadLetter(
                        event=event,
                        handler_id=row[4],
                        error_type=row[5],
                        error_message=row[6],
                        failed_at=failed_at,
                        traceback=row[8],
                    )
                )
            except Exception as exc:
                logger.debug("dead_letter_row_parse_failed: %s", exc)
        return loaded


def create_default_dead_letter_queue(
    max_size: int = DEAD_LETTER_QUEUE_MAX_SIZE,
    *,
    db_path: str | Path | None = None,
) -> DeadLetterQueue:
    """Return a durable DLQ unless TRADEX_DLQ_MEMORY=1 (tests)."""
    import os

    if os.environ.get("TRADEX_DLQ_MEMORY") == "1":
        return DeadLetterQueue(max_size=max_size)
    return PersistentDeadLetterQueue(max_size=max_size, db_path=db_path)
