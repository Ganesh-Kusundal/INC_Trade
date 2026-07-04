"""Thread-safe monotonic sequence counter for streaming tick numbering.

Implements the Martin Kleppmann requirement: every streaming tick carries
a monotonically increasing sequence number so consumers can detect gaps.
"""

import threading


class SequenceCounter:
    """Thread-safe monotonic counter that stamps streaming ticks with seq_no."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = 0

    def next(self) -> int:
        """Return the next sequence number (1-based, monotonically increasing)."""
        with self._lock:
            self._value += 1
            return self._value

    def reset(self) -> None:
        """Reset the counter to 0 (use only in tests)."""
        with self._lock:
            self._value = 0

    @property
    def current(self) -> int:
        """Return the current counter value without incrementing."""
        with self._lock:
            return self._value
