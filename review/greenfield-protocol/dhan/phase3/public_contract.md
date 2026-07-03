# Phase 3 Rate Limiting — Public Contract

## 1. Archive `DhanHttpClient` Full API

**Module**: `archive.brokers.dhan.http_client`
**Constructor Signature**: `DhanHttpClient(client_id, access_token, ...)`

| Method | Signature | Returns | Exceptions | Side Effects |
|--------|-----------|---------|------------|--------------|
| `__init__` | `(client_id: str, access_token: str, base_url: str = _DEFAULT_BASE_URL, timeout: float = 15.0, token_refresh_fn: Callable[[], str] \| None = None, enable_retry: bool = True, circuit_breaker: CircuitBreaker \| None = None, read_circuit_breaker: CircuitBreaker \| None = None, write_circuit_breaker: CircuitBreaker \| None = None, admin_circuit_breaker: CircuitBreaker \| None = None, session: requests.Session \| None = None, _rate_limiter: MultiBucketRateLimiter \| None = None, _circuit_breakers: dict[str, CircuitBreaker] \| None = None, config: DhanResilienceConfig \| None = None)` | — | — | Creates/reuses `requests.Session`; sets headers `client-id`, `access-token`, `Content-Type`, `Accept` |
| `get` | `(endpoint: str) -> dict[str, Any]` | Parsed JSON dict | `DhanError`, `AuthenticationError`, `RateLimitError` | Delegates to `_request("GET", ...)` |
| `post` | `(endpoint: str, json: dict \| None = None) -> dict[str, Any]` | Parsed JSON dict | `DhanError`, `AuthenticationError`, `RateLimitError` | Delegates to `_request("POST", ...)` |
| `put` | `(endpoint: str, json: dict \| None = None) -> dict[str, Any]` | Parsed JSON dict | `DhanError`, `AuthenticationError`, `RateLimitError` | Delegates to `_request("PUT", ...)` |
| `delete` | `(endpoint: str) -> dict[str, Any]` | Parsed JSON dict | `DhanError`, `AuthenticationError`, `RateLimitError` | Delegates to `_request("DELETE", ...)` |
| `update_token` | `(access_token: str) -> None` | — | — | Updates `self.access_token` + session header |
| `close` | `() -> None` | — | — | `self._session.close()` |
| `_get_circuit_breaker` | `(endpoint: str) -> CircuitBreaker \| None` | Category-specific CB | — | Routes by `_categorize_endpoint()` |
| `_throttle` | `(endpoint: str) -> None` | — | — | Sleeps to enforce minimum interval |
| `_acquire_rate_limit_token` | `(endpoint: str, timeout: float = 5.0) -> bool` | Token acquired? | — | Records metrics on success/rejection |
| `_try_refresh_token` | `() -> bool` | Refresh success? | Catches all internally | Sets `_refresh_backoff_until` on failure |
| `_send_raw_http` | `(method, url, json) -> requests.Response` | Raw response | `DhanError` on network error | Records CB failure on network error |
| `_request` | `(method, endpoint, json) -> dict[str, Any]` | Parsed JSON | `DhanError`, `AuthenticationError`, `RateLimitError` | Full pipeline: CB → RL → throttle → retry loop |

### Archive Attributes

| Attribute | Type | Access | Description |
|-----------|------|--------|-------------|
| `client_id` | `str` | Public | Dhan client ID |
| `access_token` | `str` | Public | Current access token |
| `_base_url` | `str` | Private | API base URL |
| `_timeout` | `float` | Private | Request timeout (default 15s) |
| `_session` | `requests.Session` | Private | HTTP session |
| `_adaptive_intervals` | `dict[str, float]` | Private | Per-endpoint adaptive backoff (updated on 429) |
| `_last_request_time` | `dict[str, float]` | Private | Per-endpoint last request timestamp |
| `_rate_lock` | `threading.Lock` | Private | Serializes throttle writes |
| `_last_refresh_time` | `float` | Private | Last successful token refresh timestamp |
| `_refresh_backoff_until` | `float` | Private | Backoff deadline after rate-limited refresh |
| `_config` | `DhanResilienceConfig` | Private | Resilience configuration |
| `_rate_metrics` | `DhanRateLimiterMetrics` | Private | Rate limiter observability |

