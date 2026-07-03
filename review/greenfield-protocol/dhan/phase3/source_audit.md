# Phase 3 — Rate Limiting · Source Audit

> **Protocol:** Greenfield Broker Replication — Dhan  
> **Phase:** 3 (Rate Limiting, Circuit Breaking, Retry)  
> **Audit Root (Archive):** `archive/brokers/dhan/`  
> **Audit Root (Greenfield):** `brokers/`  
> **Date:** 2026-07-03

---

## 1. Executive Summary

Phase 3 of the Dhan adapter implements three resilience patterns that protect the trading system from API overload, transient failures, and cascading errors:

- **Rate Limiting** — Token-bucket algorithm throttling outbound HTTP to Dhan's per-endpoint quotas.
- **Circuit Breaking** — Per-category state machines (CLOSED → OPEN → HALF_OPEN) that fast-fail requests when the API is degraded.
- **Retry with Backoff** — Exponential backoff with jitter for transient errors (5xx, 429, network failures).

The archive implementation is mature and battle-tested across 558 lines of HTTP client code, 4 dedicated resilience modules, and 57 chaos tests. The greenfield implementation consolidates the patterns into a `BaseResilientHttpClient` (138 lines) with a Dhan subclass (272 lines), but introduces several regressions documented in the Phase 3+8 Forensic Audit.

**Critical Findings (from audit):**
1. `RATE_LIMITS` values in `config.py` are intervals (seconds/request) but are passed as `rate_per_second` — inverting the intended throttle.
2. HTTP 429 is not retried in greenfield; archive retries with adaptive backoff.
3. Constructor argument order is swapped (`client_id`/`access_token` vs `access_token`/`client_id`).
4. `success_threshold=1` in greenfield CB vs archive's `3` — premature circuit closure.
5. Metrics are not in the request hot path in greenfield.
6. 3 duplicate CB/RL implementations exist across greenfield modules.

---

## 2. Archive Source Files

| File | Lines | Purpose |
|------|------:|---------|
| `archive/brokers/dhan/http_client.py` | 558 | Primary HTTP client with token refresh, retry loop, CB routing, rate limiting, adaptive throttle |
| `archive/brokers/dhan/resilience/circuit_breaker.py` | 120 | Dhan CB factory — 4 categories (orders/market_data/portfolio/admin) with tuned thresholds |
| `archive/brokers/dhan/resilience/rate_limiter.py` | 218 | Token-bucket factory + `DhanRateLimiterMetrics` for observability |
| `archive/brokers/dhan/resilience/retry_executor.py` | 178 | Per-category retry policies with `ExponentialBackoff` integration |
| `archive/brokers/dhan/resilience/websocket_rate_limiter_simple.py` | 156 | WS connection rate limiting (1 conn/s, depth-200 pool management) |
| `archive/brokers/dhan/exceptions.py` | 144 | Exception hierarchy — 15 exception classes with multiple inheritance from common |
| `archive/brokers/dhan/invariants.py` | 264 | Payload identity assertions (security_id + exchangeSegment validation) |
| `archive/brokers/dhan/metrics.py` | 43 | Prometheus counters/histograms (request_total, duration, errors, WS metrics) |
| `archive/brokers/dhan/status_mapper.py` | 41 | Order status normalization (Dhan-specific → canonical OrderStatus) |

**Total archive source lines:** 1,722

### 2.1 Key Symbols — Archive

#### `http_client.py`
- `DhanHttpClient` — Main HTTP client class
- `_categorize_endpoint(endpoint, config)` → `"read" | "write" | "admin"`
- `_rate_limit_bucket(endpoint, config)` → bucket name
- `DhanHttpClient._request(method, endpoint, json)` — 11-step request lifecycle
- `DhanHttpClient._throttle(endpoint)` — Static + adaptive interval throttle
- `DhanHttpClient._acquire_rate_limit_token(endpoint, timeout)` — Token bucket acquisition
- `DhanHttpClient._try_refresh_token()` — Token refresh with cooldown + backoff
- `DhanHttpClient._backoff_delay(attempt)` — Exponential backoff formula
- `DhanHttpClient._parse_retry_after(resp)` — Retry-After header parser
- `DhanHttpClient._send_raw_http(method, url, json)` — Single HTTP attempt

