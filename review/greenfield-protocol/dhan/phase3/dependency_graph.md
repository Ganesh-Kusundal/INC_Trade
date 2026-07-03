# Phase 3 — Rate Limiting · Dependency Graph

> **Protocol:** Greenfield Broker Replication — Dhan  
> **Phase:** 3 (Rate Limiting, Circuit Breaking, Retry)  
> **Date:** 2026-07-03

---

## 1. Archive Internal Dependencies

### 1.1 Module Import Graph

```
brokers/dhan/http_client.py
├── brokers/common/resilience/circuit_breaker.py
│   ├── CircuitBreaker
│   └── CircuitState
├── brokers/common/resilience/rate_limiter.py
│   └── MultiBucketRateLimiter
├── brokers/dhan/config.py
│   ├── DhanResilienceConfig
│   └── DEFAULT_CONFIG
├── brokers/dhan/exceptions.py
│   ├── AuthenticationError
│   ├── DhanError
│   └── RateLimitError (re-exported from common)
├── brokers/dhan/metrics.py
│   ├── dhan_errors_total
│   ├── dhan_request_duration_seconds
│   └── dhan_request_total
├── brokers/dhan/resilience/rate_limiter.py
│   └── DhanRateLimiterMetrics
├── config/endpoints.py
│   └── Dhan.REST_BASE
└── brokers/common/ssl_hardening.py
    └── create_pinned_session()

brokers/dhan/resilience/circuit_breaker.py
├── brokers/common/resilience/circuit_breaker.py
│   ├── CircuitBreaker
│   └── CircuitBreakerConfig
└── (dataclasses — stdlib)

brokers/dhan/resilience/rate_limiter.py
├── brokers/common/resilience/rate_limiter.py
│   ├── MultiBucketRateLimiter
│   └── RateLimitConfig
└── (logging, threading, time — stdlib)

brokers/dhan/resilience/retry_executor.py
├── brokers/common/resilience/backoff.py
│   └── ExponentialBackoff
├── brokers/common/resilience/circuit_breaker.py
│   └── CircuitBreaker
├── brokers/common/resilience/rate_limiter.py
│   └── MultiBucketRateLimiter
├── brokers/common/resilience/retry.py
│   ├── RetryConfig
│   └── RetryExecutor
└── (logging — stdlib)

brokers/dhan/resilience/websocket_rate_limiter_simple.py
└── (logging, threading, time — stdlib)

brokers/dhan/exceptions.py
├── brokers/common/resilience/errors.py
│   ├── BrokerError
│   ├── RateLimitError
│   ├── AuthenticationError (as _CommonAuthenticationError)
│   ├── InstrumentNotFoundError (as _CommonInstrumentNotFoundError)
│   ├── OrderError (as _CommonOrderError)
│   └── ExitAllError (as _CommonExitAllError)
└── (multiple inheritance for isinstance compatibility)

brokers/dhan/invariants.py
├── brokers/dhan/exceptions.py
│   └── DhanIdentityError
└── brokers/dhan/identity.py
    ├── DHAN_SEGMENTS
    └── is_dhan_segment()

brokers/dhan/metrics.py
└── infrastructure/metrics/registry.py
    └── metrics_registry (Counter, Histogram, Gauge)

brokers/dhan/status_mapper.py
├── domain/__init__.py
│   └── OrderStatus
├── domain/status_mapper.py
│   ├── COMMON_STATUS_MAP
│   └── StatusMapperRegistry
└── brokers/common/identity.py
    └── BrokerId
```

### 1.2 External Dependencies (Archive)

| Dependency | Used By | Purpose |
|-----------|---------|---------|
| `requests` | `http_client.py` | HTTP session, request execution |
| `threading` | `http_client.py`, `rate_limiter.py`, `websocket_rate_limiter_simple.py` | Lock-based thread safety |
| `time` | `http_client.py`, `rate_limiter.py`, `websocket_rate_limiter_simple.py` | `time.sleep()`, `time.time()`, `time.monotonic()` |
| `logging` | All modules | Structured logging with `extra={}` dicts |
| `dataclasses` | `circuit_breaker.py`, `rate_limiter.py`, `retry_executor.py` | `@dataclass` for config objects |
| `prometheus_client` (via `infrastructure.metrics`) | `metrics.py` | Counters, histograms, gauges |

---

## 2. Greenfield Internal Dependencies

