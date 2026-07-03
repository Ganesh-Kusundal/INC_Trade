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
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""

    failure_threshold: int = 5
    success_threshold: int = 3
    open_duration_ms: int = 30_000  # 30 seconds default

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0:
            raise ValueError(
                f"failure_threshold must be positive, got {self.failure_threshold}"
            )
        if self.success_threshold <= 0:
            raise ValueError(
                f"success_threshold must be positive, got {self.success_threshold}"
            )
        if self.open_duration_ms <= 0:
            raise ValueError(
                f"open_duration_ms must be positive, got {self.open_duration_ms}"
            )


@dataclass
class CircuitBreakerMetrics:
    total_calls: int = 0
    success_count: int = 0
    failure_count: int = 0
    state_changes: int = 0


class CircuitBreaker:
    """Explicit state machine (OPEN, CLOSED, HALF_OPEN) for broker 5XX errors.

    Bridges the legacy config-based signature and new positional-arguments signature.
    """

    def __init__(
        self,
        failure_threshold: int | str = 5,
        recovery_timeout: CircuitBreakerConfig | float = 30.0,
        success_threshold: int = 3,
    ):
        self._lock = threading.Lock()
        self.metrics = CircuitBreakerMetrics()
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0

        if isinstance(failure_threshold, str):
            # Legacy constructor: (name, config)
            self.name = failure_threshold
            config = recovery_timeout
            if not isinstance(config, CircuitBreakerConfig):
                config = CircuitBreakerConfig()
            self.config = config
            self._failure_threshold = config.failure_threshold
            self._recovery_timeout = config.open_duration_ms / 1000.0
            self._success_threshold = config.success_threshold
        else:
            # Greenfield constructor: (failure_threshold, recovery_timeout, success_threshold)
            self.name = "default"
            self._failure_threshold = failure_threshold
            self._recovery_timeout = (
                recovery_timeout.open_duration_ms / 1000.0
                if isinstance(recovery_timeout, CircuitBreakerConfig)
                else float(recovery_timeout)
            )
            self._success_threshold = success_threshold
            self.config = CircuitBreakerConfig(
                failure_threshold=self._failure_threshold,
                success_threshold=self._success_threshold,
                open_duration_ms=int(self._recovery_timeout * 1000),
            )

        self._state = CircuitState.CLOSED

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_recovery()
            return self._state

    def allow_request(self) -> bool:
        """Check if request is allowed (i.e. circuit is not OPEN)."""
        return self.state is not CircuitState.OPEN

    def call(
        self,
        fn: Callable[[], Any],
        ignored_exceptions: tuple[type[Exception], ...] = (),
    ) -> Any:
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
