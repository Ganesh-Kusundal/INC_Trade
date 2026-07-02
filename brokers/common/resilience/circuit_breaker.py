"""Circuit breaker — failure threshold-based with half-open recovery.

Maps 1:1 to Trade_J's CircuitBreaker pattern.
Thread-safe with RLock for concurrent access from multiple threads.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum

from domain.constants import (
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_OPEN_DURATION_MS,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
)


class CircuitState(Enum):
    """State of a circuit breaker."""

    CLOSED = "CLOSED"  # Normal operation — requests allowed
    OPEN = "OPEN"  # Failing — requests fast-fail
    HALF_OPEN = "HALF_OPEN"  # Probing — limited requests allowed


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""

    failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD
    success_threshold: int = CIRCUIT_BREAKER_SUCCESS_THRESHOLD
    open_duration_ms: int = CIRCUIT_BREAKER_OPEN_DURATION_MS  # 30 seconds default

    def __post_init__(self):
        if self.failure_threshold <= 0:
            raise ValueError(f"failure_threshold must be positive, got {self.failure_threshold}")
        if self.success_threshold <= 0:
            raise ValueError(f"success_threshold must be positive, got {self.success_threshold}")
        if self.open_duration_ms <= 0:
            raise ValueError(f"open_duration_ms must be positive, got {self.open_duration_ms}")


@dataclass
class CircuitBreakerMetrics:
    """Observability metrics for a circuit breaker."""

    failure_count: int = 0
    success_count: int = 0
    state_change_count: int = 0
    total_calls: int = 0


class CircuitBreaker:
    """Stateful circuit breaker to prevent cascading failures.

    Three states:
    - CLOSED: normal, requests pass through
    - OPEN: failure threshold exceeded, requests fail fast
    - HALF_OPEN: after open duration, allows probe requests
    """

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._lock = threading.RLock()  # Thread-safe: protects all mutable state
        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._opened_at_ns: float = 0.0
        self._state_change_count: int = 0
        self._total_calls: int = 0

    @property
    def state(self) -> CircuitState:
        """Current state, potentially transitioning from OPEN -> HALF_OPEN.

        Thread-safe: acquires lock to prevent concurrent state transitions.
        """
        with self._lock:
            if self._state == CircuitState.OPEN and (
                time.monotonic_ns() - self._opened_at_ns >= self.config.open_duration_ms * 1_000_000
            ):
                self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    @property
    def metrics(self) -> CircuitBreakerMetrics:
        """Return a snapshot of current metrics.

        Thread-safe: acquires lock to prevent torn reads.
        """
        with self._lock:
            return CircuitBreakerMetrics(
                failure_count=self._failure_count,
                success_count=self._success_count,
                state_change_count=self._state_change_count,
                total_calls=self._total_calls,
            )

    def allow_request(self) -> bool:
        """Check if a request is allowed through the circuit breaker.

        Thread-safe: acquires lock via state property.
        """
        return self.state != CircuitState.OPEN

    def on_success(self) -> None:
        """Record a successful execution.

        Thread-safe: acquires lock to prevent concurrent state corruption.
        """
        with self._lock:
            self._total_calls += 1

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._success_count += 1
                # Reset failure count on consecutive success
                self._failure_count = 0

    def on_failure(self) -> None:
        """Record a failed execution.

        Thread-safe: acquires lock to prevent concurrent state corruption.
        """
        with self._lock:
            self._total_calls += 1
            self._failure_count += 1

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately re-opens
                self._transition_to(CircuitState.OPEN)
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.config.failure_threshold
            ):
                self._transition_to(CircuitState.OPEN)

    def reset(self) -> None:
        """Force reset to CLOSED state.

        Thread-safe: acquires lock to prevent concurrent modifications.
        """
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0
            self._total_calls = 0

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state.

        NOTE: Caller must hold self._lock. This is an internal method
        called only from locked contexts (state property, on_success,
        on_failure, reset).
        """
        if self._state != new_state:
            self._state = new_state
            self._state_change_count += 1
            if new_state == CircuitState.OPEN:
                self._opened_at_ns = time.monotonic_ns()
            if new_state == CircuitState.HALF_OPEN:
                self._success_count = 0
            if new_state == CircuitState.CLOSED:
                self._failure_count = 0
                self._success_count = 0

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name='{self.name}', "
            f"state={self._state.value}, "
            f"failures={self._failure_count}/{self.config.failure_threshold})"
        )
