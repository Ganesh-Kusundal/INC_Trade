"""Idempotency-specific exceptions."""

from __future__ import annotations


class IdempotencyError(Exception):
    """Base exception for idempotency-related errors."""
    
    def __init__(self, message: str, key: str | None = None, operation: str = "unknown"):
        super().__init__(message)
        self.message = message
        self.key = key
        self.operation = operation
    
    def __str__(self) -> str:
        parts = [f"IdempotencyError: {self.message}"]
        if self.key:
            parts.append(f"key={self.key}")
        if self.operation:
            parts.append(f"operation={self.operation}")
        return " | ".join(parts)


class IdempotencyKeyExistsError(IdempotencyError):
    """Raised when attempting to create a duplicate idempotency key."""
    
    def __init__(self, key: str, existing_value: object, new_value: object):
        message = f"Idempotency key already exists: {key}"
        super().__init__(message, key, "put")
        self.existing_value = existing_value
        self.new_value = new_value


class IdempotencyCacheError(IdempotencyError):
    """Raised when there's a problem with the idempotency cache backend."""
    
    def __init__(self, message: str, backend: str, key: str | None = None):
        super().__init__(message, key, "cache_operation")
        self.backend = backend


class IdempotencyTimeoutError(IdempotencyError):
    """Raised when an idempotency operation times out."""
    
    def __init__(self, message: str = "Operation timed out", key: str | None = None, timeout_seconds: float = 0.0):
        super().__init__(message, key, "timeout")
        self.timeout_seconds = timeout_seconds


class DistributedLockError(IdempotencyError):
    """Raised when there's a problem with distributed locking."""
    
    def __init__(self, message: str, key: str, lock_name: str):
        super().__init__(message, key, "distributed_lock")
        self.lock_name = lock_name


__all__ = [
    "IdempotencyError",
    "IdempotencyKeyExistsError", 
    "IdempotencyCacheError",
    "IdempotencyTimeoutError",
    "DistributedLockError",
]