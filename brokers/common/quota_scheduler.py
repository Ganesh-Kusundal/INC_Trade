"""QuotaScheduler — global API quota coordination across all brokers.

Per-gateway throttling (rate limiters in each broker adapter) is necessary but
insufficient.  The QuotaScheduler provides global coordination so that:

1. Execution-critical traffic always has reserved headroom.
2. Historical backfill and enrichment cannot starve execution quota.
3. Quota state is observable in real time for alerting and dashboards.
4. Adding a new broker requires only registering its rate profiles — no
   changes to coordinator or orchestrator code.

Design
------
Each (broker_id, endpoint_class) pair has a token bucket.  Tokens refill at
the sustained rate.  A reserved headroom fraction is held exclusively for
EXECUTION_CRITICAL priority.  Lower-priority callers can only use non-reserved
capacity.

Token bucket mechanics:
- Tokens accumulate at ``sustained_rps`` up to ``burst_capacity``.
- When a request arrives, one token is consumed.
- If capacity < 1 token: THROTTLE (queue with deadline) or REJECT (hard).

Priority semantics:
- EXECUTION_CRITICAL — may use reserved + non-reserved capacity.
- LIVE_STREAM_CONTROL — non-reserved capacity; never queued, always reject on
  exhaustion (stream control must be immediate).
- PORTFOLIO_READ — non-reserved with short queue (5s deadline).
- HISTORICAL_BACKFILL — non-reserved with long queue (60s deadline).
- ENRICHMENT — non-reserved; lowest priority; soft reject on pressure.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import ClassVar

from brokers.common.broker_port import QuotaToken
from brokers.common.capabilities import RateLimitProfile
from brokers.common.errors import QuotaExhaustedError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Priority classification
# ---------------------------------------------------------------------------


class PriorityClass(IntEnum):
    """Priority order — lower value = higher priority."""

    EXECUTION_CRITICAL = 0
    LIVE_STREAM_CONTROL = 1
    PORTFOLIO_READ = 2
    HISTORICAL_BACKFILL = 3
    ENRICHMENT = 4


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------


class _TokenBucket:
    """Thread-safe token bucket with reserved headroom.

    sustained_rate   — tokens per second (refill rate).
    burst_capacity   — maximum tokens that can accumulate.
    reserved_headroom — fraction of burst_capacity held for EXECUTION_CRITICAL.
    """

    def __init__(
        self,
        sustained_rate: float,
        burst_capacity: float,
        reserved_headroom: float = 0.20,
    ) -> None:
        self._rate = sustained_rate
        self._capacity = burst_capacity
        self._reserved_headroom = reserved_headroom
        self._tokens: float = burst_capacity
        self._last_refill: float = time.monotonic()
        self._lock = threading.Lock()

    @property
    def _reserved_tokens(self) -> float:
        return self._capacity * self._reserved_headroom

    @property
    def _non_reserved_tokens(self) -> float:
        return self._capacity - self._reserved_tokens

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def try_acquire(self, priority: PriorityClass) -> bool:
        """Attempt to consume one token.  Returns True if successful."""
        with self._lock:
            self._refill()
            if priority == PriorityClass.EXECUTION_CRITICAL:
                # Can use all capacity including reserved
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                return False
            else:
                # Non-critical: only non-reserved capacity
                available = max(0.0, self._tokens - self._reserved_tokens)
                if available >= 1.0:
                    self._tokens -= 1.0
                    return True
                return False

    def available_tokens(self, for_priority: PriorityClass) -> float:
        """Return available tokens for the given priority (for observability)."""
        with self._lock:
            self._refill()
            if for_priority == PriorityClass.EXECUTION_CRITICAL:
                return max(0.0, self._tokens)
            return max(0.0, self._tokens - self._reserved_tokens)

    def utilization_ratio(self) -> float:
        """Return fraction of capacity that is consumed (0.0 = full, 1.0 = empty)."""
        with self._lock:
            self._refill()
            return 1.0 - (self._tokens / self._capacity) if self._capacity > 0 else 1.0


# ---------------------------------------------------------------------------
# Quota metrics (in-process; export to Prometheus via observability layer)
# ---------------------------------------------------------------------------


@dataclass
class QuotaBucketMetrics:
    """Point-in-time metrics snapshot for one bucket."""

    broker_id: str
    endpoint_class: str
    tokens_available: float
    capacity: float
    utilization_ratio: float
    sustained_rate: float


# ---------------------------------------------------------------------------
# QuotaScheduler
# ---------------------------------------------------------------------------


class QuotaScheduler:
    """Global API quota coordinator.

    Usage::

        scheduler = QuotaScheduler()
        scheduler.register_profile("dhan", RateLimitProfile(
            endpoint_class="orders", sustained_rps=25.0, ...
        ))

        token = scheduler.acquire("dhan", "orders", "EXECUTION_CRITICAL")
        try:
            result = await gateway.place_order(request, quota=token)
        finally:
            scheduler.release(token)

    Alternatively use as async context manager::

        async with scheduler.borrow("dhan", "historical", "HISTORICAL_BACKFILL") as token:
            bars = await gateway.get_historical_bars(request, quota=token)
    """

    _WAIT_INTERVALS_S: ClassVar[float] = 0.05  # polling granularity when waiting for a token

    # Max wait times per priority (seconds)
    _MAX_WAIT: ClassVar[dict[int, float]] = {
        PriorityClass.EXECUTION_CRITICAL: 2.0,
        PriorityClass.LIVE_STREAM_CONTROL: 0.0,  # reject immediately
        PriorityClass.PORTFOLIO_READ: 5.0,
        PriorityClass.HISTORICAL_BACKFILL: 60.0,
        PriorityClass.ENRICHMENT: 10.0,
    }

    def __init__(self, reserved_headroom: float = 0.20) -> None:
        self._reserved_headroom = reserved_headroom
        self._buckets: dict[tuple[str, str], _TokenBucket] = {}
        self._lock = threading.Lock()
        self._metrics_callbacks: list[Callable[[QuotaBucketMetrics], None]] = []

    def register_profile(
        self,
        broker_id: str,
        profile: RateLimitProfile,
    ) -> None:
        """Register a rate limit profile for (broker_id, endpoint_class)."""
        key = (broker_id, profile.endpoint_class)
        burst = profile.burst_rps or profile.sustained_rps * 2
        with self._lock:
            self._buckets[key] = _TokenBucket(
                sustained_rate=profile.sustained_rps,
                burst_capacity=burst,
                reserved_headroom=self._reserved_headroom,
            )
        logger.debug(
            "quota.profile.registered",
            extra={
                "broker_id": broker_id,
                "endpoint_class": profile.endpoint_class,
                "sustained_rps": profile.sustained_rps,
            },
        )

    def acquire(
        self,
        broker_id: str,
        endpoint_class: str,
        priority_class: str | PriorityClass,
    ) -> QuotaToken:
        """Block until a token is available or deadline is reached.

        Raises ``QuotaExhaustedError`` when the wait deadline is exceeded.
        This is a synchronous blocking call — use ``acquire_async()`` from
        async contexts when possible.
        """
        priority = (
            priority_class
            if isinstance(priority_class, PriorityClass)
            else PriorityClass[priority_class]
        )
        max_wait = self._MAX_WAIT.get(int(priority), 10.0)
        deadline = time.monotonic() + max_wait

        bucket = self._get_or_default_bucket(broker_id, endpoint_class)

        while True:
            if bucket.try_acquire(priority):
                token_id = str(uuid.uuid4())
                logger.debug(
                    "quota.acquire",
                    extra={
                        "broker_id": broker_id,
                        "endpoint_class": endpoint_class,
                        "priority": priority.name,
                        "token_id": token_id,
                    },
                )
                with contextlib.suppress(Exception):
                    from brokers.common.observability.audit import emit_quota_event

                    emit_quota_event(
                        broker_id,
                        endpoint_class,
                        priority.name,
                        "acquire",
                        token_id=token_id,
                    )
                return QuotaToken(
                    broker_id=broker_id,
                    endpoint_class=endpoint_class,
                    priority_class=priority.name,
                    token_id=token_id,
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                retry_after = 1.0 / bucket._rate if bucket._rate > 0 else None
                logger.warning(
                    "quota.reject",
                    extra={
                        "broker_id": broker_id,
                        "endpoint_class": endpoint_class,
                        "priority": priority.name,
                        "max_wait_s": max_wait,
                    },
                )
                with contextlib.suppress(Exception):
                    from brokers.common.observability.audit import emit_quota_event

                    emit_quota_event(
                        broker_id,
                        endpoint_class,
                        priority.name,
                        "reject",
                        retry_after_s=retry_after,
                    )
                raise QuotaExhaustedError(
                    broker_id=broker_id,
                    endpoint_class=endpoint_class,
                    priority_class=priority.name,
                    retry_after_seconds=retry_after,
                )

            time.sleep(min(self._WAIT_INTERVALS_S, remaining))

    async def acquire_async(
        self,
        broker_id: str,
        endpoint_class: str,
        priority_class: str | PriorityClass,
    ) -> QuotaToken:
        """Async variant — yields to the event loop while waiting."""
        import asyncio

        priority = (
            priority_class
            if isinstance(priority_class, PriorityClass)
            else PriorityClass[priority_class]
        )
        max_wait = self._MAX_WAIT.get(int(priority), 10.0)
        deadline = time.monotonic() + max_wait
        bucket = self._get_or_default_bucket(broker_id, endpoint_class)

        while True:
            if bucket.try_acquire(priority):
                token_id = str(uuid.uuid4())
                return QuotaToken(
                    broker_id=broker_id,
                    endpoint_class=endpoint_class,
                    priority_class=priority.name,
                    token_id=token_id,
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                retry_after = 1.0 / bucket._rate if bucket._rate > 0 else None
                raise QuotaExhaustedError(
                    broker_id=broker_id,
                    endpoint_class=endpoint_class,
                    priority_class=priority.name,
                    retry_after_seconds=retry_after,
                )

            await asyncio.sleep(min(self._WAIT_INTERVALS_S, remaining))

    def release(self, token: QuotaToken) -> None:
        """Release a token after the request completes.

        Currently a no-op in the token-bucket model (tokens are not held
        during request execution — only at acquisition time).  Retained for
        future in-flight tracking.
        """

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    class _BorrowContext:
        def __init__(
            self,
            scheduler: QuotaScheduler,
            broker_id: str,
            endpoint_class: str,
            priority: PriorityClass,
        ) -> None:
            self._scheduler = scheduler
            self._broker_id = broker_id
            self._endpoint_class = endpoint_class
            self._priority = priority
            self._token: QuotaToken | None = None

        async def __aenter__(self) -> QuotaToken:
            self._token = await self._scheduler.acquire_async(
                self._broker_id, self._endpoint_class, self._priority
            )
            return self._token

        async def __aexit__(self, *_: object) -> None:
            if self._token is not None:
                self._scheduler.release(self._token)

    def borrow(
        self,
        broker_id: str,
        endpoint_class: str,
        priority_class: str | PriorityClass,
    ) -> _BorrowContext:
        """Return an async context manager that acquires and releases a token."""
        priority = (
            priority_class
            if isinstance(priority_class, PriorityClass)
            else PriorityClass[priority_class]
        )
        return self._BorrowContext(self, broker_id, endpoint_class, priority)

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def metrics_snapshot(self) -> list[QuotaBucketMetrics]:
        """Return current metrics for all registered buckets."""
        with self._lock:
            items = list(self._buckets.items())
        result = []
        for (broker_id, endpoint_class), bucket in items:
            result.append(
                QuotaBucketMetrics(
                    broker_id=broker_id,
                    endpoint_class=endpoint_class,
                    tokens_available=bucket.available_tokens(PriorityClass.HISTORICAL_BACKFILL),
                    capacity=bucket._capacity,
                    utilization_ratio=bucket.utilization_ratio(),
                    sustained_rate=bucket._rate,
                )
            )
        return result

    def headroom_for(
        self,
        broker_id: str,
        endpoint_class: str,
    ) -> float:
        """Return the non-reserved headroom fraction (0.0-1.0) for the given bucket.

        Used by the router in quota_aware mode to score candidates.
        """
        bucket = self._buckets.get((broker_id, endpoint_class))
        if bucket is None:
            return 1.0  # Unknown bucket — treat as unlimited
        available = bucket.available_tokens(PriorityClass.HISTORICAL_BACKFILL)
        return available / bucket._capacity if bucket._capacity > 0 else 0.0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_default_bucket(
        self,
        broker_id: str,
        endpoint_class: str,
    ) -> _TokenBucket:
        with self._lock:
            bucket = self._buckets.get((broker_id, endpoint_class))
            if bucket is None:
                # Create a generous default for unregistered profiles
                bucket = _TokenBucket(
                    sustained_rate=10.0,
                    burst_capacity=20.0,
                    reserved_headroom=self._reserved_headroom,
                )
                self._buckets[(broker_id, endpoint_class)] = bucket
        return bucket
