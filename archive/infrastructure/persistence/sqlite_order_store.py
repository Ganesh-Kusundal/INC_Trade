"""SQLite-backed durable order snapshot store.

Single-writer invariant: only one live TradingContext / OrderManager process
should write to a given database path. Horizontal scale requires external
coordination (not supported in-process).

Used to hydrate in-memory OMS state after restart when broker reconciliation
has not yet run.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover — Windows dev environments
    fcntl = None  # type: ignore[assignment]

from domain.entities import Order
from domain.exceptions import TradeXV2Error
from domain.types import OrderStatus, OrderType, ProductType, Side

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("market_data/oms_orders.sqlite")


def _order_to_row(order: Order) -> tuple[Any, ...]:
    return (
        order.order_id,
        order.correlation_id,
        order.symbol,
        order.exchange,
        order.side.value,
        order.order_type.value,
        order.product_type.value,
        order.quantity,
        order.filled_quantity,
        str(order.price),
        str(order.avg_price),
        order.status.value,
        order.timestamp.isoformat() if order.timestamp else None,
        order.reject_reason,
    )


def _row_to_order(row: sqlite3.Row) -> Order:
    ts = row["timestamp"]
    return Order(
        order_id=row["order_id"],
        correlation_id=row["correlation_id"] or "",
        symbol=row["symbol"],
        exchange=row["exchange"],
        side=Side(row["side"]),
        order_type=OrderType(row["order_type"]),
        product_type=ProductType(row["product_type"]),
        quantity=row["quantity"],
        filled_quantity=row["filled_quantity"],
        price=Decimal(row["price"]),
        avg_price=Decimal(row["avg_price"]),
        status=OrderStatus(row["status"]),
        timestamp=datetime.fromisoformat(ts) if ts else None,
        reject_reason=row["reject_reason"],
    )


class OmsWriterLockError(TradeXV2Error):
    """Raised when another process owns the OMS SQLite writer lock."""


class SqliteOrderStore:
    """Append-friendly upsert store for canonical :class:`Order` snapshots."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        require_single_writer: bool | None = None,
    ) -> None:
        self._path = Path(path or _DEFAULT_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._lock_path = Path(str(self._path) + ".lock")
        self._lock_fd: Any | None = None
        _require = (
            require_single_writer
            if require_single_writer is not None
            else os.getenv("PYTEST_CURRENT_TEST") is None
        )
        if _require:
            self._acquire_writer_lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent read performance and crash recovery.
        # WAL allows readers to proceed while a writer is active, which is critical
        # for the OMS single-writer invariant with multiple reader threads.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _acquire_writer_lock(self) -> None:
        if fcntl is None:
            logger.warning("fcntl unavailable — OMS single-writer lock skipped on this platform")
            return
        try:
            self._lock_fd = open(self._lock_path, "w", encoding="utf-8")
            try:
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                # P-1.4 Bug 1: Close FD before raising to prevent leak
                self._lock_fd.close()
                self._lock_fd = None
                raise OmsWriterLockError(
                    f"Another process holds the OMS writer lock at {self._lock_path}. "
                    "Only one live TradingContext may write to this store."
                ) from exc
            self._lock_fd.write(str(os.getpid()))
            self._lock_fd.flush()
        except Exception:
            # P-1.4: Ensure FD is closed on any exception
            if self._lock_fd is not None:
                self._lock_fd.close()
                self._lock_fd = None
            raise

    def writer_lock_held(self) -> bool:
        """True when this process holds the cross-process writer lock."""
        return self._lock_fd is not None

    def lock_path(self) -> Path:
        return self._lock_path

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    correlation_id TEXT,
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    product_type TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    filled_quantity INTEGER NOT NULL,
                    price TEXT NOT NULL,
                    avg_price TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT,
                    reject_reason TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_orders_correlation ON orders(correlation_id)"
            )
            self._conn.commit()

    def upsert(self, order: Order) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO orders (
                    order_id, correlation_id, symbol, exchange, side, order_type,
                    product_type, quantity, filled_quantity, price, avg_price,
                    status, timestamp, reject_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    correlation_id=excluded.correlation_id,
                    filled_quantity=excluded.filled_quantity,
                    avg_price=excluded.avg_price,
                    status=excluded.status,
                    timestamp=excluded.timestamp,
                    reject_reason=excluded.reject_reason
                """,
                _order_to_row(order),
            )
            self._conn.commit()

    def load_all(self) -> list[Order]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM orders").fetchall()
        return [_row_to_order(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
            # P-1.4 Bug 2: Move lock_fd cleanup INSIDE lock to prevent race condition
            if self._lock_fd is not None and fcntl is not None:
                try:
                    fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                finally:
                    self._lock_fd.close()
                    self._lock_fd = None
