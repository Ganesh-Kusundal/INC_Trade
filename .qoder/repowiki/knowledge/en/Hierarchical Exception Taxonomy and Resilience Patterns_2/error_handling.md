The TradeXV2 codebase employs a structured, hierarchical exception system centered on `TradeXV2Error` to enforce clear boundaries between broker-specific failures, data-layer issues, and configuration problems. Error handling is deeply integrated with resilience patterns (Circuit Breakers, Retry Executors) and monadic result types (`GatewayResult`) to manage transient failures without relying on unstructured control flow.

### 1. Core Exception Hierarchy
All custom exceptions inherit from a root `TradeXV2Error` defined in `brokers/common/resilience/errors.py`. This hierarchy allows for granular catching at different architectural layers:

- **`TradeXV2Error`**: The root of all application-specific errors.
- **`BrokerError`**: Base class for all broker-integration failures. It has two primary sub-categories:
  - **`RetryableError`**: Transient failures (e.g., network blips) that the `RetryExecutor` will automatically attempt to resolve.
  - **`NonRetryableError`**: Permanent failures (e.g., invalid credentials, malformed payloads) that should fail immediately.
- **Specialized Broker Errors**: 
  - `RateLimitError`: Triggered when API quotas are exceeded; often handled by rate-limiting middleware or backoff strategies.
  - `CircuitBreakerOpenError`: Raised when a service is intentionally blocked due to repeated failures.
  - `AuthenticationError`, `InstrumentNotFoundError`, `OrderError`.
- **Domain-Specific Errors**:
  - **Data Layer**: `DataError` for datalake/processing issues.
  - **Configuration**: `ConfigError` for missing or invalid environment settings.
  - **Validation**: `ValidationError` for input sanitization failures.

### 2. Adapter-Level Specialization
Broker adapters (e.g., Dhan, Upstox) define their own exception classes that extend the canonical `BrokerError`. For example, `brokers/dhan/exceptions.py` defines `DhanError`, which serves as a base for feature-specific errors like `SuperOrderError` or `EDISError`. This ensures that while adapters have specific error types, they remain catchable by the common resilience infrastructure.

### 3. Resilience and Propagation
Error propagation is managed through several key mechanisms:
- **`RetryExecutor`**: Located in `brokers/common/resilience/retry.py`, this component orchestrates the "Check -> Rate Limit -> Execute -> Handle" flow. It distinguishes between `RetryableError` (triggers exponential backoff) and `NonRetryableError` (immediate failure).
- **Circuit Breakers**: Implemented in `brokers/common/resilience/circuit_breaker.py`, these prevent cascading failures by fast-failing requests when a service is deemed unhealthy (OPEN state).
- **Monadic Results**: The `GatewayResult` class in `brokers/common/core/result.py` provides a functional approach to error handling. Instead of throwing exceptions for expected operational failures, operations return a `Failure` state containing the error, allowing for chaining via `.map()`, `.flat_map()`, and `.recover()`.

### 4. Presentation and CLI Formatting
In the CLI layer (`cli/utils/error_formatter.py`), raw exceptions are transformed into user-friendly, actionable messages. The `format_error` function inspects exception strings for keywords (e.g., "401", "rate limit", "timeout") and maps them to guidance like "Run: tradex doctor" or "Retry after 60s". This decouples internal error codes from external user experience.

### 5. API Layer Handling
The FastAPI-based Data Lake API (`datalake/api/`) uses standard `HTTPException` for HTTP-level errors (401, 403, 404, 500). Dependency injection functions in `datalake/api/deps.py` raise these exceptions when services are unavailable or authentication fails, ensuring consistent RESTful error responses.

### Key Conventions for Developers
- **Extend Canonical Types**: Always inherit from `BrokerError` or `TradeXV2Error` rather than creating standalone exception classes.
- **Use Retryable vs. Non-Retryable**: Explicitly choose between `RetryableError` and `NonRetryableError` to guide the `RetryExecutor`'s behavior.
- **Prefer GatewayResult for Control Flow**: Use `GatewayResult` for operations where failure is a common, expected outcome (e.g., cache misses, optional data fetches) to avoid expensive stack traces.
- **Centralize Error Messages**: Use `cli.utils.error_formatter` to ensure consistent messaging across all CLI commands.