### 2.1 Module Import Graph

```
brokers/adapters/dhan/http.py
├── brokers/adapters/dhan/config.py
│   ├── ENDPOINTS
│   ├── RATE_LIMITS
│   ├── READ_PREFIXES
│   └── WRITE_PREFIXES
├── brokers/domain/exceptions.py
│   ├── AuthenticationError
│   ├── BrokerError
│   ├── BrokerServerError
│   └── RateLimitError
└── brokers/resilience/http_client.py
    ├── BaseResilientHttpClient
    └── TokenRefreshSignal

brokers/resilience/http_client.py
├── brokers/domain/exceptions.py
│   ├── AuthenticationError
│   ├── BrokerError
│   ├── BrokerServerError
│   └── RateLimitError
├── brokers/resilience/circuit_breaker.py
│   └── CircuitBreaker
├── brokers/resilience/rate_limiter.py
│   └── TokenBucketRateLimiter
├── brokers/resilience/retry.py
│   └── RetryPolicy
└── brokers/infrastructure/ssl_hardening.py (optional)
    └── create_pinned_session()

brokers/resilience/circuit_breaker.py
├── brokers/domain/exceptions.py
│   └── CircuitOpenError
└── (threading, time, enum, dataclasses — stdlib)

brokers/resilience/rate_limiter.py
└── (threading, time — stdlib)

brokers/resilience/retry.py
└── (random, time — stdlib)

brokers/adapters/dhan/exceptions.py
└── brokers/domain/exceptions.py
    ├── AuthenticationError
    ├── BrokerError
    ├── BrokerServerError
    ├── NetworkError
    ├── OrderRejectedError
    └── RateLimitError

brokers/adapters/dhan/config.py
└── (no internal dependencies — pure configuration)

brokers/adapters/dhan/metrics.py
├── prometheus_client
│   ├── Counter
│   └── Histogram
└── (logging, functools, time — stdlib)

brokers/domain/exceptions.py
└── brokers/domain/error_codes.py
    ├── AUTH_ERROR
    ├── BROKER_DEGRADED
    ├── CIRCUIT_OPEN
    ├── INSTRUMENT_NOT_FOUND
    ├── NOT_SUPPORTED
    └── RATE_LIMITED

─── DUPLICATE IMPLEMENTATIONS ──────────────────────────────────────────────

brokers/infrastructure/resilience/circuit_breaker.py
└── (time, threading, enum — stdlib)
    NOTE: No import of domain exceptions; raises bare Exception

brokers/infrastructure/resilience/rate_limiter.py
└── (time, threading — stdlib)

brokers/infrastructure/resilience/retry_executor.py
├── .circuit_breaker.py (local — infrastructure copy)
│   └── CircuitBreaker
└── .rate_limiter.py (local — infrastructure copy)
    └── MultiBucketRateLimiter
```

### 2.2 External Dependencies (Greenfield)

| Dependency | Used By | Purpose |
|-----------|---------|---------|
| `requests` | `resilience/http_client.py` | HTTP session, request execution |
| `threading` | `resilience/circuit_breaker.py`, `resilience/rate_limiter.py`, `adapters/dhan/http.py` | Lock/Condition-based thread safety |
| `time` | `resilience/circuit_breaker.py`, `resilience/rate_limiter.py`, `adapters/dhan/http.py` | `time.sleep()`, `time.monotonic()` |
| `random` | `resilience/retry.py` | Jitter computation |
| `logging` | All modules | Standard logging |
| `prometheus_client` | `adapters/dhan/metrics.py` | Direct Counter/Histogram (not via registry) |
| `dataclasses` | `resilience/circuit_breaker.py` | `CircuitBreakerMetrics` |
| `enum` | `resilience/circuit_breaker.py` | `CircuitState` enum |
| `abc` | `resilience/http_client.py` | `ABC`, `abstractmethod` |

---

## 3. Cross-Phase Dependencies

### 3.1 Phase 1 (Authentication) Dependencies

