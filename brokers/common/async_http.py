"""Shared async HTTP helper — offloads sync HTTP calls to the thread pool.

Both DhanProvider and UpstoxProvider had identical _http methods that
offload sync HTTP calls via run_in_executor.  This mixin eliminates
that duplication.

Usage::

    class DhanProvider(ResolutionMixin, AsyncHttpMixin):
        async def get_quote(self, instrument):
            data = await self._http(self._client.get_quote, segment, [sid])
            ...
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class AsyncHttpMixin:
    """Mixin that provides an async wrapper for sync HTTP calls.

    Offloads blocking HTTP calls to the default thread pool executor
    so they don't block the asyncio event loop.
    """

    @staticmethod
    async def _http(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Offload a sync HTTP call to the thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


__all__ = ["AsyncHttpMixin"]
