"""Observer protocols for the reactive Instrument pipeline.

ADR-008: Observer pattern formalized with typed protocols.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class QuoteObserver(Protocol):
    """Protocol for receiving quote tick notifications."""

    def on_quote(self, instrument: Any, quote: Any) -> None: ...


@runtime_checkable
class DepthObserver(Protocol):
    """Protocol for receiving depth update notifications."""

    def on_depth(self, instrument: Any, depth: Any) -> None: ...