#### `resilience/circuit_breaker.py`
- `DhanCircuitBreakerFactory` — Factory with static methods per category
- `DhanCircuitBreakerFactory.create_orders()` → `CircuitBreaker("dhan-orders", ...)`
- `DhanCircuitBreakerFactory.create_market_data()` → `CircuitBreaker("dhan-market-data", ...)`
- `DhanCircuitBreakerFactory.create_portfolio()` → `CircuitBreaker("dhan-portfolio", ...)`
- `DhanCircuitBreakerFactory.create_admin()` → `CircuitBreaker("dhan-admin", ...)`
- `create_circuit_breakers()` → `dict[str, CircuitBreaker]`
- Constants: `ORDERS_FAILURE_THRESHOLD=3`, `DEFAULT_FAILURE_THRESHOLD=5`, `RECOVERY_TIMEOUT_MS=30_000`, `SUCCESS_THRESHOLD=3`

#### `resilience/rate_limiter.py`
- `DhanRateLimiterFactory` — Factory for `MultiBucketRateLimiter`
- `DhanRateLimiterFactory.create()` → `MultiBucketRateLimiter`
- `DhanRateLimiterFactory.create_config(category)` → `RateLimitConfig`
- `DhanRateLimiterMetrics` — RPS, queue depth, rejection tracking
- Constants: `ORDERS_RATE_PER_SECOND=25.0`, `MARKET_DATA_RATE_PER_SECOND=10.0`, `QUOTE_RATE_PER_SECOND=6.67`, `PORTFOLIO_RATE_PER_SECOND=20.0`, `ADMIN_RATE_PER_SECOND=10.0`

#### `resilience/retry_executor.py`
- `DhanRetryPolicy` — Per-endpoint policy dataclass
- `DhanRetryExecutorFactory.create(category, cb, rl)` → `RetryExecutor`
- Pre-defined policies: `ORDERS_POLICY`, `MARKET_DATA_POLICY`, `PORTFOLIO_POLICY`, `ADMIN_POLICY`
- `create_retry_executor(category, cb, rl)` — Convenience function

#### `resilience/websocket_rate_limiter_simple.py`
- `SimpleWebSocketRateLimiter` — Connection rate limiting (1 conn/s)
- `SimpleWebSocketRateLimiter.can_create_connection()` → bool
- `SimpleWebSocketRateLimiter.can_create_depth_200_connection()` → bool
- `get_dhan_ws_rate_limiter()` — Global singleton accessor

#### `exceptions.py`
- `DhanError(BrokerError)` — Base Dhan exception
- `AuthenticationError(DhanError, _CommonAuthenticationError)` — Token errors
- `OrderError(DhanError, _CommonOrderError)` — Order failures
- `InstrumentNotFoundError(DhanError, _CommonInstrumentNotFoundError)`
- `RateLimitError` — Re-exported from common
- `DhanIdentityError(DhanError)` — Payload identity violations
- `ExitAllError(DhanError, _CommonExitAllError)`

#### `invariants.py`
- `assert_dhan_identity(security_id_or_ref, segment, context)` — Two-shape identity check
- `assert_dhan_segment(segment, context)` — Segment validation
- `assert_dhan_payload(payload, context)` — Dict-level payload check
- `assert_valid_security_id(security_id, context)` — Bare security_id validation

---

## 3. Greenfield Source Files