| Archive | Greenfield | Phase 1 Feature |
|---------|------------|-----------------|
| `DhanHttpClient._token_refresh_fn` | `DhanHttpClient._token_refresh_fn` | Token refresh callback injection |
| `DhanHttpClient._try_refresh_token()` | `DhanHttpClient._try_refresh_token()` | Token refresh with cooldown + backoff |
| `DhanHttpClient.update_token()` | `DhanHttpClient.update_token()` | Token update in session headers |
| N/A | `DhanHttpClient._refresh_lock` | Shared lock for concurrent refresh (greenfield adds this) |
| `config.token.refresh_cooldown_seconds` | `_REFRESH_COOLDOWN_SECONDS = 60.0` | Minimum time between refresh attempts |
| `config.token.rate_limit_backoff_seconds` | `_RATE_LIMIT_BACKOFF_SECONDS = 130.0` | Backoff when Dhan rate limits token generation |

### 3.2 Phase 0 (Foundation/Config) Dependencies

| Archive | Greenfield | Phase 0 Feature |
|---------|------------|-----------------|
| `brokers/dhan/config.py` → `DhanResilienceConfig` | `brokers/adapters/dhan/config.py` → `RATE_LIMITS`, `READ_PREFIXES`, `WRITE_PREFIXES` | Resilience configuration |
| `config/endpoints.py` → `Dhan.REST_BASE` | `brokers/adapters/dhan/config.py` → `REST_BASE`, `ENDPOINTS` | Endpoint registry |
| `DEFAULT_CONFIG` (comprehensive resilience config) | Hardcoded in `BaseResilientHttpClient.__init__()` | Default thresholds |
| `brokers/common/resilience/*` (shared patterns) | `brokers/resilience/*` (greenfield patterns) | Common resilience primitives |

### 3.3 Cross-Phase Coupling Diagram

```
Phase 0 (Foundation)
    │
    ├── config.py ─────────────────────────────────────────────┐
    │   └── REST_BASE, ENDPOINTS, RATE_LIMITS                  │
    │                                                          │
    ├── domain/exceptions.py ──────────────────────────────┐   │
    │   └── BrokerError, RateLimitError, CircuitOpenError  │   │
    │                                                      │   │
    │                                                      ▼   ▼
Phase 1 (Authentication)                              Phase 3 (Rate Limiting)
    │                                                      │
    ├── token_refresh_fn ──────────────────────────────────▶│
    │   (injected callback)                                 │
    │                                                       │
    ├── refresh_cooldown ──────────────────────────────────▶│
    │                                                       │
    └── refresh_lock ──────────────────────────────────────▶│
        (concurrent refresh safety)                         │
                                                            │
Phase 3 Internal:                                           │
    ├── config.py ──────────────────────────────────────────┘
    │   └── RATE_LIMITS, READ_PREFIXES, WRITE_PREFIXES
    │
    ├── resilience/circuit_breaker.py
    │   └── CircuitBreaker, CircuitState
    │
    ├── resilience/rate_limiter.py
    │   └── TokenBucketRateLimiter
    │
    └── resilience/retry.py
        └── RetryPolicy
```

---

## 4. Dependency Diagram (ASCII)

