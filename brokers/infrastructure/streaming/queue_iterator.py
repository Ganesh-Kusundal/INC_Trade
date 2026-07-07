"""Queue-based AsyncIterator — bridges asyncio.Queue to StreamingPort.

The ``QueueIterator`` wraps an ``asyncio.Queue`` and yields items as they
arrive, implementing the ``AsyncIterator`` protocol required by
``StreamingPort.subscribe_quotes()`` and ``subscribe_orders()``.

When the stream is closed (via ``close()``), iteration stops gracefully.

Usage::

    queue: asyncio.Queue[Quote] = asyncio.Queue(maxsize=1000)
    iterator = QueueIterator(queue)

    async for quote in iterator:
        process(quote)
"""

from __future__ import annotations

import asyncio
import weakref
from typing import AsyncIterator, Generic, TypeVar

T = TypeVar("T")

# Sentinel object to signal end of stream
_SENTINEL = object()

# Registry of live iterators so a single stop()/close_all() can unblock every
# consumer, even ones whose queue the caller did not keep a direct reference
# to.  A WeakSet avoids keeping dead iterators (and their queues) alive.
_LIVE_ITERATORS: weakref.WeakSet = weakref.WeakSet()


class QueueIterator(Generic[T], AsyncIterator[T]):
    """Convert an ``asyncio.Queue`` into an ``AsyncIterator``.

    The iterator yields items from the queue as they become available.
    Call ``close()`` or the module-level ``stop_all_iterators()`` to signal
    end-of-stream — a sentinel is pushed into the queue so any ``async for``
    consumer exits promptly instead of hanging.
    """

    def __init__(self, queue: asyncio.Queue[T | object]) -> None:
        self._queue = queue
        self._closed = False
        _LIVE_ITERATORS.add(self)

    def __aiter__(self) -> QueueIterator[T]:
        return self

    async def __anext__(self) -> T:
        if self._closed and self._queue.empty():
            raise StopAsyncIteration

        item = await self._queue.get()

        if item is _SENTINEL:
            self._closed = True
            raise StopAsyncIteration

        # Type narrowing: item is T at this point
        return item  # type: ignore[return-value]

    def close(self) -> None:
        """Signal end-of-stream. Remaining queued items are still yielded.

        Pushes a sentinel into the queue so any ``async for`` consumer
        currently blocked on ``__anext__`` wakes up and exits instead of
        hanging after the producer stops.
        """
        if not self._closed:
            self._closed = True
            # Make room for the sentinel if queue is full — drop oldest item
            try:
                self._queue.put_nowait(_SENTINEL)
            except asyncio.QueueFull:
                try:
                    self._queue.get_nowait()  # Drop oldest to make room
                except asyncio.QueueEmpty:
                    pass
                try:
                    self._queue.put_nowait(_SENTINEL)
                except asyncio.QueueFull:
                    # Truly stuck — __anext__ will still check _closed on the
                    # next wakeup, so the consumer can still terminate.
                    pass

    # ``stop`` is a synonym for ``close`` (consistent with orchestrator API).
    stop = close

    @property
    def is_closed(self) -> bool:
        return self._closed


def stop_all_iterators() -> None:
    """Push a sentinel into every live ``QueueIterator``'s queue.

    Call this from an orchestrator's ``stop()`` so that all ``async for``
    consumers exit even if the caller only holds queue references.  Safe to
    call multiple times.
    """
    for it in list(_LIVE_ITERATORS):
        try:
            it.close()
        except Exception:
            pass


def create_quote_stream(maxsize: int = 1000) -> tuple[asyncio.Queue, QueueIterator]:
    """Create a matched queue + iterator pair for quote streaming.

    Returns (queue, iterator) where the producer puts items into the queue
    and the consumer iterates over the iterator.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    return queue, QueueIterator(queue)


def create_order_stream(maxsize: int = 1000) -> tuple[asyncio.Queue, QueueIterator]:
    """Create a matched queue + iterator pair for order update streaming."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
    return queue, QueueIterator(queue)


__all__ = [
    "QueueIterator",
    "create_quote_stream",
    "create_order_stream",
    "_SENTINEL",
]