| File | Lines | Purpose |
|------|------:|---------|
| `brokers/adapters/dhan/http.py` | 272 | Dhan HTTP client — extends `BaseResilientHttpClient`, token refresh, response handling |
| `brokers/resilience/http_client.py` | 138 | Abstract `BaseResilientHttpClient` — CB + RL + retry orchestration |
| `brokers/resilience/circuit_breaker.py` | 139 | Greenfield CB implementation — 3-state machine with `call()` wrapper |
| `brokers/resilience/rate_limiter.py` | 64 | `TokenBucketRateLimiter` — Thread-safe token bucket with condition variable |
| `brokers/resilience/retry.py` | 50 | `RetryPolicy` — Exponential backoff with jitter |
| `brokers/infrastructure/resilience/circuit_breaker.py` | 70 | **DUPLICATE** CB — Alternative implementation with `allow_request()` API |
| `brokers/infrastructure/resilience/rate_limiter.py` | 52 | **DUPLICATE** RL — `TokenBucketRateLimiter` + `MultiBucketRateLimiter` |
| `brokers/infrastructure/resilience/retry_executor.py` | 75 | **DUPLICATE** retry — `RetryExecutor` with CB+RL integration |
| `brokers/adapters/dhan/exceptions.py` | 35 | Dhan exception subclasses (thin wrappers over domain exceptions) |
| `brokers/adapters/dhan/config.py` | 116 | Endpoints, rate limits, prefix maps, exchange/segment mappings |
| `brokers/adapters/dhan/metrics.py` | 66 | Prometheus metrics with `MetricsRegistry` + `observe_metrics` decorator |
| `brokers/domain/exceptions.py` | 123 | Domain exception hierarchy rooted at `TradeXV2Error` |

**Total greenfield source lines:** 1,200 (including 197 lines of duplicate implementations)

### 3.1 Key Symbols — Greenfield

#### `adapters/dhan/http.py`
- `DhanHttpClient(BaseResilientHttpClient)` — Dhan-specific client
- `DhanHttpClient._categorize(endpoint)` → `"read" | "write" | "admin"`
- `DhanHttpClient._build_url(endpoint)` → absolute URL
- `DhanHttpClient._handle_response(resp)` → dict (raises `TokenRefreshSignal` on 401/token error)
- `DhanHttpClient._try_refresh_token()` → `str | None`
- `DhanHttpClient._is_token_error(status_code, error_code, message)` → bool
- `DhanHttpClient._parse_retry_after(resp)` → float (defaults to 30.0)

#### `resilience/http_client.py`
- `BaseResilientHttpClient(ABC)` — Abstract base with CB/RL/retry orchestration
- `TokenRefreshSignal(Exception)` — Internal retry signal
- `BaseResilientHttpClient._request(method, endpoint, **kwargs)` — 5-step lifecycle
- `BaseResilientHttpClient._apply_rate_limit(endpoint)` — Prefix-match rate limiter
- Abstract methods: `_categorize()`, `_build_url()`, `_handle_response()`

#### `resilience/circuit_breaker.py`
- `CircuitBreaker(failure_threshold, recovery_timeout, success_threshold)` — CB with `call()` wrapper
- `CircuitState` — Enum: CLOSED, OPEN, HALF_OPEN
- `CircuitBreakerMetrics` — total_calls, success_count, failure_count, state_changes
- `CircuitBreaker.call(fn, ignored_exceptions)` — Execute with CB protection
- `CircuitBreaker.record_success()` / `record_failure()` — Manual state recording

#### `resilience/rate_limiter.py`
- `TokenBucketRateLimiter(rate_per_second, capacity)` — Token bucket with `threading.Condition`
- `TokenBucketRateLimiter.acquire(tokens, timeout)` → bool

#### `resilience/retry.py`
- `RetryPolicy(max_retries, base_delay_ms, max_delay_ms, retryable_exceptions)`
- `RetryPolicy.call(fn)` → T — Execute with retry
- `RetryPolicy._compute_delay(attempt)` — Exponential backoff + jitter

#### `infrastructure/resilience/circuit_breaker.py` (DUPLICATE)
- `CircuitBreaker(failure_threshold, recovery_timeout, success_threshold=3)` — Alternative CB
- `CircuitState` — Separate enum with `auto()` values
- `CircuitBreaker.allow_request()` → bool — Pull-based API
- `CircuitBreaker.record_success()` / `record_failure()`

