The TradeXV2 platform employs a multi-layered error handling strategy that combines **custom exception hierarchies**, **monadic result types**, **resilience patterns** (circuit breakers, retries), and **user-facing error formatting**. This approach ensures robust fault tolerance in broker interactions while providing actionable feedback to CLI users and API consumers.

### 1. Core Exception Hierarchy
All custom exceptions inherit from a root `TradeXV2Error` defined in `brokers/common/resilience/errors.py`. This hierarchy is strictly typed to support selective catching and resilience logic:

- **`TradeXV2Error`**: The base class for all platform-specific errors.
- **`BrokerError`**: Base for all broker-related failures. Subtypes include:
  - `RetryableError`: Transient failures (e.g., network blips) that the `RetryExecutor` will automatically attempt to resolve.
  - `NonRetryableError`: Permanent failures (e.g., invalid parameters) that should fail immediately.
  - `RateLimitError`, `CircuitBreakerOpenError`, `AuthenticationError`, `InstrumentNotFoundError`, `OrderError`.
  - `BrokerDegradedError`: Raised when all configured brokers are unhealthy, signaling a system-wide degraded state.
- **`DataError`**, **`ConfigError`**, **`ValidationError`**: Domain-specific errors for the datalake and configuration subsystems.
- **`UnsupportedGatewayOperation`**: A specialized `NotImplementedError` in `brokers/common/gateway_errors.py` used when a broker gateway lacks a specific contract method.

### 2. Monadic Result Pattern (`GatewayResult`)
To avoid excessive try/except blocks in core logic, the `domain/result.py` module implements a `GatewayResult[T]` monad. This pattern wraps operation outcomes with metadata (source, latency) and provides functional combinators:
- **`success(value)` / `failure(error)`**: Factory methods.
- **`map(fn)` / `flat_map(fn)`**: Chain transformations only if the previous step succeeded.
- **`recover(fn)`**: Provide fallback values on failure.
- **`get_or_else(default)`**: Extract the value or a default.
This is heavily used in gateway and data-fetching layers to propagate errors without throwing exceptions until necessary.

### 3. Resilience and Retry Logic
The `brokers/common/resilience/` package implements a `RetryExecutor` that orchestrates fault tolerance:
1. **Circuit Breaker Check**: Fails fast if the circuit is open (`CircuitBreakerOpenError`).
2. **Rate Limiting**: Acquires tokens from a `MultiBucketRateLimiter` before execution.
3. **Execution & Classification**: 
   - `RetryableError` triggers exponential backoff.
   - `NonRetryableError` and plain `Exception` (by default) fail immediately.
4. **Backoff**: Uses `ExponentialBackoff` with configurable max delays.

For CLI commands, a simpler `@with_retry` decorator in `cli/utils/retry_handler.py` handles transient `ConnectionError`, `TimeoutError`, and `OSError` exceptions with exponential backoff.

### 4. API and Middleware Error Handling
The FastAPI application (`datalake/api/main.py`) uses `RequestLoggingMiddleware` (`datalake/api/middleware.py`) to:
- Generate/correlate `X-Request-ID` headers.
- Log request duration and status codes.
- Record Prometheus metrics for error rates (5xx status codes).
Unhandled exceptions in the API layer result in standard FastAPI 500 responses, while specific business errors should be mapped to appropriate HTTP status codes by routers (though explicit exception handlers are not currently centralized in `main.py`).

### 5. CLI Error Formatting
The `cli/utils/error_formatter.py` module translates raw Python exceptions into user-friendly, actionable messages. It inspects exception strings for keywords (e.g., "401", "rate limit", "timeout") and returns guidance like:
- *"Authentication failed. Token may be expired. Run: tradex doctor"*
- *"Rate limit exceeded. Retry after 60s..."*
It also classifies severity (`critical`, `error`, `warning`, `info`) and determines retryability for the CLI's interactive console.

### Developer Conventions
- **Use `GatewayResult`** for internal data fetching and gateway operations to enable chaining and metadata tracking.
- **Raise specific `TradeXV2Error` subtypes** (e.g., `RetryableError`) rather than generic `Exception` to ensure the `RetryExecutor` behaves correctly.
- **Do not catch `BrokerError` broadly** unless you intend to handle all broker failures; prefer catching specific subtypes.
- **Use `format_error`** in CLI commands to ensure consistent user messaging.
- **Avoid silent failures**: The `intelligent_gateway` and other core components are designed to raise `BrokerDegradedError` or similar when services are unavailable, rather than returning empty data.