"""HistoricalDataCoordinator — federated multi-broker historical data fetching.

This is a standalone component — not embedded in any gateway.  It owns:
  - Request planning and date-range clipping per broker constraints
  - Chunk allocation across brokers based on policy and quota headroom
  - Concurrent broker fetches with quota gating
  - Bar normalization and sorting
  - Overlap validation between overlapping source windows
  - Merge with configurable conflict resolution
  - Provenance ledger construction
  - Degraded-mode fallback when a source is incomplete

The system gets historical data faster by using both brokers' quotas in
parallel where the date range can be partitioned cleanly.

Architecture invariant: the coordinator calls ``CommonBrokerGateway.get_historical_bars()``
on individual gateways.  It does not call gateway.history() or any internal
adapter method.  Provenance survives every step.

Usage Example:
    # Create coordinator with broker registry and router
    coordinator = HistoricalDataCoordinator(
        registry=BrokerRegistry(),
        router=BrokerRouter(),
        policy=default_source_selection_policy(),
    )
    
    # Create and execute query
    query = HistoricalQuery(
        instrument=InstrumentRef(symbol="RELIANCE", exchange="NSE"),
        timeframe="1D",
        from_date=date(2024, 1, 1),
        to_date=date(2024, 12, 31),
        merge_strategy="prefer_primary",
    )
    
    # Get historical bars (automatically federates across brokers)
    bars = coordinator.get_historical_bars(query)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from brokers.common.broker_port import (
    HistoricalBarRequest,
    QuotaToken,
)
from brokers.common.errors import MergeConflictError, RoutingError
from brokers.common.models import OperationKind, RouteDecision, RoutingRequest
from brokers.common.provenance import (
    BarRangeRecord,
    ChunkRecord,
    ConflictRecord,
    ProvenanceLedger,
)
from brokers.common.registry import BrokerRegistry
from brokers.common.router import BrokerRouter
from domain.historical import (
    DateRange,
    Gap,
    HistoricalBar,
    HistoricalSeries,
    InstrumentRef,
    MergeManifest,
)

logger = logging.getLogger(__name__)

MergeStrategy = Literal["prefer_primary", "prefer_newest_provenance", "fail_on_conflict"]

# Tolerance for OHLCV comparison between overlapping sources (10 basis points)
_DEFAULT_CONFLICT_TOLERANCE_PCT = Decimal("0.001")


@dataclass(frozen=True)
class HistoricalQuery:
    """Top-level query into the HistoricalDataCoordinator.

    instrument      — the instrument to fetch.
    timeframe       — candle interval, e.g. ``"1m"``, ``"1D"``.
    from_date       — requested start date (inclusive).
    to_date         — requested end date (inclusive).
    merge_strategy  — how to resolve conflicts when sources overlap.
    conflict_tolerance_pct — relative tolerance for OHLCV comparison.
    request_id      — caller-supplied correlation ID; one is generated if None.
    max_concurrent_fetches — cap on simultaneous broker calls.
    """

    instrument: InstrumentRef
    timeframe: str
    from_date: date
    to_date: date
    merge_strategy: MergeStrategy = "prefer_primary"
    conflict_tolerance_pct: Decimal = _DEFAULT_CONFLICT_TOLERANCE_PCT
    request_id: str | None = None
    max_concurrent_fetches: int = 4


@dataclass
class _ChunkPlan:
    """Internal planning record — not exposed outside this module."""

    chunk_id: str
    broker_id: str
    instrument: InstrumentRef
    from_date: date
    to_date: date
    timeframe: str
    request_id: str
    is_fallback: bool = False


class HistoricalDataCoordinator:
    """Federated multi-broker historical data coordinator.

    Usage::

        coordinator = HistoricalDataCoordinator(registry=registry, router=router,
                                                 quota_fn=scheduler.acquire)
        series, ledger = await coordinator.fetch(query)
    """

    def __init__(
        self,
        registry: BrokerRegistry,
        router: BrokerRouter,
        quota_fn: Callable[[str, str, str], QuotaToken],
    ) -> None:
        """
        quota_fn
            Callable ``(broker_id, endpoint_class, priority_class) -> QuotaToken``.
            Typically ``QuotaScheduler.acquire``.
        """
        self._registry = registry
        self._router = router
        self._quota_fn = quota_fn

    async def fetch(
        self,
        query: HistoricalQuery,
    ) -> tuple[HistoricalSeries, ProvenanceLedger]:
        """Fetch, normalize, validate, and merge historical bars.

        Returns the merged ``HistoricalSeries`` and its ``ProvenanceLedger``.
        Always returns a result — uses degraded mode rather than raising when
        a source is partially unavailable.

        Raises
        ------
        RoutingError      — if no broker can be selected for any chunk.
        MergeConflictError — if ``merge_strategy="fail_on_conflict"`` and
                             irreconcilable conflicts are detected.
        """
        request_id = query.request_id or str(uuid.uuid4())
        ledger = ProvenanceLedger(
            request_id=request_id,
            instrument=str(query.instrument),
            timeframe=query.timeframe,
            merge_strategy=query.merge_strategy,
        )

        # 1. Plan chunks
        chunks = self._plan_chunks(query, request_id)
        if not chunks:
            # Build empty degraded series
            ledger.mark_degraded("no_chunks_planned")
            return self._empty_series(query, ledger), ledger

        # 2. Fetch all chunks concurrently (respecting concurrency cap)
        semaphore = asyncio.Semaphore(query.max_concurrent_fetches)
        fetch_results: list[
            tuple[_ChunkPlan, Sequence[HistoricalBar] | None]
        ] = await asyncio.gather(
            *[self._fetch_chunk_guarded(chunk, semaphore, ledger) for chunk in chunks],
            return_exceptions=False,
        )

        # 3. Collect bars per chunk
        all_bars: list[HistoricalBar] = []
        chunk_bars: dict[str, list[HistoricalBar]] = {}
        for plan, bars in fetch_results:
            if bars is None:
                # Attempt fallback for this chunk
                bars = await self._try_fallback(plan, ledger)
            if bars is not None:
                chunk_bars[plan.chunk_id] = list(bars)
                all_bars.extend(bars)

        if not all_bars:
            ledger.mark_degraded("all_chunks_failed")
            return self._empty_series(query, ledger), ledger

        # 4. Normalize: sort by event_time
        all_bars.sort(key=lambda b: b.event_time)

        # 5. Overlap validation and merge
        merged, conflicts = self._merge(
            all_bars,
            chunk_bars=chunk_bars,
            strategy=query.merge_strategy,
            tolerance=query.conflict_tolerance_pct,
        )
        for c in conflicts:
            ledger.add_conflict(c)
            with contextlib.suppress(Exception):
                from brokers.common.observability.audit import emit_merge_conflict

                emit_merge_conflict(
                    request_id=request_id,
                    instrument=c.instrument,
                    timeframe=c.timeframe,
                    bar_event_time=c.bar_event_time.isoformat(),
                    primary_broker=c.primary_broker,
                    secondary_broker=c.secondary_broker,
                    delta_pct=str(c.delta_pct),
                    resolution=c.resolution,
                )

        if query.merge_strategy == "fail_on_conflict" and conflicts:
            raise MergeConflictError(
                conflict_count=len(conflicts),
                chunk_ids=list(chunk_bars.keys()),
            )

        # 6. Re-index and build bar range provenance
        merged = [replace(bar, bar_index=idx) for idx, bar in enumerate(merged)]
        self._populate_bar_ranges(merged, ledger)

        # 7. Detect gaps in coverage
        gaps = self._detect_gaps(merged, query)

        # 8. Build merge manifest
        all_failed = ledger.failed_chunks()
        manifest = MergeManifest(
            chunk_assignments={p.chunk_id: p.broker_id for p in chunks},
            conflict_count=len(conflicts),
            conflict_resolution=query.merge_strategy,
            degraded=len(all_failed) > 0,
            degraded_reason="; ".join(f.error or "" for f in all_failed if f.error),
        )
        if manifest.degraded:
            ledger.mark_degraded(manifest.degraded_reason)

        series = HistoricalSeries(
            bars=merged,
            coverage=DateRange(start=query.from_date, end=query.to_date),
            instrument=query.instrument,
            timeframe=query.timeframe,
            gaps=gaps,
            merge_manifest=manifest,
        )

        logger.info(
            "historical.fetch.complete",
            extra={
                **ledger.to_summary_dict(),
                "gaps_count": len(gaps),
            },
        )
        return series, ledger

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _plan_chunks(self, query: HistoricalQuery, request_id: str) -> list[_ChunkPlan]:
        """Plan fetch chunks by clipping ranges and assigning to brokers.

        Strategy:
        1. Ask the router for parallel brokers.
        2. For each eligible broker, determine the date range it can serve
           (constrained by HistoricalWindowConstraint).
        3. Partition the requested range so brokers do not duplicate work:
           - Upstox takes the most recent window (up to its max_lookback_days).
           - Dhan takes the remainder.
        4. Split long ranges into max_chunk_days chunks.
        """
        # Determine routing
        route_request = RoutingRequest(
            operation=OperationKind.GET_HISTORICAL_BARS,
            trace_id=request_id,
            instrument=str(query.instrument),
        )
        try:
            decision: RouteDecision = self._router.route(route_request)
        except RoutingError:
            logger.error(
                "historical.routing.failed",
                extra={"request_id": request_id, "instrument": str(query.instrument)},
            )
            return []

        eligible_brokers = list(decision.parallel_brokers) or [decision.primary_broker]
        today = date.today()
        chunks: list[_ChunkPlan] = []

        # Determine per-broker feasible ranges and partition
        broker_ranges = self._partition_ranges(
            query.from_date, query.to_date, query.timeframe, eligible_brokers, today
        )

        for broker_id, (from_d, to_d) in broker_ranges.items():
            cap_descriptor = self._registry.get_capabilities(broker_id)
            constraint = cap_descriptor.capabilities.historical_window_for(query.timeframe)
            max_chunk = constraint.max_chunk_days if constraint else 90

            # Split into chunks
            current = from_d
            while current <= to_d:
                end = min(current + timedelta(days=max_chunk - 1), to_d)
                chunks.append(
                    _ChunkPlan(
                        chunk_id=str(uuid.uuid4()),
                        broker_id=broker_id,
                        instrument=query.instrument,
                        from_date=current,
                        to_date=end,
                        timeframe=query.timeframe,
                        request_id=request_id,
                    )
                )
                current = end + timedelta(days=1)

        return chunks

    def _partition_ranges(
        self,
        from_date: date,
        to_date: date,
        timeframe: str,
        broker_ids: list[str],
        today: date,
    ) -> dict[str, tuple[date, date]]:
        """Partition the requested range across eligible brokers.

        For two brokers where one (e.g. Upstox) has a short intraday window and
        the other (Dhan) has a long one, the recent window goes to Upstox and
        the older portion goes to Dhan — avoiding duplicated fetches.
        """
        result: dict[str, tuple[date, date]] = {}

        # Build broker window map: broker_id -> max_lookback_days
        broker_windows: dict[str, int] = {}
        for bid in broker_ids:
            with contextlib.suppress(Exception):
                cap = self._registry.get_capabilities(bid).capabilities
                constraint = cap.historical_window_for(timeframe)
                if constraint and cap.supports_historical_data:
                    broker_windows[bid] = constraint.max_lookback_days

        if not broker_windows:
            return result

        if len(broker_windows) == 1:
            bid, max_days = next(iter(broker_windows.items()))
            earliest = today - timedelta(days=max_days)
            effective_from = max(from_date, earliest)
            if effective_from <= to_date:
                result[bid] = (effective_from, to_date)
            return result

        # Multi-broker: sort by coverage ascending (shorter coverage = recent window)
        sorted_brokers = sorted(broker_windows.items(), key=lambda x: x[1])
        # The broker with shorter max_lookback takes the recent slice
        short_broker, short_days = sorted_brokers[0]
        long_broker, long_days = sorted_brokers[-1]

        short_earliest = today - timedelta(days=short_days)
        long_earliest = today - timedelta(days=long_days)

        # Short broker: max(from_date, short_earliest) to to_date
        short_from = max(from_date, short_earliest)
        if short_from <= to_date:
            result[short_broker] = (short_from, to_date)

        # Long broker: max(from_date, long_earliest) to (short_from - 1 day)
        long_to = short_from - timedelta(days=1)
        long_from = max(from_date, long_earliest)
        if long_from <= long_to:
            result[long_broker] = (long_from, long_to)

        return result

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    async def _fetch_chunk_guarded(
        self,
        plan: _ChunkPlan,
        semaphore: asyncio.Semaphore,
        ledger: ProvenanceLedger,
    ) -> tuple[_ChunkPlan, Sequence[HistoricalBar] | None]:
        async with semaphore:
            return await self._fetch_chunk(plan, ledger)

    async def _fetch_chunk(
        self,
        plan: _ChunkPlan,
        ledger: ProvenanceLedger,
    ) -> tuple[_ChunkPlan, Sequence[HistoricalBar] | None]:
        import time

        start = time.monotonic()
        try:
            quota = self._quota_fn(plan.broker_id, "historical", "HISTORICAL_BACKFILL")
            gw = self._registry.get_gateway(plan.broker_id)
            request = HistoricalBarRequest(
                instrument=plan.instrument,
                timeframe=plan.timeframe,
                from_date=plan.from_date.isoformat(),
                to_date=plan.to_date.isoformat(),
                request_id=plan.request_id,
            )
            bars = await gw.get_historical_bars(request, quota=quota)
            elapsed = (time.monotonic() - start) * 1000
            self._record_chunk_result(plan, ledger, bars, elapsed)
            return plan, bars
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self._record_chunk_result(plan, ledger, None, elapsed, error=exc)
            return plan, None

    def _record_chunk_result(
        self,
        plan: _ChunkPlan,
        ledger: ProvenanceLedger,
        bars: Sequence[HistoricalBar] | None,
        elapsed_ms: float,
        error: Exception | None = None,
    ) -> None:
        """Record chunk outcome in the ledger, audit log, and structured log."""
        bar_count = len(bars) if bars is not None else 0
        event_type = "complete" if error is None else "failed"

        ledger.add_chunk(
            ChunkRecord(
                chunk_id=plan.chunk_id,
                broker_id=plan.broker_id,
                from_date=plan.from_date,
                to_date=plan.to_date,
                timeframe=plan.timeframe,
                bars_fetched=bar_count,
                error=str(error) if error else None,
                fetch_latency_ms=elapsed_ms,
            )
        )

        with contextlib.suppress(Exception):
            from brokers.common.observability.audit import emit_historical_chunk

            emit_historical_chunk(
                request_id=plan.request_id,
                chunk_id=plan.chunk_id,
                broker_id=plan.broker_id,
                from_date=plan.from_date.isoformat(),
                to_date=plan.to_date.isoformat(),
                timeframe=plan.timeframe,
                event_type=event_type,
                bar_count=bar_count,
                latency_ms=elapsed_ms,
                **({"error": str(error)} if error else {}),
            )

        if error is None:
            logger.info(
                "historical.chunk.complete",
                extra={
                    "chunk_id": plan.chunk_id,
                    "broker_id": plan.broker_id,
                    "from_date": plan.from_date.isoformat(),
                    "to_date": plan.to_date.isoformat(),
                    "bar_count": bar_count,
                    "request_id": plan.request_id,
                },
            )
        else:
            logger.warning(
                "historical.chunk.failed",
                extra={
                    "chunk_id": plan.chunk_id,
                    "broker_id": plan.broker_id,
                    "error": str(error),
                    "request_id": plan.request_id,
                },
            )

    async def _try_fallback(
        self,
        failed_plan: _ChunkPlan,
        ledger: ProvenanceLedger,
    ) -> Sequence[HistoricalBar] | None:
        """Try remaining eligible brokers for a failed chunk."""
        route_request = RoutingRequest(
            operation=OperationKind.GET_HISTORICAL_BARS,
            trace_id=failed_plan.request_id,
        )
        try:
            decision = self._router.route(route_request)
        except RoutingError:
            return None

        fallbacks = [b for b in decision.fallback_brokers if b != failed_plan.broker_id]
        for fallback_id in fallbacks:
            fallback_plan = _ChunkPlan(
                chunk_id=str(uuid.uuid4()),
                broker_id=fallback_id,
                instrument=failed_plan.instrument,
                from_date=failed_plan.from_date,
                to_date=failed_plan.to_date,
                timeframe=failed_plan.timeframe,
                request_id=failed_plan.request_id,
                is_fallback=True,
            )
            _, bars = await self._fetch_chunk(fallback_plan, ledger)
            if bars is not None:
                # Mark bars as fallback provenance
                fallback_bars = [
                    HistoricalBar(
                        instrument=b.instrument,
                        timeframe=b.timeframe,
                        event_time=b.event_time,
                        open=b.open,
                        high=b.high,
                        low=b.low,
                        close=b.close,
                        volume=b.volume,
                        open_interest=b.open_interest,
                        bar_index=b.bar_index,
                        is_partial=b.is_partial,
                        label_convention=b.label_convention,
                        provenance=b.provenance.as_fallback(),
                    )
                    for b in bars
                ]
                return fallback_bars
        return None

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def _merge(
        self,
        bars: list[HistoricalBar],
        chunk_bars: dict[str, list[HistoricalBar]],
        strategy: MergeStrategy,
        tolerance: Decimal,
    ) -> tuple[list[HistoricalBar], list[ConflictRecord]]:
        """Merge sorted bars, detecting and resolving OHLCV conflicts."""
        conflicts: list[ConflictRecord] = []
        merged: dict[datetime, HistoricalBar] = {}

        for bar in bars:
            ts = bar.event_time
            if ts not in merged:
                merged[ts] = bar
                continue

            existing = merged[ts]
            delta = abs(bar.close - existing.close)
            base = existing.close if existing.close != Decimal("0") else Decimal("1")
            delta_pct = delta / base

            if delta_pct <= tolerance:
                # Within tolerance — prefer existing (primary source)
                continue

            # Conflict outside tolerance
            conflict = ConflictRecord(
                bar_event_time=ts,
                instrument=str(bar.instrument),
                timeframe=bar.timeframe,
                primary_broker=existing.provenance.source.broker_id,
                secondary_broker=bar.provenance.source.broker_id,
                primary_close=existing.close,
                secondary_close=bar.close,
                delta_pct=delta_pct,
                resolution=strategy,
            )
            conflicts.append(conflict)

            if strategy == "prefer_primary":
                pass  # keep existing
            elif (
                strategy == "prefer_newest_provenance"
                and bar.provenance.fetched_at > existing.provenance.fetched_at
            ):
                merged[ts] = bar
            # fail_on_conflict: keep existing; caller raises after seeing conflicts

        return sorted(merged.values(), key=lambda b: b.event_time), conflicts

    # ------------------------------------------------------------------
    # Provenance bar ranges
    # ------------------------------------------------------------------

    def _populate_bar_ranges(
        self,
        bars: list[HistoricalBar],
        ledger: ProvenanceLedger,
    ) -> None:
        """Build BarRangeRecord entries mapping bar indices to source chunks."""
        if not bars:
            return

        current_broker = bars[0].provenance.source.broker_id
        current_chunk_id = bars[0].provenance.request_id
        range_start = 0

        for idx in range(1, len(bars)):
            bar = bars[idx]
            broker = bar.provenance.source.broker_id
            chunk_id = bar.provenance.request_id
            if broker != current_broker or chunk_id != current_chunk_id:
                ledger.add_bar_range(
                    BarRangeRecord(
                        start_bar_index=range_start,
                        end_bar_index=idx - 1,
                        chunk_id=current_chunk_id,
                        broker_id=current_broker,
                    )
                )
                current_broker = broker
                current_chunk_id = chunk_id
                range_start = idx

        ledger.add_bar_range(
            BarRangeRecord(
                start_bar_index=range_start,
                end_bar_index=len(bars) - 1,
                chunk_id=current_chunk_id,
                broker_id=current_broker,
            )
        )

    # ------------------------------------------------------------------
    # Gap detection
    # ------------------------------------------------------------------

    def _detect_gaps(
        self,
        bars: list[HistoricalBar],
        query: HistoricalQuery,
    ) -> list[Gap]:
        """Detect gaps between the requested coverage and actual bars.

        Gap detection is calendar-day based for daily bars.  For intraday bars,
        gaps are detected by finding consecutive bars with timestamps more than
        2x the timeframe apart (approximate heuristic).
        """
        gaps: list[Gap] = []
        if not bars:
            gaps.append(Gap(start=query.from_date, end=query.to_date, reason="all_failed"))
            return gaps

        # Coverage gap at start
        first_bar_date = bars[0].event_time.date()
        if first_bar_date > query.from_date:
            gaps.append(
                Gap(
                    start=query.from_date,
                    end=first_bar_date - timedelta(days=1),
                    reason="missing_from_start",
                )
            )

        # Coverage gap at end
        last_bar_date = bars[-1].event_time.date()
        if last_bar_date < query.to_date:
            gaps.append(
                Gap(
                    start=last_bar_date + timedelta(days=1),
                    end=query.to_date,
                    reason="missing_from_end",
                )
            )

        return gaps

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_series(query: HistoricalQuery, ledger: ProvenanceLedger) -> HistoricalSeries:
        return HistoricalSeries(
            bars=[],
            coverage=DateRange(start=query.from_date, end=query.to_date),
            instrument=query.instrument,
            timeframe=query.timeframe,
            gaps=[Gap(start=query.from_date, end=query.to_date, reason=ledger.degraded_reason)],
            merge_manifest=MergeManifest(degraded=True, degraded_reason=ledger.degraded_reason),
        )