#### `infrastructure/resilience/rate_limiter.py` (DUPLICATE)
- `TokenBucketRateLimiter(capacity, rate_per_second)` — Note: arg order swapped vs canonical
- `MultiBucketRateLimiter(configs)` — Multi-category wrapper

#### `infrastructure/resilience/retry_executor.py` (DUPLICATE)
- `RetryExecutor(max_attempts, base_delay, max_delay, cb, rl, rate_limit_category)`
- `RetryExecutor.execute(func)` → T — Unified CB+RL+retry execution

#### `domain/exceptions.py`
- `TradeXV2Error` — Root exception
- `BrokerError(TradeXV2Error)` — Base broker error with `code` attribute
- `RetryableError(BrokerError)` — Transient errors
- `NonRetryableError(BrokerError)` — Permanent errors
- `NetworkError(RetryableError)` — Transport failures
- `BrokerServerError(BrokerError)` — HTTP 5xx
- `RateLimitError(BrokerError)` — HTTP 429 with `retry_after`
- `CircuitOpenError(BrokerError)` — CB open
- `AuthenticationError(BrokerError)` — Token invalid
- `TokenRateLimitError(BrokerError)` — Token generation rate limit
- `InstrumentNotFoundError(BrokerError)` — Symbol resolution failure
- `NotSupportedError(BrokerError)` — Unsupported operation
- `BrokerDegradedError(BrokerError)` — Health below threshold

---

## 4. Archived Test Files

| File | Lines | Tests | Purpose |
|------|------:|------:|---------|
| `archive/brokers/dhan/tests/unit/test_http_client.py` | 81 | 6 | HTTP client unit tests (response unwrapping, 401/429/500, failure status, token update) |
| `archive/brokers/dhan/tests/unit/test_circuit_breaker_regression.py` | 100 | 2 | DH-906 regression — read CB open must not block orders; write CB open must fast-fail |
| `archive/brokers/dhan/tests/unit/test_chaos.py` | 861 | 57 | CB/retry/RL integration: network failure, CB state machine, factory tests, thread safety, retry exhaustion, rate limit enforcement, graceful degradation, recovery, concurrent failures, fault injection |
| `archive/brokers/dhan/tests/unit/test_edge_cases.py` | 229 | 14 | OrderStatus normalization, symbol resolver, order validation, gateway shortcuts |
| `archive/brokers/dhan/tests/integration/test_error_paths.py` | 134 | 10 | Live API error paths (invalid symbols, invalid timeframes, empty queries, missing limit price) |

**Total archived test lines:** 1,405  
**Total archived test count:** 89

---

## 5. Rate Limit Constants Inventory

### 5.1 Archive Rate Limits (Token Bucket — `rate_limiter.py`)

| Category | Rate (req/s) | Capacity | Bucket Name |
|----------|-------------:|---------:|-------------|
| Orders | 25.0 | 25 | `orders` |
| Market Data | 10.0 | 10 | `market_data` |
| Portfolio | 20.0 | 20 | `portfolio` |
| Admin | 10.0 | 10 | `admin` |
| Quote (legacy) | 6.67 | 7 | (mapped via bucket_map) |

### 5.2 Archive Static Rate Limits (Interval-based — `http_client.py._throttle`)

Source: `DhanResilienceConfig.rate_limit.limits` (from `config.py`)

| Endpoint Prefix | Interval (s/req) | Effective Rate |
|----------------|-----------------:|---------------:|
| `/marketfeed/quote` | 1.0 | ~1 req/s |
| `/marketfeed/ltp` | 0.15 | ~6.7 req/s |
| `/marketfeed/ohlc` | 0.15 | ~6.7 req/s |
| `/optionchain` | 0.35 | ~2.9 req/s |
| `/charts/` | 0.15 | ~6.7 req/s |
| `/orders` | 0.04 | 25 req/s |

