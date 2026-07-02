## Overview

TradeXV2 employs a **dual-strategy error handling system** combining:
1. **Exception-based errors** for control flow and boundary failures (broker adapters, state machines)
2. **Monadic result types** (`GatewayResult`) for gateway operations requiring metadata propagation (latency, cache status, source)

The system is anchored by a centralized exception hierarchy in `brokers/common/resilience/errors.py` with strict inheritance rules enforced via architecture tests.

---

## Exception Hierarchy

### Root Exception: `TradeXV2Error`

All application-level exceptions inherit from `TradeXV2Error`, enabling unified catch blocks at service boundaries:

```python
class TradeXV2Error(Exception):
    """Root exception for all TradeXV2 errors."""
```

### Broker Error Branch

Broker-specific errors form a dedicated subtree under `BrokerError`:

- **`RetryableError`** — transient failures eligible for automatic retry (network blips, temporary rate limits)
- **`NonRetryableError`** — permanent failures that should NOT be retried (invalid credentials, malformed requests)
- **`RateLimitError`** — broker API rate limit exceeded
- **`CircuitBreakerOpenError`** — circuit breaker tripped; request fast-failed
- **`AuthenticationError`** — token expired or rejected
- **`InstrumentNotFoundError`** — requested instrument missing from resolver cache
- **`OrderError`** — order placement/modification/cancellation failure
- **`NotSupportedError`** — feature not implemented by broker adapter
- **`BrokerDegradedError`** — all brokers unhealthy; system in degraded mode (includes health status snapshot)

### Non-Broker Error Branch

Errors outside the broker domain inherit directly from `TradeXV2Error`:

- **`DataError`** — datalake and data processing failures
- **`ConfigError`** — missing or invalid configuration
- **`ValidationError`** — input validation failures

### Adapter-Specific Exceptions

Each broker adapter defines its own exception classes that extend the canonical hierarchy. Example from Dhan:

```python
class DhanError(BrokerError): ...
class InstrumentNotFoundError(DhanError): ...
class OrderError(DhanError): ...
```

This ensures that catching `BrokerError` catches exceptions from any broker adapter, while adapter-specific handlers can catch narrower types.

---

## Monadic Result Type: `GatewayResult`

Located in `domain/result.py`, `GatewayResult[T]` wraps operation outcomes with metadata:

```python
@dataclass
class ResultMetadata:
    source: str = ""
    latency_ms: float = 0.0
    cached: bool = False
    cache_hit: bool = False
```

### Functional Combinators

- **`.map(fn)`** — transforms success value; catches exceptions and converts to failure
- **`.flat_map(fn)`** — chains operations returning `GatewayResult`
- **`.recover(fn)`** — provides fallback on failure
- **`.get_or_else(default)`** — extracts value or returns default

### Usage Pattern

```python
result = GatewayResult.success(data, metadata=meta)
result = GatewayResult.failure("error message")

# Chaining with automatic error propagation
result.map(transform).flat_map(more_work).recover(fallback)
```

This pattern is used extensively in gateway implementations to propagate observability metadata alongside results.

---

## Resilience Integration

### Circuit Breaker

`brokers/common/resilience/circuit_breaker.py` implements a thread-safe circuit breaker with three states:

- **CLOSED** — normal operation
- **OPEN** — failure threshold exceeded; requests fast-fail with `CircuitBreakerOpenError`
- **HALF_OPEN** — probing phase after open duration expires

Configuration via constants: `CIRCUIT_BREAKER_FAILURE_THRESHOLD`, `CIRCUIT_BREAKER_SUCCESS_THRESHOLD`, `CIRCUIT_BREAKER_OPEN_DURATION_MS`.

### Retry Executor

`brokers/common/resilience/retry.py` combines circuit breaker + rate limiter + exponential backoff:

```python
executor = RetryExecutor(
    config=RetryConfig(max_attempts=3),
    circuit_breaker=cb,
    rate_limiter=limiter,
    backoff=ExponentialBackoff(base_delay_ms=100),
)
executor.execute(lambda: broker.place_order(...))
```

Retry behavior:
- **`RetryableError`** — triggers backoff and retry
- **`NonRetryableError`** — immediately fails without retry
- **Plain `Exception`** — NOT retried by default (explicit opt-in required)

### CLI Retry Decorator

`cli/utils/retry_handler.py` provides `@with_retry` decorator for CLI commands:

```python
@with_retry(max_retries=3, backoff_factor=1.0)
def fetch_quote(symbol):
    return gw.quote(symbol)
```

Default retryable errors: `ConnectionError`, `TimeoutError`, `OSError`.

---

## Error Codes

Centralized in `brokers/common/resilience/error_codes.py` with module-prefixed codes:

| Prefix | Module | Examples |
|--------|--------|----------|
| `DH-xxx` | Dhan API | `DH-906` (invalid token), `DH-808` (token expired) |
| `BRO-xxx` | Broker layer | `BRO-001` (auth failed), `BRO-004` (circuit breaker open) |
| `DLK-xxx` | Datalake | `DLK-001` (data not found), `DLK-003` (IO failed) |
| `CFG-xxx` | Configuration | `CFG-001` (missing required), `CFG-003` (env not set) |
| `VAL-xxx` | Validation | `VAL-003` (path traversal), `VAL-005` (injection detected) |

---

## Error Presentation (CLI)

`cli/utils/error_formatter.py` converts raw exceptions to user-friendly messages:

- **Pattern matching** on error strings (HTTP status codes, keywords)
- **Actionable guidance** (e.g., "Run: tradex doctor" for auth errors)
- **Severity classification**: critical, error, warning, info
- **Retryability detection** via `is_retryable_error(exc)`

---

## State Machine Errors

`brokers/common/core/state_machine.py` defines `IllegalTransitionError` for invalid state transitions in order/position/scanner lifecycles:

```python
class IllegalTransitionError(Exception):
    def __init__(self, from_state: T, to_state: T):
        super().__init__(f"Illegal transition: {from_state} → {to_state}")
```

---

## Architecture Enforcement

`tests/architecture/test_cross_cutting_concerns.py` enforces:

1. All broker exceptions must inherit from `BrokerError`
2. Non-broker exceptions must inherit from `TradeXV2Error` (not `BrokerError`)
3. Error codes must be defined and accessible

These tests fail CI if inheritance rules are violated.

---

## Developer Rules

1. **Never raise bare `Exception`** — use the appropriate subclass from `brokers.common.resilience.errors`
2. **Adapter exceptions must extend canonical types** — e.g., `DhanError(BrokerError)`, not `DhanError(Exception)`
3. **Use `GatewayResult` for gateway operations** — enables metadata propagation (latency, cache status)
4. **Distinguish retryable vs non-retryable** — wrap transient failures in `RetryableError`, permanent failures in `NonRetryableError`
5. **Catch `TradeXV2Error` at service boundaries** — avoids swallowing unrelated exceptions
6. **Use error codes for logging/metrics** — reference constants from `error_codes.py` for correlation
7. **No panic/recover pattern** — Python exceptions are the sole error propagation mechanism; no Go-style panics exist
