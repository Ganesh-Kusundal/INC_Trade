"""ProvenanceLedger — audit record for multi-source historical data merges.

Every federated historical fetch produces a ``ProvenanceLedger`` that answers:
- Which chunks were assigned to which broker?
- Which bar index ranges came from which source?
- Were there any conflicts, and how were they resolved?
- Is the series degraded (partial data)?

This ledger is the audit trail required by the zero-parity rule: backtest,
replay, and live must consume data with identical provenance semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from infrastructure.time_service import time_service


@dataclass(frozen=True)
class ChunkRecord:
    """Audit record for a single fetched chunk.

    chunk_id    — unique identifier for this chunk (used in merge manifests).
    broker_id   — broker that served this chunk.
    from_date   — start of the fetched date range.
    to_date     — end of the fetched date range.
    timeframe   — candle interval fetched.
    bars_fetched — number of bars returned by the broker.
    error       — None on success; error message on failure.
    fetch_latency_ms — how long the broker call took.
    """

    chunk_id: str
    broker_id: str
    from_date: date
    to_date: date
    timeframe: str
    bars_fetched: int
    error: str | None = None
    fetch_latency_ms: float = 0.0
    fetched_at: datetime = field(default_factory=lambda: time_service.now())

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class BarRangeRecord:
    """Maps a bar index range to its source chunk.

    start_bar_index and end_bar_index are inclusive indices into the merged
    ``HistoricalSeries.bars`` list.
    """

    start_bar_index: int
    end_bar_index: int
    chunk_id: str
    broker_id: str


@dataclass(frozen=True)
class ConflictRecord:
    """Describes a single bar-level conflict detected during merge.

    Two or more sources returned different OHLCV values for the same timestamp.
    The resolution field documents which source won.
    """

    bar_event_time: datetime
    instrument: str
    timeframe: str
    primary_broker: str
    secondary_broker: str
    primary_close: Decimal
    secondary_close: Decimal
    delta_pct: Decimal
    resolution: str  # "prefer_primary" | "prefer_newest" | "flagged"


@dataclass
class ProvenanceLedger:
    """Complete audit record for a federated historical fetch.

    chunks         — all fetched chunks (success and failure).
    bar_ranges     — bar index → source chunk mapping in the final merged series.
    conflicts      — all detected OHLCV conflicts between sources.
    merge_strategy — strategy used to resolve conflicts.
    degraded       — True when the series is incomplete due to partial failures.
    degraded_reason — human-readable reason for degradation.
    request_id     — correlation ID from the originating HistoricalQuery.
    """

    request_id: str
    instrument: str
    timeframe: str
    chunks: list[ChunkRecord] = field(default_factory=list)
    bar_ranges: list[BarRangeRecord] = field(default_factory=list)
    conflicts: list[ConflictRecord] = field(default_factory=list)
    merge_strategy: str = "prefer_primary"
    degraded: bool = False
    degraded_reason: str = ""
    created_at: datetime = field(default_factory=lambda: time_service.now())

    def add_chunk(self, chunk: ChunkRecord) -> None:
        self.chunks.append(chunk)

    def add_bar_range(self, record: BarRangeRecord) -> None:
        self.bar_ranges.append(record)

    def add_conflict(self, conflict: ConflictRecord) -> None:
        self.conflicts.append(conflict)

    def mark_degraded(self, reason: str) -> None:
        self.degraded = True
        self.degraded_reason = reason

    def brokers_used(self) -> set[str]:
        return {c.broker_id for c in self.chunks if c.succeeded}

    def failed_chunks(self) -> list[ChunkRecord]:
        return [c for c in self.chunks if not c.succeeded]

    def total_bars(self) -> int:
        return sum(c.bars_fetched for c in self.chunks if c.succeeded)

    def to_summary_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "brokers_used": list(self.brokers_used()),
            "chunks_total": len(self.chunks),
            "chunks_failed": len(self.failed_chunks()),
            "total_bars": self.total_bars(),
            "conflict_count": len(self.conflicts),
            "merge_strategy": self.merge_strategy,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
        }