### 5.3 Greenfield Rate Limits (`config.py.RATE_LIMITS`)

| Endpoint Prefix | Value | Comment | Interpretation |
|----------------|------:|---------|----------------|
| `/marketfeed/quote` | 1.0 | 1 req/s | Interval (s/req) |
| `/marketfeed/ltp` | 0.15 | ~6.7 req/s | Interval (s/req) |
| `/marketfeed/ohlc` | 0.15 | ~6.7 req/s | Interval (s/req) |
| `/optionchain` | 0.35 | ~2.9 req/s | Interval (s/req) |
| `/charts/` | 0.15 | ~6.7 req/s | Interval (s/req) |
| `/orders` | 0.04 | 25 req/s | Interval (s/req) |

**BUG (CRITICAL):** These values are intervals (seconds per request) but are passed to `TokenBucketRateLimiter(rate_per_second=rate, ...)` in `BaseResilientHttpClient.__init__`, inverting the intended throttle. A value of `0.04` (intended: 25 req/s) becomes 0.04 req/s (1 req per 25 seconds).

---

## 6. Circuit Breaker Thresholds Inventory

### 6.1 Archive CB Thresholds (`resilience/circuit_breaker.py`)

| Category | failure_threshold | success_threshold | open_duration_ms | CB Name |
|----------|------------------:|------------------:|-----------------:|---------|
| Orders | 3 | 3 | 30,000 (30s) | `dhan-orders` |
| Market Data | 5 | 3 | 30,000 (30s) | `dhan-market-data` |
| Portfolio | 5 | 3 | 30,000 (30s) | `dhan-portfolio` |
| Admin | 5 | 3 | 30,000 (30s) | `dhan-admin` |

### 6.2 Greenfield CB Thresholds (`resilience/http_client.py` — hardcoded in `BaseResilientHttpClient`)

| Category | failure_threshold | success_threshold | recovery_timeout (s) | Notes |
|----------|------------------:|------------------:|---------------------:|-------|
| read | 5 | 1 (default) | 30.0 | Maps to market_data endpoints |
| write | 3 | 1 (default) | 60.0 | Maps to order endpoints |
| admin | 5 | 1 (default) | 30.0 | Default category |

**Divergences:**
- `success_threshold=1` (greenfield) vs `3` (archive) — single success closes half-open circuit prematurely.
- `recovery_timeout=60.0` for write (greenfield) vs `30.0` (archive) — doubled open duration.
- No `portfolio` category in greenfield — portfolio endpoints fall into `admin` CB.

### 6.3 Duplicate CB (`infrastructure/resilience/circuit_breaker.py`)

| Parameter | Default |
|-----------|--------:|
| failure_threshold | 5 |
| recovery_timeout | 30.0 |
| success_threshold | 3 |

Note: This implementation uses `allow_request()` (pull-based) vs `call()` (push-based) in the canonical greenfield CB.

---

## 7. Retry Policies Inventory

### 7.1 Archive Retry Policies (`resilience/retry_executor.py`)

| Category | max_attempts | base_delay_ms | max_delay_ms | Backoff Multiplier | Jitter |
|----------|-------------:|--------------:|-------------:|-------------------:|-------:|
| Orders | 3 | 1,000 | 8,000 | 2.0× | ±20% |
| Market Data | 2 | 500 | 4,000 | 2.0× | ±20% |
| Portfolio | 3 | 1,000 | 8,000 | 2.0× | ±20% |
| Admin | 3 | 1,000 | 8,000 | 2.0× | ±20% |

Archive backoff formula (in `http_client.py._backoff_delay`):
```
delay_ms = min(base_delay_ms × 2^(attempt-1), max_delay_ms)
```
Default: 500ms × 2^(attempt-1), capped at 5,000ms (from `DEFAULT_CONFIG.retry`).

### 7.2 Greenfield Retry Policy (`resilience/http_client.py` — single global policy)

