"""Fill detection port — detects order fills from broker order streams.

Adapters that support order streaming (e.g., Dhan order stream) implement
this protocol so the OMS can auto-detect fills and publish OrderFilledEvents.

Architecture::

    OMS.place_order()
        │
        ▼
    Broker adapter executes order
        │
        ▼
    FillDetectionPort.detect_fills()
        │
        ▼
    OMS processes FillResult → updates OrderRepository → publishes OrderFilledEvent
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from brokers_core.domain.entities import FillResult


@runtime_checkable
class FillDetectionPort(Protocol):
    """Protocol for detecting order fills from broker streams.

    Implementations check broker order/execution streams and return
    FillResult objects representing executed trades.

    Usage::

        class DhanFillDetection:
            def detect_fills(self, order_id: str) -> list[FillResult]:
                ...

            def on_fill(self, callback: Callable[[FillResult], None]) -> None:
                ...
    """

    def detect_fills(self, order_id: str) -> list[FillResult]:
        """Check for fills on a specific order.

        Queries the broker's order/execution stream and returns any
        fills that have occurred since the last check.

        Args:
            order_id: Broker-assigned order identifier.

        Returns:
            List of FillResult objects representing executed trades.
            Empty list if no fills detected.
        """
        ...

    def on_fill(self, callback: Callable[[FillResult], None]) -> None:
        """Register a callback invoked when a fill is detected.

        The callback is called synchronously in the detection thread.
        Implementations should batch or debounce if callbacks are
        high-frequency.

        Args:
            callback: Callable accepting a single FillResult argument.
        """
        ...
