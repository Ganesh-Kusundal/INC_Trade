"""Circuit breaker — 3-state failure protection.

States:
- CLOSED: normal operation, requests pass through
- OPEN: failures exceeded threshold, requests fast-fail
- HALF_OPEN: recovery timeout elapsed, probing with limited requests

Thread-safe with threading.Lock.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from brokers.domain.exceptions import CircuitOpenError


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerMetrics:
    total_calls: int = 0
    success_count: int = 0
    failure_count: int = 0
    state_changes: int = 0


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 1,
    ):
        if failure_threshold <= 0:
            raise ValueError(
                f"failure_threshold must be positive, got {failure_threshold}"
            )
        if recovery_timeout <= 0:
            raise ValueError(
                f"recovery_timeout must be positive, got {recovery_timeout}"
            )

        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._lock = threading.Lock()
        self.metrics = CircuitBreakerMetrics()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_recovery()
            return self._state

    def call(self, fn: Callable[[], Any], ignored_exceptions: tuple[type[Exception], ...] = ()) -> Any:
        with self._lock:
            self._check_recovery()
            if self._state is CircuitState.OPEN:
                raise CircuitOpenError("Circuit breaker is open")

        try:
            result = fn()
        except Exception as exc:
            from brokers.domain.exceptions import BrokerServerError
            is_ignored = any(isinstance(exc, t) for t in ignored_exceptions)
            if is_ignored and isinstance(exc, BrokerServerError):
                is_ignored = False
            if not is_ignored:
                self.record_failure()
            raise

        self.record_success()
        return result

    def record_success(self) -> None:
        with self._lock:
            self.metrics.total_calls += 1
            self.metrics.success_count += 1

            if self._state is CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif self._state is CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self.metrics.total_calls += 1
            self.metrics.failure_count += 1
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state is CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif (
                self._state is CircuitState.CLOSED
                and self._failure_count >= self._failure_threshold
            ):
                self._transition_to(CircuitState.OPEN)

    def reset(self) -> None:
        with self._lock:
            self._transition_to(CircuitState.CLOSED)

    def _check_recovery(self) -> None:
        if (
            self._state is CircuitState.OPEN
            and time.monotonic() - self._last_failure_time >= self._recovery_timeout
        ):
            self._transition_to(CircuitState.HALF_OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        self._state = new_state
        self.metrics.state_changes += 1
        if new_state is CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state is CircuitState.HALF_OPEN:
            self._success_count = 0