| Parameter | Value |
|-----------|------:|
| max_retries | 3 |
| base_delay_ms | 500 |
| max_delay_ms | 5,000 |
| retryable_exceptions | `(RequestException, BrokerServerError)` |

Greenfield backoff formula (`retry.py._compute_delay`):
```
delay_ms = min(base_delay_ms × 2^attempt, max_delay_ms) + jitter
jitter = random.randint(0, delay_ms // 4)
```

**Divergences:**
- No per-category retry policies in greenfield (single global policy).
- Market data gets 3 retries in greenfield vs 2 in archive.
- Max delay 5s (greenfield) vs 8s (archive orders/portfolio).
- 429 not retried in greenfield (raises `RateLimitError` immediately).

---

## 8. Exception Hierarchy

### 8.1 Archive Exception Hierarchy

```
BrokerError (brokers.common.resilience.errors)
└── DhanError (brokers.dhan.exceptions)
    ├── AuthenticationError (+ _CommonAuthenticationError)
    ├── InstrumentNotFoundError (+ _CommonInstrumentNotFoundError)
    ├── MarketDataError
    ├── OrderError (+ _CommonOrderError)
    ├── ConfigurationError
    ├── DhanIdentityError
    ├── SuperOrderError
    ├── ForeverOrderError
    ├── ConditionalTriggerError
    ├── LedgerError
    ├── UserProfileError
    ├── IPManagementError
    ├── ExitAllError (+ _CommonExitAllError)
    └── EDISError

RateLimitError — re-exported from brokers.common.resilience.errors
```

### 8.2 Greenfield Exception Hierarchy

```
TradeXV2Error (brokers.domain.exceptions)
├── ConfigError
├── DataError
├── ValidationError
└── BrokerError (code: str)
    ├── RetryableError
    │   └── NetworkError
    ├── NonRetryableError
    ├── BrokerServerError
    ├── OrderRejectedError (order_id: str)
    ├── RateLimitError (retry_after: float | None)
    ├── CircuitOpenError
    ├── AuthenticationError
    ├── TokenRateLimitError
    ├── InstrumentNotFoundError (symbol: str)
    ├── NotSupportedError
    ├── BrokerDegradedError (health_status: dict)
    └── DhanError (brokers.adapters.dhan.exceptions)
        ├── DhanAuthenticationError
        ├── DhanRateLimitError
        ├── DhanOrderRejectedError
        ├── DhanConnectionError
        └── DhanServerError
```

---

## 9. Summary of Gaps

| # | Finding | Severity | Archive | Greenfield |
|---|---------|----------|---------|------------|
| 1 | RATE_LIMITS inversion bug | CRITICAL | Intervals used correctly in `_throttle()` | Passed as `rate_per_second` — inverted |
| 2 | 429 not retried | CRITICAL | Retried with adaptive backoff | Raises `RateLimitError` immediately |
| 3 | Constructor arg order swapped | CRITICAL | `client_id, access_token` | `access_token, client_id` |
| 4 | success_threshold=1 | HIGH | `success_threshold=3` | `success_threshold=1` (default) |
| 5 | Metrics not in hot path | HIGH | `dhan_request_total.inc()` in `_request()` | Metrics via decorator, not in `_request()` |
| 6 | 3 duplicate CB/RL implementations | HIGH | Single canonical implementation | `resilience/` + `infrastructure/resilience/` duplicates |
| 7 | Write CB open_duration 60s vs 30s | MEDIUM | 30,000ms for all categories | 60.0s for write |
| 8 | DH-906 text scan vs structured key | MEDIUM | `"DH-906" in body` text scan | `error_code in token_error_codes` structured check |
| 9 | No portfolio CB category | MEDIUM | 4 categories (orders/market_data/portfolio/admin) | 3 categories (read/write/admin) |
| 10 | No invariants module | MEDIUM | 264 lines of payload identity assertions | Not ported |
| 11 | No WS rate limiter | MEDIUM | `SimpleWebSocketRateLimiter` (156 lines) | Not ported |
