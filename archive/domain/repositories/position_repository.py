"""Position repository protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain import Position


@runtime_checkable
class PositionRepository(Protocol):
    """Query port for open positions."""

    def get_positions(self) -> list[Position]:
        """Return all open positions."""
        ...


__all__ = ["PositionRepository"]
