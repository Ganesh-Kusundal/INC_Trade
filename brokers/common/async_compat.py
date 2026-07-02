"""Shared async/sync boundary helpers.

When synchronous Python code needs to drive an async coroutine (e.g.
WebSocket connect/disconnect), there are two cases:

1. **Async context** — an event loop is already running.  The coroutine is
   scheduled via ``run_coroutine_threadsafe`` which is safe from any
   thread (not just the event-loop thread).
2. **Sync context** — no event loop.  A temporary loop is created, the
   coroutine is awaited, and the loop is torn down.

Both patterns were duplicated in ``lifecycle_wrapper.py`` and
``gateway.py:stream()``.  This module centralises them into a single
``run_async_compat`` helper.

Thread safety
-------------
``run_coroutine_threadsafe`` is always used in the async-context path
because the caller may be on a different thread (e.g. a CLI command
calling ``gateway.stream()`` while the Textual TUI owns the event
loop).  ``asyncio.ensure_future`` would fail with
``RuntimeError: Task attached to a different loop`` when called from
a non-loop thread.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


def run_async_compat(
    coro: Awaitable[Any],
    *,
    fire_and_forget: bool = True,
    timeout: float | None = None,
) -> Any | None:
    """Run an async coroutine from synchronous code, handling both contexts.

    Args:
        coro: The awaitable to execute.
        fire_and_forget: When ``True`` (default) and an event loop is
            already running, the coroutine is scheduled via
            ``run_coroutine_threadsafe`` and ``None`` is returned
            immediately.  When ``False`` the caller blocks until the
            coroutine completes (useful when a return value is needed).

            .. warning:: ``fire_and_forget=False`` blocks the current
               thread via ``future.result()``.  Calling it from the
               event-loop thread **will deadlock**.  Only use this
               path from a non-loop thread (e.g. a worker thread).

        timeout: Maximum seconds to wait when ``fire_and_forget=False``.
            ``None`` means wait forever.

    Returns:
        The coroutine's result when awaited synchronously, or ``None``
        when scheduled as fire-and-forget.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — sync context.  Create a temporary loop.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    # Async context — loop is running.  Use run_coroutine_threadsafe
    # so this works from any thread (not just the loop's thread).
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    if fire_and_forget:
        return None
    return future.result(timeout=timeout)


def connect_async_then(
    connect_coro: Awaitable[Any],
    on_connected: Callable[[], None],
) -> None:
    """Connect an async resource, then run post-connect actions synchronously.

    This handles the common pattern where ``connect()`` is async but
    ``subscribe()`` / ``add_listener()`` / any setup is sync and must
    run **after** the connection is established.

    In async context the coroutine is scheduled via
    ``run_coroutine_threadsafe`` (thread-safe), and *on_connected* is
    called as part of the same scheduled task — guaranteeing ordering.
    In sync context a temporary loop runs the coroutine, then
    *on_connected* is called synchronously.

    Args:
        connect_coro: The awaitable connect coroutine.
        on_connected: Sync callable executed after the connect completes.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Sync context — connect synchronously, then run callback.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(connect_coro)
            on_connected()
        finally:
            loop.close()
        return

    # Async context — schedule connect+callback atomically.
    async def _connect_and_act() -> None:
        await connect_coro
        on_connected()

    asyncio.run_coroutine_threadsafe(_connect_and_act(), loop)