---

## 2. Greenfield `DhanHttpClient` Full API

**Module**: `brokers.adapters.dhan.http`
**Constructor Signature**: `DhanHttpClient(access_token, client_id, ...)`

| Method | Signature | Returns | Exceptions | Side Effects |
|--------|-----------|---------|------------|--------------|
| `__init__` | `(access_token: str, client_id: str, base_url: str = "", timeout: float = 10.0, token_refresh_fn: Callable[[], str \| None] \| None = None, refresh_lock: threading.Lock \| None = None, refresh_cooldown_seconds: float = 60.0, rate_limit_backoff_seconds: float = 130.0)` | — | — | Calls `super().__init__(rate_limits=RATE_LIMITS, timeout=timeout)`; sets session headers |
| `get` | `(endpoint: str, params: dict \| None = None) -> dict` | Parsed JSON dict | `BrokerError`, `AuthenticationError`, `RateLimitError`, `CircuitOpenError`, `BrokerServerError` | Delegates to `_request("GET", ..., params=params)` |
| `post` | `(endpoint: str, json: dict \| None = None) -> dict` | Parsed JSON dict | Same as `get` | Delegates to `_request("POST", ..., json=json)` |
| `put` | `(endpoint: str, json: dict \| None = None) -> dict` | Parsed JSON dict | Same as `get` | Delegates to `_request("PUT", ..., json=json)` |
| `delete` | `(endpoint: str, params: dict \| None = None) -> dict` | Parsed JSON dict | Same as `get` | Delegates to `_request("DELETE", ..., params=params)` |
| `update_token` | `(new_token: str) -> None` | — | — | Updates `_access_token` + session header `access-token` |
| `close` | `() -> None` | — | — | `self._session.close()` (inherited) |
| `client_id` (property) | — | `str` | — | Read-only accessor |
| `access_token` (property) | — | `str` | — | Read-only accessor |

### Greenfield-Only Attributes

| Attribute | Type | Access | Description |
|-----------|------|--------|-------------|
| `_access_token` | `str` | Via property | Current access token |
| `_client_id` | `str` | Via property | Dhan client ID |
| `_base_url` | `str` | Private | Auto-detected from ENDPOINTS if empty |
| `_token_refresh_fn` | `Callable \| None` | Private | Token refresh callable |
| `_refresh_lock` | `threading.Lock \| None` | Private | Shared lock for concurrent refresh prevention |
| `_refresh_cooldown_seconds` | `float` | Private | Min time between refresh attempts (60s) |
| `_rate_limit_backoff_seconds` | `float` | Private | Backoff on Dhan token rate limit (130s) |
| `_last_refresh_time` | `float` | Private | Last successful refresh timestamp |
| `_refresh_backoff_until` | `float` | Private | Backoff deadline after rate-limited refresh |
| `_adaptive_intervals` | `dict[str, float]` | Private | Per-endpoint adaptive intervals from 429s |

---

## 3. `BaseResilientHttpClient` Abstract API

**Module**: `brokers.resilience.http_client`

| Method | Signature | Returns | Exceptions | Notes |
|--------|-----------|---------|------------|-------|
| `__init__` | `(rate_limits: dict[str, float], timeout: float = 10.0)` | — | — | Creates `_rate_limiters`, `_circuit_breakers` (3), `_retry` |
| `get` | `(endpoint: str, params: dict \| None = None) -> dict` | Parsed JSON | Propagates from `_handle_response` | Calls `_request("GET", ...)` |
| `post` | `(endpoint: str, json: dict \| None = None) -> dict` | Parsed JSON | Same | Calls `_request("POST", ...)` |
| `put` | `(endpoint: str, json: dict \| None = None) -> dict` | Parsed JSON | Same | Calls `_request("PUT", ...)` |
| `delete` | `(endpoint: str, params: dict \| None = None) -> dict` | Parsed JSON | Same | Calls `_request("DELETE", ...)` |
| `close` | `() -> None` | — | — | Closes `_session` |
| `_request` | `(method, endpoint, **kwargs) -> dict` | Parsed JSON | `BrokerError` wraps all non-BrokerError exceptions | Full pipeline: categorize → CB → rate limit → retry |
| `_apply_rate_limit` | `(endpoint: str) -> None` | — | — | Prefix match → `acquire(1, timeout=5.0)` |
| `_categorize` | `(endpoint: str) -> str` | `"read" \| "write" \| "admin"` | — | **Abstract** — subclass must implement |
| `_build_url` | `(endpoint: str) -> str` | Absolute URL | — | **Abstract** — subclass must implement |
| `_handle_response` | `(resp: requests.Response) -> dict` | Parsed JSON | Domain exceptions | **Abstract** — subclass must implement |