### 4.1 Archive Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ARCHIVE DEPENDENCY GRAPH                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────┐                                                    │
│  │  config/endpoints.py│──── Dhan.REST_BASE ────┐                          │
│  └─────────────────────┘                         │                          │
│                                                   ▼                          │
│  ┌─────────────────────┐    ┌──────────────────────────────────────┐       │
│  │  brokers/dhan/      │───▶│  brokers/dhan/http_client.py         │       │
│  │  config.py          │    │  ┌─────────────────────────────────┐ │       │
│  │  ┌───────────────┐  │    │  │  DhanHttpClient                 │ │       │
│  │  │DhanResilience │  │    │  │  - _request()                   │ │       │
│  │  │Config         │  │    │  │  - _throttle()                  │ │       │
│  │  │DEFAULT_CONFIG │  │    │  │  - _acquire_rate_limit_token()  │ │       │
│  │  └───────────────┘  │    │  │  - _try_refresh_token()         │ │       │
│  └─────────────────────┘    │  └─────────────────────────────────┘ │       │
│                              └──────────────────────────────────────┘       │
│                                  │         │         │                      │
│                    ┌─────────────┘         │         └──────────────┐       │
│                    ▼                       ▼                        ▼       │
│  ┌──────────────────────────┐  ┌────────────────────┐  ┌─────────────────┐ │
│  │ brokers/common/resilience│  │ brokers/dhan/      │  │ brokers/dhan/   │ │
│  │ ┌──────────────────────┐│  │ metrics.py         │  │ exceptions.py   │ │
│  │ │ circuit_breaker.py   ││  │ ┌────────────────┐ │  │ ┌─────────────┐ │ │
│  │ │ CircuitBreaker       ││  │ │dhan_request_   │ │  │ │DhanError    │ │ │
│  │ │ CircuitState         ││  │ │total           │ │  │ │AuthError    │ │ │
│  │ ├──────────────────────┤│  │ │dhan_errors_    │ │  │ │RateLimitErr │ │ │
│  │ │ rate_limiter.py      ││  │ │total           │ │  │ └─────────────┘ │ │
│  │ │ MultiBucketRateLimiter│  │ │dhan_request_   │ │  └─────────────────┘ │
│  │ │ RateLimitConfig      ││  │ │duration_seconds│ │                      │
│  │ ├──────────────────────┤│  │ └────────────────┘ │                      │
│  │ │ retry.py             ││  └────────────────────┘                      │
│  │ │ RetryExecutor        ││                                              │
│  │ │ RetryConfig          ││  ┌────────────────────────────────────────┐  │
│  │ ├──────────────────────┤│  │ brokers/dhan/resilience/               │  │
│  │ │ backoff.py           ││  │ ┌──────────────────────────────────┐   │  │
│  │ │ ExponentialBackoff   ││  │ │ circuit_breaker.py               │   │  │
│  │ └──────────────────────┘│  │ │ DhanCircuitBreakerFactory        │   │  │
│  └──────────────────────────┘  │ │ create_circuit_breakers()        │   │  │
│                                │ ├──────────────────────────────────┤   │  │
│                                │ │ rate_limiter.py                  │   │  │
│                                │ │ DhanRateLimiterFactory           │   │  │
│                                │ │ DhanRateLimiterMetrics           │   │  │
│                                │ │ create_rate_limiter()            │   │  │
│                                │ ├──────────────────────────────────┤   │  │
│                                │ │ retry_executor.py                │   │  │
│                                │ │ DhanRetryPolicy                  │   │  │
│                                │ │ DhanRetryExecutorFactory         │   │  │
│                                │ │ ORDERS_POLICY, MARKET_DATA_POLICY│   │  │
│                                │ ├──────────────────────────────────┤   │  │
│                                │ │ websocket_rate_limiter_simple.py │   │  │
│                                │ │ SimpleWebSocketRateLimiter       │   │  │
│                                │ └──────────────────────────────────┘   │  │
│                                └────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────┐  ┌────────────────────────────────────────┐  │
│  │ brokers/dhan/            │  │ infrastructure/metrics/registry.py     │  │
│  │ invariants.py            │  │ ┌────────────────────────────────────┐ │  │
│  │ assert_dhan_identity()   │  │ │ metrics_registry                   │ │  │
│  │ assert_dhan_payload()    │  │ │ .counter() .histogram() .gauge()   │ │  │
│  │ assert_dhan_segment()    │  │ └────────────────────────────────────┘ │  │
│  └──────────────────────────┘  └────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Greenfield Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       GREENFIELD DEPENDENCY GRAPH                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ brokers/adapters/dhan/http.py                                       │    │
│  │ ┌───────────────────────────────────────────────────────────────┐   │    │
│  │ │ DhanHttpClient(BaseResilientHttpClient)                       │   │    │
│  │ │ - _categorize()  - _build_url()  - _handle_response()        │   │    │
│  │ │ - _try_refresh_token()  - _is_token_error()                  │   │    │
│  │ └───────────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                    │                    │                            │
│       ▼                    ▼                    ▼                            │
│  ┌──────────────┐  ┌────────────────────┐  ┌──────────────────────────┐    │
│  │adapters/dhan/│  │resilience/         │  │domain/exceptions.py      │    │
│  │config.py     │  │http_client.py      │  │ ┌──────────────────────┐ │    │
│  │ ┌──────────┐ │  │ ┌────────────────┐ │  │ │TradeXV2Error         │ │    │
│  │ │RATE_LIMITS│ │  │ │BaseResilient   │ │  │ │ └──BrokerError       │ │    │
│  │ │READ_PREF │ │  │ │HttpClient      │ │  │ │    ├──RetryableError  │ │    │
│  │ │WRITE_PREF│ │  │ │ ._request()    │ │  │ │    ├──BrokerServerErr │ │    │
│  │ │ENDPOINTS │ │  │ │ ._apply_rate_  │ │  │ │    ├──RateLimitError  │ │    │
│  │ └──────────┘ │  │ │  limit()       │ │  │ │    ├──CircuitOpenErr  │ │    │
│  └──────────────┘  │ └────────────────┘ │  │ │    ├──AuthError       │ │    │
│                     └────────────────────┘  │ └──────────────────────┘ │    │
│                              │              └──────────────────────────┘    │
│                ┌─────────────┼─────────────┐                                │
│                ▼             ▼             ▼                                 │
│  ┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐                │
│  │resilience/       │ │resilience/   │ │resilience/       │                │
│  │circuit_breaker.py│ │rate_limiter.py│ │retry.py          │                │
│  │ ┌──────────────┐ │ │ ┌──────────┐ │ │ ┌──────────────┐ │                │
│  │ │CircuitBreaker│ │ │ │TokenBuck │ │ │ │RetryPolicy   │ │                │
│  │ │CircuitState  │ │ │ │RateLimiter│ │ │ │ ._call()     │ │                │
│  │ │CircuitBreaker│ │ │ │ ._refill()│ │ │ │ ._compute_   │ │                │
│  │ │Metrics       │ │ │ │ ._acquire │ │ │ │  delay()     │ │                │
│  │ └──────────────┘ │ │ └──────────┘ │ │ └──────────────┘ │                │
│  └──────────────────┘ └──────────────┘ └──────────────────┘                │
│                                                                             │
│  ═══════════════════ DUPLICATE IMPLEMENTATIONS ═══════════════════════════   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ brokers/infrastructure/resilience/                                  │    │
│  │ ┌────────────────────────┐ ┌─────────────────────┐ ┌─────────────┐ │    │
│  │ │ circuit_breaker.py     │ │ rate_limiter.py     │ │retry_exec.py│ │    │
│  │ │ ┌────────────────────┐ │ │ ┌─────────────────┐ │ │ ┌─────────┐ │ │    │
│  │ │ │CircuitBreaker      │ │ │ │TokenBucketRate  │ │ │ │Retry    │ │ │    │
│  │ │ │ (allow_request API)│ │ │ │Limiter          │ │ │ │Executor │ │ │    │
│  │ │ │ success_threshold=3│ │ │ │ (arg order      │ │ │ │ (CB+RL  │ │ │    │
│  │ │ │ (different from    │ │ │ │  swapped vs     │ │ │ │  unified│ │ │    │
│  │ │ │  canonical CB)     │ │ │ │  canonical RL)  │ │ │ │  execute│ │ │    │
│  │ │ └────────────────────┘ │ │ ├─────────────────┤ │ │ └─────────┘ │ │    │
│  │ └────────────────────────┘ │ │MultiBucketRate  │ │ └─────────────┘ │    │
│  │                             │ │Limiter          │ │                  │    │
│  │                             │ └─────────────────┘ │                  │    │
│  │  NOTE: These are NOT imported by the active HTTP client path.       │    │
│  │  They exist as legacy/alternative implementations.                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ adapters/dhan/metrics.py                                            │    │
│  │ ┌───────────────────────────────────────────────────────────────┐   │    │
│  │ │ MetricsRegistry (static methods)                              │   │    │
│  │ │ observe_metrics (decorator — NOT applied to any active code)  │   │    │
│  │ │ DHAN_REQUESTS_TOTAL, DHAN_REQUEST_ERRORS, DHAN_REQUEST_DURATION│  │    │
│  │ └───────────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Greenfield Duplicate Implementation Problem

### 5.1 Three Circuit Breaker Implementations

| # | Location | Lines | API Style | success_threshold | Used By |
|---|----------|------:|-----------|------------------:|---------|
| 1 | `brokers/resilience/circuit_breaker.py` | 139 | `call(fn, ignored_exceptions)` | 1 (default) | `BaseResilientHttpClient` |
| 2 | `brokers/infrastructure/resilience/circuit_breaker.py` | 70 | `allow_request()` + `record_success()`/`record_failure()` | 3 | `infrastructure/resilience/retry_executor.py` |
| 3 | `brokers/common/resilience/circuit_breaker.py` (archive) | ~200 | `CircuitBreaker(name, CircuitBreakerConfig)` | Configurable | Archive HTTP client |

**Problem:** Implementations 1 and 2 have incompatible APIs. Implementation 1 uses a push-based `call()` wrapper; implementation 2 uses a pull-based `allow_request()` check. Code written for one cannot use the other without refactoring.

### 5.2 Three Rate Limiter Implementations

| # | Location | Lines | Constructor Arg Order | Features | Used By |
|---|----------|------:|----------------------|----------|---------|
| 1 | `brokers/resilience/rate_limiter.py` | 64 | `(rate_per_second, capacity)` | `threading.Condition`, blocking `acquire()` | `BaseResilientHttpClient` |
| 2 | `brokers/infrastructure/resilience/rate_limiter.py` | 52 | `(capacity, rate_per_second)` | `time.sleep(0.01)` polling, `MultiBucketRateLimiter` | `infrastructure/resilience/retry_executor.py` |
| 3 | `brokers/common/resilience/rate_limiter.py` (archive) | ~150 | `RateLimitConfig(rate_per_second, capacity)` | `MultiBucketRateLimiter` with named categories | Archive HTTP client |

**Problem:** Implementations 1 and 2 have **swapped constructor argument order** (`rate_per_second, capacity` vs `capacity, rate_per_second`). Passing arguments in the wrong order silently creates a misconfigured limiter. Implementation 2 also includes `MultiBucketRateLimiter` which is absent from implementation 1.

### 5.3 Three Retry Implementations

| # | Location | Lines | API | Features | Used By |
|---|----------|------:|-----|----------|---------|
| 1 | `brokers/resilience/retry.py` | 50 | `RetryPolicy.call(fn)` | Exponential backoff + jitter, exception filtering | `BaseResilientHttpClient` |
| 2 | `brokers/infrastructure/resilience/retry_executor.py` | 75 | `RetryExecutor.execute(fn)` | Unified CB+RL+retry, string-based error detection | Standalone |
| 3 | `brokers/common/resilience/retry.py` (archive) | ~100 | `RetryExecutor.execute(fn)` | `RetryConfig` + `ExponentialBackoff` + CB/RL integration | Archive |

**Problem:** Implementation 2 uses string-based error detection (`"5xx" in str(e).lower()`) rather than type-based exception filtering. This is fragile and can produce false positives/negatives.

### 5.4 Consolidation Recommendation

```
CURRENT STATE (3 implementations each):

  adapters/dhan/http.py
       │
       ▼
  resilience/http_client.py ──────▶ resilience/circuit_breaker.py (CB #1)
       │                        ──▶ resilience/rate_limiter.py (RL #1)
       │                        ──▶ resilience/retry.py (Retry #1)
       │
       │  (unused duplicates)
       ├──▶ infrastructure/resilience/circuit_breaker.py (CB #2)
       ├──▶ infrastructure/resilience/rate_limiter.py (RL #2)
       └──▶ infrastructure/resilience/retry_executor.py (Retry #2)

TARGET STATE (single canonical implementation):

  adapters/dhan/http.py
       │
       ▼
  resilience/http_client.py ──────▶ resilience/circuit_breaker.py
       │                        ──▶ resilience/rate_limiter.py
       │                        ──▶ resilience/retry.py
       │
       │  (infrastructure/resilience/ deleted or aliased to canonical)
```

---

## 6. Dependency Summary Matrix

| Module | Archive Imports | Greenfield Imports | External Deps | Phase 1 Deps | Phase 0 Deps |
|--------|----------------|-------------------|---------------|--------------|--------------|
| HTTP Client | CB, RL, config, exceptions, metrics, SSL | config, domain exceptions, BaseResilientHttpClient | `requests`, `threading`, `time` | `token_refresh_fn`, refresh cooldown | `REST_BASE`, `ENDPOINTS` |
| Circuit Breaker | common CB + CBConfig | domain exceptions (`CircuitOpenError`) | `threading`, `time`, `enum` | — | — |
| Rate Limiter | common RL + RateLimitConfig | — | `threading`, `time` | — | — |
| Retry | common backoff, CB, RL, retry | — | `random`, `time` | — | — |
| Exceptions | common resilience errors | domain exceptions, error_codes | — | — | — |
| Config | — | — | — | — | `DEFAULT_CONFIG` (archive) |
| Metrics | infrastructure metrics registry | `prometheus_client` directly | `prometheus_client` | — | — |
| Invariants | dhan exceptions, dhan identity | **NOT PORTED** | — | — | — |
| WS Rate Limiter | — | **NOT PORTED** | `threading`, `time` | — | — |
| Status Mapper | domain OrderStatus, status_mapper | **NOT PORTED** | — | — | — |
