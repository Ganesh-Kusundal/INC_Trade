"""Scanner result — value object returned by ``Scanner.scan()``.

Encapsulates the matched instruments along with scan metadata
(total scanned, duration, etc.) for downstream consumers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScanResult:
    """Outcome of a single scan execution.

    Attributes:
        matched: Tuples of (instrument, reason) where reason is a string
            describing why the instrument matched.
        total_scanned: Total number of instruments evaluated.
        duration_ms: Wall-clock duration of the scan in milliseconds.
        timestamp: Unix epoch seconds when the scan completed.
    """

    matched: list[tuple[Any, str]] = field(default_factory=list)
    total_scanned: int = 0
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def __len__(self) -> int:
        """Number of matched instruments."""
        return len(self.matched)

    def __iter__(self) -> Any:
        """Iterate over (instrument, reason) tuples."""
        return iter(self.matched)

    def __bool__(self) -> bool:
        """True if at least one instrument matched."""
        return len(self.matched) > 0

    def symbols(self) -> list[str]:
        """List of composite keys for matched instruments."""
        return [inst.composite_key for inst, _ in self.matched]