### Internal Components Created by `__init__`

| Component | Configuration | Count |
|-----------|--------------|-------|
| `_rate_limiters` | One `TokenBucketRateLimiter` per entry in `rate_limits` dict | N (6 for Dhan) |
| `_circuit_breakers` | `read(5,30,1)`, `write(3,60,1)`, `admin(5,30,1)` | 3 |
| `_retry` | `RetryPolicy(max_retries=3, base_delay_ms=500, max_delay_ms=5000, retryable=(RequestException, BrokerServerError))` | 1 |
| `_session` | `create_pinned_session()` or `requests.Session()` | 1 |

---

## 4. `CircuitBreaker` API

### Greenfield (`brokers.resilience.circuit_breaker.CircuitBreaker`)

| Method | Signature | Returns | Exceptions | Notes |
|--------|-----------|---------|------------|-------|
| `__init__` | `(failure_threshold: int = 5, recovery_timeout: float = 30.0, success_threshold: int = 1)` | — | `ValueError` if thresholds ≤ 0 | Validates inputs |
| `state` (property) | — | `CircuitState` | — | Checks recovery timeout lazily |
| `call` | `(fn: Callable[[], Any], ignored_exceptions: tuple[type[Exception], ...] = ()) -> Any` | `fn()` result | `CircuitOpenError` if OPEN; propagates `fn()` exceptions | Records success/failure automatically |
| `record_success` | `() -> None` | — | — | HALF_OPEN→CLOSED if threshold met; CLOSED resets failure count |
| `record_failure` | `() -> None` | — | — | HALF_OPEN→OPEN immediately; CLOSED→OPEN if threshold met |
| `reset` | `() -> None` | — | — | Force to CLOSED; clears all counters |
| `metrics` (attribute) | `CircuitBreakerMetrics` | — | — | `total_calls`, `success_count`, `failure_count`, `state_changes` |

### Archive Infrastructure (`brokers.infrastructure.resilience.circuit_breaker.CircuitBreaker`)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(failure_threshold=5, recovery_timeout=30.0, success_threshold=3)` | — | Default `success_threshold=3` vs greenfield's `1` |
| `allow_request` | `() -> bool` | `bool` | Checks state + recovery timeout; transitions OPEN→HALF_OPEN |
| `record_success` | `() -> None` | — | HALF_OPEN→CLOSED if `successes >= success_threshold` |
| `record_failure` | `() -> None` | — | HALF_OPEN→OPEN immediately; CLOSED→OPEN if threshold met |

### Key Differences

| Aspect | Greenfield | Archive (new resilience) | Archive (infrastructure) |
|--------|-----------|--------------------------|--------------------------|
| Lock type | `threading.Lock` | `threading.RLock` | `threading.RLock` |
| Time source | `time.monotonic()` | `time.time()` | `time.time()` |
| Default `success_threshold` | 1 | 3 | 3 |
| API style | `call(fn)` wrapper | `allow_request()` + manual record | `allow_request()` + manual record |
| Metrics | `CircuitBreakerMetrics` dataclass | None | None |
| Input validation | `ValueError` on bad params | None | None |

---

## 5. `TokenBucketRateLimiter` API

### Greenfield (`brokers.resilience.rate_limiter.TokenBucketRateLimiter`)

| Method | Signature | Returns | Exceptions | Notes |
|--------|-----------|---------|------------|-------|
| `__init__` | `(rate_per_second: float = 10.0, capacity: int = 10)` | — | `ValueError` if ≤ 0 | Validates inputs |
| `available_tokens` (property) | — | `float` | — | Refills before reading |
| `acquire` | `(tokens: int = 1, timeout: float \| None = None) -> bool` | Acquired? | — | Blocks with `Condition.wait()`; returns `False` if timeout or `tokens > capacity` |

