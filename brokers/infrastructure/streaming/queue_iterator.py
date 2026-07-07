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
from typing import AsyncIterator, Generic, TypeVar

T = TypeVar("T")

# Sentinel object to signal end of stream
_SENTINEL = object()


class QueueIterator(Generic[T], AsyncIterator[T]):
    """Convert an ``asyncio.Queue`` into an ``AsyncIterator``.

    The iterator yields items from the queue as they become available.
    Call ``close()`` to signal end-of-stream — the iterator will drain
    any remaining items and then raise ``StopAsyncIteration``.
    """

    def __init__(self, queue: asyncio.Queue[T | object]) -> None:
        self._queue = queue
        self._closed = False

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
        """Signal end-of-stream. Remaining queued items are still yielded."""
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
                    pass  # Truly stuck — __anext__ will check is_closed

    @property
    def is_closed(self) -> bool:
        return self._closed


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
