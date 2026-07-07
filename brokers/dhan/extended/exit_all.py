"""Dhan exit all — batch liquidation of all open positions.

API: POST /exitall — exit all open positions
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExitAllResult:
    """Result of an exit-all operation."""

    positions_closed: int = 0
    orders_cancelled: int = 0
    message: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExitAllResult:
        return cls(
            positions_closed=int(data.get("positionsClosed", 0) or 0),
            orders_cancelled=int(data.get("ordersCancelled", 0) or 0),
            message=str(data.get("message", "")),
        )


class DhanExitAll:
    """Exit all positions for Dhan.

    Usage::

        exit_all = DhanExitAll(client=dhan_client)
        result = exit_all.execute()
        print(f"Closed {result.positions_closed} positions")
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def execute(self) -> ExitAllResult:
        """Exit all open positions and cancel pending orders."""
        logger.info("dhan_exit_all_execute")
        data = self._client.post("/exitall")
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return ExitAllResult.from_dict(raw if isinstance(raw, dict) else {})


__all__ = ["DhanExitAll", "ExitAllResult"]