### Archive Infrastructure (`brokers.infrastructure.resilience.rate_limiter.TokenBucketRateLimiter`)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(capacity: int, rate_per_second: float)` | — | **Parameter order reversed** vs greenfield |
| `acquire` | `(tokens: int = 1, timeout: float \| None = None) -> bool` | Acquired? | Spin-loop with `time.sleep(0.01)` |

### Archive `MultiBucketRateLimiter`

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(configs: dict[str, TokenBucketRateLimiter])` | — | Map of category → limiter |
| `acquire` | `(category: str, tokens: int = 1, timeout: float \| None = None) -> bool` | Acquired? | Unknown category → `True` |

### Key Differences

| Aspect | Greenfield | Archive Infrastructure |
|--------|-----------|----------------------|
| Constructor param order | `(rate_per_second, capacity)` | `(capacity, rate_per_second)` |
| Blocking mechanism | `threading.Condition.wait()` | `time.sleep(0.01)` spin-loop |
| Input validation | `ValueError` on bad params | None |
| Default values | `rate=10.0, capacity=10` | No defaults |
| Multi-bucket | N/A (dict of individual limiters) | `MultiBucketRateLimiter` wrapper |

---

## 6. `RetryPolicy` API

### Greenfield (`brokers.resilience.retry.RetryPolicy`)

| Method | Signature | Returns | Exceptions | Notes |
|--------|-----------|---------|------------|-------|
| `__init__` | `(max_retries: int = 3, base_delay_ms: int = 500, max_delay_ms: int = 5000, retryable_exceptions: tuple = (Exception,))` | — | `ValueError` if `max_retries < 0` | Validates |
| `call` | `(fn: Callable[[], T]) -> T` | `fn()` result | Last caught exception after all retries exhausted | Exponential backoff + jitter |
| `_compute_delay` | `(attempt: int) -> int` | Delay in ms | — | `min(base × 2^attempt, max) + randint(0, delay//4)` |

### Archive (`brokers.infrastructure.resilience.retry_executor.RetryExecutor`)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(max_attempts, base_delay, max_delay, circuit_breaker=None, rate_limiter=None, rate_limit_category=None)` | — | Integrates CB + RL into retry |
| `execute` | `(func: Callable[[], T]) -> T` | `func()` result | Heuristic error classification (string matching) |

---

## 7. `DhanResilienceConfig` API (Archive Only)

**Module**: `archive.brokers.dhan.config`

| Dataclass | Fields | Defaults |
|-----------|--------|----------|
| `DhanRateLimitConfig` | `limits: dict[str, float]`, `read_prefixes: tuple`, `write_prefixes: tuple`, `bucket_map: dict[str, str]` | See `DEFAULT_RATE_LIMITS`, `DEFAULT_READ_CB_PREFIXES`, etc. |
| `DhanRetryConfig` | `max_retries: int`, `base_delay_ms: int`, `max_delay_ms: int` | 3, 500, 5000 |
| `DhanCircuitBreakerConfig` | `read_prefixes`, `write_prefixes`, `orders_failure_threshold`, `default_failure_threshold`, `recovery_timeout_ms`, `success_threshold` | 3, 5, 30000, 3 |
| `DhanTokenConfig` | `refresh_cooldown_seconds`, `rate_limit_backoff_seconds` | 60, 130 |
| `DhanResilienceConfig` | `rate_limit`, `retry`, `circuit_breaker`, `token`, `base_url` | All defaults composed |

| Method | Signature | Returns |
|--------|-----------|---------|
| `from_dict` | `(data: dict \| None) -> DhanResilienceConfig` | New instance |
| `to_dict` | `() -> dict[str, Any]` | Serializable dict |

**Greenfield has NO equivalent configuration object.** All values are hardcoded in `BaseResilientHttpClient.__init__` and `brokers.adapters.dhan.config.RATE_LIMITS`.

---

## 8. `DhanRateLimiterMetrics` API (Archive Only)

**Module**: `archive.brokers.dhan.resilience.rate_limiter`

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `()` | — | Creates empty tracking dicts |
| `record_request` | `(category: str) -> None` | — | Appends timestamp; prunes >60s |
| `record_rejection` | `(category: str) -> None` | — | Increments rejection counter |
| `increment_queue_depth` | `(category: str) -> None` | — | Increments waiting count |
| `decrement_queue_depth` | `(category: str) -> None` | — | Decrements waiting count |
| `get_requests_per_second` | `(category: str) -> float` | Rate over last 10s | Computed from timestamps |

**Greenfield has NO equivalent metrics class.** The `MetricsRegistry` in `brokers.adapters.dhan.metrics` provides Prometheus counters but is not wired into the request path.

---

## 9. Exception Hierarchy

### Archive Exception Hierarchy

```
Exception
└── BrokerError (brokers.common.resilience.errors)
    ├── RateLimitError
    ├── AuthenticationError (common)
    ├── InstrumentNotFoundError (common)
    ├── OrderError (common)
    ├── ExitAllError (common → NotSupportedError)
    └── DhanError (archive.brokers.dhan.exceptions)
        ├── InstrumentNotFoundError (multiple inheritance)
        ├── MarketDataError
        ├── OrderError (multiple inheritance)
        ├── AuthenticationError (multiple inheritance)
        ├── ConfigurationError
        ├── DhanIdentityError
        ├── SuperOrderError
        ├── ForeverOrderError
        ├── ConditionalTriggerError
        ├── LedgerError
        ├── UserProfileError
        ├── IPManagementError
        ├── ExitAllError (multiple inheritance)
        └── EDISError
```

### Greenfield Exception Hierarchy

```
Exception
└── TradeXV2Error (brokers.domain.exceptions)
    ├── ConfigError
    ├── DataError
    ├── ValidationError
    └── BrokerError (code: str = "")
        ├── RetryableError
        │   └── NetworkError
        ├── NonRetryableError
        ├── BrokerServerError (code: str)
        ├── OrderRejectedError (order_id: str, code: str)
        ├── RateLimitError (retry_after: float | None)
        ├── CircuitOpenError
        ├── AuthenticationError
        ├── TokenRateLimitError
        ├── InstrumentNotFoundError (symbol: str)
        ├── NotSupportedError
        └── BrokerDegradedError (health_status: dict)
```

### Exception Mapping Differences

| Scenario | Archive Exception | Greenfield Exception |
|----------|------------------|---------------------|
| HTTP 429 | `RateLimitError` (after retries exhausted) | `RateLimitError` (immediate, no retry) |
| HTTP 401 | `AuthenticationError` | `AuthenticationError` |
| DH-906 | `AuthenticationError` (text scan) | `AuthenticationError` (errorCode field) |
| HTTP 5xx | `DhanError` (after retries) | `BrokerServerError` (retryable via RetryPolicy) |
| CB open | `DhanError("Circuit breaker open: ...")` | `CircuitOpenError` |
| Network error | `DhanError("HTTP ... failed: ...")` | `RequestException` (retryable) → `BrokerError` wrapper |
| API failure status | `DhanError("API failure: ...")` | `BrokerError("API failure: ...")` |

---

## 10. BREAKING CHANGE: Constructor Argument Order

```
                    ARCHIVE                          GREENFIELD
    ┌──────────────────────────────────┐  ┌──────────────────────────────────┐
    │ DhanHttpClient(                  │  │ DhanHttpClient(                  │
    │     client_id: str,      ← 1st  │  │     access_token: str,   ← 1st  │
    │     access_token: str,   ← 2nd  │  │     client_id: str,      ← 2nd  │
    │     ...                          │  │     ...                          │
    │ )                                │  │ )                                │
    └──────────────────────────────────┘  └──────────────────────────────────┘
```

**Impact**: Any positional call `DhanHttpClient("12345", "token...")` will silently swap credentials. The archive sends `client_id="12345"` and `access_token="token..."`; the greenfield sends `access_token="12345"` and `client_id="token..."`.

**Severity**: **CRITICAL** — No compile-time or runtime error; authentication will fail silently or succeed with wrong identity.

**Mitigation**: Always use keyword arguments, or update all call sites to match the greenfield order `(access_token, client_id)`.
