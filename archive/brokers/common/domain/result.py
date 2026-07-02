"""GatewayResult — a monadic result type inspired by Trade_J's GatewayResult.

Wraps operation outcomes with metadata (source, latency, cache info) and
provides functional combinators: ``map``, ``flat_map``, ``recover``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class ResultMetadata:
    """Metadata attached to every GatewayResult (source, latency)."""

    source: str = ""
    latency_ms: float = 0.0


class GatewayResult(Generic[T]):
    """Wraps a successful value or an error with metadata.

    Usage::
        result = GatewayResult.success(data, metadata=meta)
        result = GatewayResult.failure("error message")

        # Chaining
        result.map(transform).flat_map(more_work).recover(fallback)
    """

    __slots__ = ("_error", "_is_success", "_metadata", "_value")

    def __init__(
        self,
        value: T | None = None,
        error: Any = None,
        metadata: ResultMetadata | None = None,
        is_success: bool = True,
    ):
        self._value = value
        self._error = error
        self._metadata = metadata or ResultMetadata()
        self._is_success = is_success

    @classmethod
    def success(cls, value: T, metadata: ResultMetadata | None = None) -> GatewayResult[T]:
        """Create a successful result."""
        return cls(value=value, metadata=metadata, is_success=True)

    @classmethod
    def failure(cls, error: Any, metadata: ResultMetadata | None = None) -> GatewayResult[T]:
        """Create a failure result."""
        return cls(error=error, metadata=metadata, is_success=False)

    @property
    def is_success(self) -> bool:
        return self._is_success

    @property
    def is_failure(self) -> bool:
        return not self._is_success

    @property
    def value(self) -> T | None:
        return self._value

    @property
    def error(self) -> Any:
        return self._error

    @property
    def metadata(self) -> ResultMetadata:
        return self._metadata

    def map(self, fn: Callable[[T], U]) -> GatewayResult[U]:
        """Apply ``fn`` to the value if this is a success."""
        if self._is_success and self._value is not None:
            try:
                return GatewayResult.success(fn(self._value), self._metadata)
            except Exception as e:
                return GatewayResult.failure(e, self._metadata)
        return GatewayResult.failure(self._error, self._metadata)

    def flat_map(self, fn: Callable[[T], GatewayResult[U]]) -> GatewayResult[U]:
        """Apply ``fn`` (which returns a GatewayResult) to the value."""
        if self._is_success and self._value is not None:
            try:
                return fn(self._value)
            except Exception as e:
                return GatewayResult.failure(e, self._metadata)
        return GatewayResult.failure(self._error, self._metadata)

    def recover(self, fn: Callable[[Any], T]) -> GatewayResult[T]:
        """On failure, use ``fn`` to produce a fallback value."""
        if not self._is_success:
            try:
                return GatewayResult.success(fn(self._error), self._metadata)
            except Exception as e:
                return GatewayResult.failure(e, self._metadata)
        return self

    def get_or_else(self, default: T) -> T:
        """Return the value or a default if this is a failure."""
        if self._is_success and self._value is not None:
            return self._value
        return default

    def __bool__(self) -> bool:
        return self._is_success

    def __str__(self) -> str:
        if self._is_success:
            return f"Success({self._value!r})"
        return f"Failure({self._error!r})"

    def __repr__(self) -> str:
        return str(self)
