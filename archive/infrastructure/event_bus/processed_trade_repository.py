"""Idempotency ledger for trade events.

A ``trade`` from a broker is the most dangerous event in the system:
double-processing it doubles a position, which loses money.

The :class:`ProcessedTradeRepository` records every trade id we have
already accepted and rejects duplicates with a loud, observable outcome.

Storage
-------
Two layers, both thread-safe:

1. **In-memory** (always): ``set[TradeIdKey]`` for fast lookups.
2. **Persistent** (optional): a JSONL file append-only, fsynced on
   write. Replayed at startup so restarts don't reintroduce duplicates.

Key construction
----------------
A trade is identified by **two** ids when the broker provides them
(``trade_id`` + ``broker_trade_id``), falling back to just the broker
``trade_id`` otherwise. Constructing the key defensively means a
malformed payload cannot sneak past the dedup check.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from domain.constants import (
    DEFAULT_STOP_TIMEOUT_SECONDS,
    PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS,
    PROCESSED_TRADE_RETENTION_SECONDS,
)
from domain.lifecycle_health import HealthState, HealthStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradeIdKey:
    """Canonical identifier for a trade.

    Two trades are considered the same if and only if their
    :class:`TradeIdKey` compares equal.
    """

    trade_id: str
    broker_trade_id: str | None = None
    order_id: str | None = None

    def __post_init__(self) -> None:
        if not self.trade_id:
            raise ValueError("TradeIdKey requires a non-empty trade_id")
        # Defensive normalisation.
        object.__setattr__(self, "trade_id", str(self.trade_id).strip())
        if self.broker_trade_id is not None:
            object.__setattr__(self, "broker_trade_id", str(self.broker_trade_id).strip())
        if self.order_id is not None:
            object.__setattr__(self, "order_id", str(self.order_id).strip())

    @classmethod
    def from_trade(cls, trade: Any) -> TradeIdKey:
        """Build a key from a domain ``Trade`` (or any duck-typed object)."""
        trade_id = getattr(trade, "trade_id", "") or ""
        broker_trade_id = (
            getattr(trade, "broker_trade_id", None)
            or getattr(trade, "exchange_trade_id", None)
            or None
        )
        order_id = getattr(trade, "order_id", None) or None
        return cls(
            trade_id=trade_id,
            broker_trade_id=broker_trade_id,
            order_id=order_id,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TradeIdKey:
        """Build a key from a raw event payload ``{"trade": Trade(...)}``."""
        trade = payload.get("trade")
        if trade is not None:
            return cls.from_trade(trade)
        return cls(
            trade_id=str(payload.get("trade_id", "")),
            broker_trade_id=payload.get("broker_trade_id"),
            order_id=payload.get("order_id"),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "trade_id": self.trade_id,
            "broker_trade_id": self.broker_trade_id,
            "order_id": self.order_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TradeIdKey:
        return cls(
            trade_id=str(raw.get("trade_id", "")),
            broker_trade_id=raw.get("broker_trade_id"),
            order_id=raw.get("order_id"),
        )


class ProcessedTradeRepository:
    """Idempotency ledger for trade events.

    Singleton Pattern (P0.6)
    ------------------------
    This class enforces a singleton pattern per persistence path to prevent
    duplicate trade processing and idempotency failures. Use :meth:`get_instance`
    to obtain the canonical instance for a given persistence path.

    Parameters
    ----------
    persistence_path:
        Optional path to a JSONL file used to durably record every
        processed trade. When omitted, the ledger is in-memory only.
    on_duplicate:
        Optional callback invoked when a duplicate is detected. Useful
        for emitting a metric without coupling this class to a metrics
        implementation.
    max_age_seconds:
        Maximum age in seconds for in-memory entries. Entries older than
        this are evicted during cleanup. Default: 86400 (24 hours).
        Set to 0 to disable eviction.
    """

    # P0.6: Singleton registry - one instance per persistence path
    _instances: ClassVar[dict[str, ProcessedTradeRepository]] = {}
    _singleton_lock: ClassVar[threading.Lock] = threading.Lock()  # Thread-safe singleton creation

    @classmethod
    def get_instance(
        cls,
        persistence_path: str | Path | None = None,
        on_duplicate=None,
        max_age_seconds: int = PROCESSED_TRADE_RETENTION_SECONDS,
    ) -> ProcessedTradeRepository:
        """Get or create the canonical singleton instance for a persistence path.

        This method enforces that only ONE instance exists per persistence path,
        preventing duplicate trade processing and idempotency failures.

        Parameters
        ----------
        persistence_path:
            Optional path to a JSONL file. Different paths create different
            instances. When omitted, uses the 'default' instance.
        on_duplicate:
            Optional callback for duplicate detection (only used when creating
            a new instance).
        max_age_seconds:
            Maximum age for in-memory entries (only used when creating a new
            instance).

        Returns
        -------
        ProcessedTradeRepository
            The canonical instance for the given persistence path.

        Thread Safety
        -------------
        This method is thread-safe. Multiple threads calling get_instance()
        concurrently will receive the same instance for the same path.

        Examples
        --------
        >>> # Get the default instance
        >>> repo1 = ProcessedTradeRepository.get_instance()
        >>> repo2 = ProcessedTradeRepository.get_instance()
        >>> repo1 is repo2  # Same instance
        True

        >>> # Different paths create different instances
        >>> repo_a = ProcessedTradeRepository.get_instance(persistence_path="/tmp/a.jsonl")
        >>> repo_b = ProcessedTradeRepository.get_instance(persistence_path="/tmp/b.jsonl")
        >>> repo_a is repo_b  # Different instances
        False
        """
        key = str(persistence_path) if persistence_path else "default"

        # Fast path: check without lock (common case)
        if key in cls._instances:
            return cls._instances[key]

        # Slow path: create with lock (thread-safe)
        with cls._singleton_lock:
            # Double-check after acquiring lock
            if key not in cls._instances:
                cls._instances[key] = cls(
                    persistence_path=persistence_path,
                    on_duplicate=on_duplicate,
                    max_age_seconds=max_age_seconds,
                )
            return cls._instances[key]

    @classmethod
    def clear_instances(cls) -> None:
        """Clear all singleton instances from the registry.

        This method is primarily intended for test isolation and long-running
        process health. In production, instances should persist for the
        lifetime of the process.

        Thread Safety
        -------------
        This method is thread-safe. It acquires _singleton_lock before
        clearing the registry.

        Examples
        --------
        >>> # Clear all instances (e.g., between tests)
        >>> ProcessedTradeRepository.clear_instances()
        >>> ProcessedTradeRepository.get_instance() is ProcessedTradeRepository.get_instance()
        True  # New instance created
        """
        with cls._singleton_lock:
            cls._instances.clear()

    @classmethod
    def get_instance_count(cls) -> int:
        """Return the number of singleton instances currently registered.

        Useful for monitoring and debugging memory leaks.

        Returns
        -------
        int
            Number of instances in the registry.
        """
        return len(cls._instances)

    def __init__(
        self,
        persistence_path: str | Path | None = None,
        on_duplicate=None,
        max_age_seconds: int = PROCESSED_TRADE_RETENTION_SECONDS,
    ) -> None:
        self._lock = threading.RLock()
        self._seen: set[TradeIdKey] = set()
        self._key_timestamps: dict[TradeIdKey, float] = {}
        self._max_age_seconds = max_age_seconds
        self._path = Path(persistence_path) if persistence_path else None
        self._on_duplicate = on_duplicate
        self._duplicates_observed = 0
        self._total_processed = 0
        self._evicted = 0
        # Auto-cleanup state — wired by attach_auto_cleanup().
        self._auto_cleanup_thread: threading.Thread | None = None
        self._auto_cleanup_stop = threading.Event()
        self._auto_cleanup_interval = PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def attach_auto_cleanup(
        self,
        interval_seconds: int = PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS,
    ) -> None:
        """Start a daemon thread that periodically evicts expired entries.

        The thread is named ``processed-trade-cleanup`` and is stopped
        automatically when the process exits (it is a daemon). Callers
        that need deterministic shutdown should call
        :meth:`stop_auto_cleanup` from their lifecycle manager's stop
        path. Idempotent — calling twice is a no-op.
        """
        if self._auto_cleanup_thread and self._auto_cleanup_thread.is_alive():
            return
        if self._max_age_seconds <= 0:
            logger.debug("ProcessedTradeRepository: auto-cleanup disabled (max_age_seconds<=0)")
            return
        self._auto_cleanup_interval = max(1, int(interval_seconds))
        self._auto_cleanup_stop.clear()
        self._auto_cleanup_thread = threading.Thread(
            target=self._auto_cleanup_loop,
            name="processed-trade-cleanup",
            daemon=True,
        )
        self._auto_cleanup_thread.start()
        logger.info(
            "ProcessedTradeRepository: auto-cleanup started (interval=%ds, retention=%ds)",
            self._auto_cleanup_interval,
            self._max_age_seconds,
        )

    def stop_auto_cleanup(self, timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS) -> None:
        """Stop the auto-cleanup thread. Idempotent."""
        if not self._auto_cleanup_thread:
            return
        self._auto_cleanup_stop.set()
        self._auto_cleanup_thread.join(timeout=timeout_seconds)
        if self._auto_cleanup_thread.is_alive():
            logger.warning(
                "ProcessedTradeRepository: auto-cleanup did not stop within %.1fs",
                timeout_seconds,
            )
        else:
            logger.info("ProcessedTradeRepository: auto-cleanup stopped")
        self._auto_cleanup_thread = None

    def health(self) -> HealthStatus:
        """Health snapshot for SRE. Reports the repository's size and
        whether auto-cleanup is running."""
        with self._lock:
            size = len(self._seen)
            detail = f"size={size} max_age={self._max_age_seconds}s"
        if self._auto_cleanup_thread and self._auto_cleanup_thread.is_alive():
            return HealthStatus(
                state=HealthState.HEALTHY,
                service="processed-trade-repository",
                detail=detail + " auto-cleanup=running",
            )
        return HealthStatus(
            state=HealthState.HEALTHY,
            service="processed-trade-repository",
            detail=detail + " auto-cleanup=off",
        )

    def _auto_cleanup_loop(self) -> None:
        """Periodic eviction loop. Uses Event.wait so stop is responsive."""
        try:
            while not self._auto_cleanup_stop.is_set():
                try:
                    self.cleanup()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception(
                        "ProcessedTradeRepository: auto-cleanup iteration failed: %s",
                        exc,
                    )
                if self._auto_cleanup_stop.wait(timeout=self._auto_cleanup_interval):
                    break
        finally:
            logger.debug("ProcessedTradeRepository: auto-cleanup thread exiting")

    # ── Public API ────────────────────────────────────────────────────────

    def is_processed(self, key: TradeIdKey) -> bool:
        with self._lock:
            return key in self._seen

    def mark_processed(self, key: TradeIdKey) -> bool:
        """Record ``key`` as processed.

        Returns True if the key was *new* (caller should apply the trade).
        Returns False if the key was already present (caller MUST skip).
        """
        if not key.trade_id:
            raise ValueError(
                "ProcessedTradeRepository.mark_processed requires a non-empty trade_id"
            )
        import time

        with self._lock:
            if key in self._seen:
                self._duplicates_observed += 1
                if self._on_duplicate is not None:
                    try:
                        self._on_duplicate(key)
                    except Exception:
                        logger.exception("ProcessedTradeRepository: on_duplicate raised")
                logger.info(
                    "ProcessedTradeRepository: duplicate trade %s ignored",
                    key.trade_id,
                )
                return False
            self._seen.add(key)
            self._key_timestamps[key] = time.time()
            self._total_processed += 1
            if self._path is not None:
                self._append_to_disk(key)
            return True

    def process(self, key: TradeIdKey) -> bool:
        """Alias for :meth:`mark_processed`. Returns True on first sight."""
        return self.mark_processed(key)

    def contains(self, key: TradeIdKey) -> bool:
        return self.is_processed(key)

    def size(self) -> int:
        with self._lock:
            return len(self._seen)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._seen),
                "duplicates_observed": self._duplicates_observed,
                "total_processed": self._total_processed,
                "evicted": self._evicted,
            }

    def clear(self) -> None:
        """Wipe in-memory state. Persistence file is left untouched."""
        with self._lock:
            self._seen.clear()
            self._key_timestamps.clear()
            self._duplicates_observed = 0
            self._total_processed = 0

    def cleanup(self) -> int:
        """Evict entries older than max_age_seconds.

        Returns the number of entries evicted.
        """
        if self._max_age_seconds <= 0:
            return 0
        import time

        now = time.time()
        cutoff = now - self._max_age_seconds
        evicted = 0
        with self._lock:
            expired = [k for k, ts in self._key_timestamps.items() if ts < cutoff]
            for key in expired:
                self._seen.discard(key)
                del self._key_timestamps[key]
                evicted += 1
            self._evicted += evicted
        if evicted > 0:
            logger.info(
                "ProcessedTradeRepository: evicted %d expired entries (age>%ds)",
                evicted,
                self._max_age_seconds,
            )
        return evicted

    # ── Persistence ───────────────────────────────────────────────────────

    def _append_to_disk(self, key: TradeIdKey) -> None:
        assert self._path is not None
        record = {
            **key.to_dict(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        line = json.dumps(record, separators=(",", ":"), sort_keys=True)
        # Append-only; crash-safe.
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            with contextlib.suppress(OSError, ValueError):
                os.fsync(f.fileno())
                # Filesystem may not support fsync (e.g. some CI sandboxes).

    def _load_from_disk(self) -> None:
        assert self._path is not None
        if not self._path.exists():
            return
        loaded = 0
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "ProcessedTradeRepository: corrupt line in %s: %s",
                        self._path,
                        exc,
                    )
                    continue
                try:
                    key = TradeIdKey.from_dict(record)
                except ValueError:
                    continue
                self._seen.add(key)
                loaded += 1
        self._total_processed = loaded
        logger.info(
            "ProcessedTradeRepository: loaded %d processed trades from %s",
            loaded,
            self._path,
        )
