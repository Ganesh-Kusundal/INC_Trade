# Phase 5 — Cross-Cutting Concerns Audit

**Date:** 2026-07-02

---

## 1. Exception Hierarchy

### 1.1 Current Hierarchy

```
TradeXV2Error                              # Root
├── BrokerError                            # Broker communication failures
│   ├── AuthenticationError                # Auth/token failures
│   ├── BrokerDegradedError                # Broker partially unavailable
│   ├── BrokerUnavailableError             # Broker completely down
│   ├── OrderError                         # Order execution failures
│   ├── DataError                          # Market data failures
│   ├── StreamError                        # WebSocket transport failures
│   │   ├── StreamAuthError                # WebSocket auth failures
│   │   └── StreamStalenessError           # Stream data too old
│   ├── InstrumentNotFoundError            # Symbol resolution failure
│   ├── NotSupportedError                  # Unsupported operation
│   └── ExitAllError                       # Emergency exit
├── CircuitBreakerOpenError                # Circuit breaker tripped
├── RateLimitError                         # API quota exceeded
├── RetryableError                         # Explicitly retryable
├── NonRetryableError                      # Explicitly non-retryable
├── ValidationError                        # Input validation failure
├── ConfigError                            # Configuration error
├── QuotaExhaustedError                    # Quota scheduler depleted
├── RoutingError                           # Broker routing failure
├── HistoricalFetchError                   # Historical data fetch failure
├── MergeConflictError                     # Historical data merge conflict
├── UnsupportedGatewayOperationError       # Gateway doesn't implement method
├── BrokerNotReadyError                    # Bootstrap/readiness failure
└── TotpRateLimitError                     # TOTP cooldown active
```

### 1.2 Assessment

| Criterion | Status | Detail |
|-----------|--------|--------|
| Consistent hierarchy | **YES** | Single root (TradeXV2Error), clear categorization |
| Domain exceptions | **YES** | DomainError, InvalidOrderError in domain/ |
| Infrastructure exceptions | **YES** | BrokerError, StreamError, etc. |
| Transport exceptions | **YES** | StreamError, StreamAuthError |
| Authentication exceptions | **YES** | AuthenticationError, BrokerAuthError |
| Retryable vs non-retryable | **YES** | Explicit RetryableError / NonRetryableError markers |
| Validation exceptions | **YES** | ValidationError |
| Business exceptions | **PARTIAL** | DomainError exists but limited domain-specific exceptions |

### 1.3 Gaps

| Gap | Severity | Recommendation |
|-----|----------|---------------|
| No `InsufficientMarginError` | MEDIUM | Add for pre-trade risk checks |
| No `MarketClosedError` | MEDIUM | Add for market hours validation |
| No `DuplicateOrderError` | LOW | Idempotency layer could use specific exception |
| `BrokerDegradedError` vs `BrokerUnavailableError` distinction unclear | LOW | Document degradation threshold |

---

## 2. Error Reporting

### 2.1 Structured Errors

| Feature | Implementation | Quality |
|---------|---------------|---------|
| Error messages | Exception classes with descriptive messages | GOOD |
| Correlation IDs | `ContextVar`-based, propagated through async boundaries | EXCELLENT |
| Request IDs | Via correlation ID mechanism | GOOD |
| Root-cause preservation | Exception chaining (`raise ... from ...`) | NEEDS VERIFICATION |
| Diagnostic information | `BrokerNotReadyError` includes broker, status, context | GOOD |

### 2.2 Audit Events

Rich structured audit event schemas in `observability/audit.py`:

| Event | Fields |
|-------|--------|
| `RoutingDecisionEvent` | trace_id, operation, broker, reason |
| `QuotaEvent` | broker, endpoint, priority, acquired, wait_ms |
| `HistoricalChunkEvent` | broker, symbol, range, bars, duration_ms |
| `StreamStateChangeEvent` | broker, stream, old_state, new_state |
| `StreamFailoverEvent` | broker, stream, reason, fallback |

### 2.3 Failure Taxonomy

7 failure modes documented in `FAILURE_TAXONOMY`:
*(Specific modes pending full audit of audit.py)*

---

## 3. Fault Tolerance

### 3.1 Retry Patterns

| Component | Mechanism | Backoff | Jitter | Max Retries | Retryable Errors |
|-----------|-----------|---------|--------|-------------|-----------------|
| `RetryExecutor` | Generic configurable | Exponential | Yes | Configurable | Configurable exception list |
| `HistoricalDownloadEngine` | Chunk-level retry | Exponential | Unknown | Configurable | Network errors |
| HTTP client | `HTTPAdapter(max_retries=3)` | Default urllib3 | No | 3 | Connection errors |
| WebSocket reconnect | Auto-reconnect | Backoff | Unknown | Unknown | Connection loss |
| Auth token refresh | `should_generate_token()` | Unknown | N/A | Unknown | Token rejection |

### 3.2 Circuit Breaker

| Property | Value |
|----------|-------|
| States | CLOSED → OPEN → HALF_OPEN |
| Failure threshold | Configurable (domain/constants/resilience.py) |
| Reset timeout | Configurable |
| Scope | Per-broker or per-endpoint (NEEDS VERIFICATION) |

### 3.3 Rate Limiting

| Component | Mechanism | Detail |
|-----------|-----------|--------|
| `TokenBucketRateLimiter` | Token bucket | Multi-bucket support |
| `QuotaScheduler` | Priority-based quota | 5 levels: EXECUTION_CRITICAL → ENRICHMENT |
| Reserved headroom | YES | Execution operations get reserved quota |
| Blocking + async acquire | YES | Both sync and async acquisition |

### 3.4 Resilience Patterns Summary

| Pattern | Present | Quality |
|---------|---------|---------|
| Retry with backoff | YES | GOOD — configurable, jittered |
| Circuit breaker | YES | GOOD — 3-state machine |
| Rate limiting | YES | EXCELLENT — priority-based with headroom |
| Timeout | YES | Configurable per-operation |
| Graceful degradation | YES | Historical coordinator degraded mode |
| Fail-fast | PARTIAL | Circuit breaker provides this |
| Bulkhead | PARTIAL | Connection pool provides some isolation |
| Fallback | YES | Router supports fallback brokers |

---

## 4. Logging

### 4.1 Structured Logging

| Feature | Implementation |
|---------|---------------|
| JSON structured formatter | `StructuredFormatter` in `logging_config.py` |
| Human-readable formatter | `HumanReadableFormatter` (colored) |
| Log levels | Standard Python logging levels |
| Configuration | `configure_logging()` function |

### 4.2 Sensitive Data Masking

**Defence-in-depth approach with 9 regex patterns:**

| Pattern | Target |
|---------|--------|
| `TokenRedactionFilter` | Access tokens, API keys |
| Pattern 1-9 | Various token formats (bearer, JWT, API key, etc.) |

**Assessment:** EXCELLENT — 9 patterns is thorough. Defence-in-depth is the right approach for secrets.

### 4.3 Correlation IDs

| Feature | Implementation |
|---------|---------------|
| Thread-safe propagation | `ContextVar` (async-safe) |
| Auto-generation | `resolve_correlation_id()` |
| Log inclusion | `CorrelationFilter` adds to every log record |
| Cross-service | Via audit events with trace_id |

### 4.4 Audit Logging

| Log | Format | Rotation | Idempotency |
|-----|--------|----------|-------------|
| `BufferedEventLog` | JSONL append-only | Day rotation | `_seen_ids` set |
| `ProvenanceLedger` | Chunk records | Unknown | Conflict detection |
| `EventLog` (deprecated) | JSONL | Day rotation | Yes |

---

## 5. Configuration

### 5.1 Environment Isolation

| Environment | Mechanism | Detail |
|-------------|-----------|--------|
| Dhan | `.env.local` | CLIENT_ID, ACCESS_TOKEN, PIN/TOTP |
| Upstox | `.env.upstox` | CLIENT_ID, tokens, TOTP mode |
| Paper | None | No credentials needed |
| Platform | `os.environ` | TRADEX_BROKER_POLICY, TRADEX_EXECUTION_BROKER |

### 5.2 Configuration Hierarchy

```
1. Environment variables (highest priority)
2. .env files (per-broker)
3. BrokerSettings defaults (frozen dataclass)
4. Domain constants (lowest priority)
```

### 5.3 Secrets Management

| Aspect | Current | Assessment |
|--------|---------|-----------|
| Token storage | .env files + JSON token state | ACCEPTABLE for dev |
| Token persistence | Atomic file write (fcntl) | GOOD |
| Vault integration | NONE | GAP — no HashiCorp Vault, AWS Secrets Manager |
| Secret rotation | Manual | GAP — no automated rotation |
| Token expiry detection | JWT exp claim parsing | GOOD |
| Proactive refresh | `should_generate_token()` | GOOD — refreshes before expiry |

### 5.4 Validation

| Component | Validation | Detail |
|-----------|-----------|--------|
| `CredentialValidator` | Broker-specific | Checks required fields per broker |
| `BrokerSettings` | Env var parsing | Type conversion, defaults |
| Config schema | `config/schema.py` | Schema validation |
| Config profiles | `config/profiles/` | Named profiles |

---

## 6. Security

### 6.1 Credential Storage

| Credential | Storage | Protection |
|-----------|---------|-----------|
| Access tokens | .env files + JSON store | File-level (OS permissions) |
| TOTP secrets | Environment | In-memory only |
| Client IDs | .env files | File-level |
| PIN | Environment | In-memory only |

### 6.2 Token Security

| Aspect | Implementation | Assessment |
|--------|---------------|-----------|
| Token in memory | `TokenState` dataclass | GOOD — not persisted unnecessarily |
| Token in transit | HTTPS only (TLS 1.2+) | EXCELLENT — ssl_hardening.py |
| Token in logs | 9-pattern redaction | EXCELLENT |
| Token in env files | Atomic write with fcntl | GOOD — prevents corruption |
| JWT verification | NOT verified (exp claim only) | ACCEPTABLE — we're the token holder |

### 6.3 TLS/SSL

| Feature | Implementation |
|---------|---------------|
| TLS version | 1.2+ only |
| Cipher suites | Mozilla Intermediate profile |
| Hostname verification | Enabled |
| Compression | Disabled |
| Certificate pinning | Not implemented |
| Session hardening | `HardenedHTTPSAdapter`, `create_pinned_session()` |

### 6.4 Input Validation

| Boundary | Validation | Detail |
|----------|-----------|--------|
| Symbol names | `normalize_symbol()`, path traversal rejection | GOOD |
| Order payload | `order_validation.py` — notional warning (₹50,000) | PARTIAL |
| Exchange segment | `parse_segment()`, `canonical_exchange_short()` | GOOD |
| Enum values | `canonicalize_order_enums()` | GOOD |

### 6.5 Security Gaps

| Gap | Severity | Recommendation |
|-----|----------|---------------|
| No vault integration | HIGH | Add HashiCorp Vault / AWS Secrets Manager |
| No certificate pinning | MEDIUM | Consider for production |
| .env files on disk | MEDIUM | File permissions, consider encrypted storage |
| No rate limiting on auth endpoint specifically | MEDIUM | TOTP cooldown helps but isn't per-IP |
| JWT exp parsed without verification | LOW | Acceptable since we're the token holder |

---

## 7. Observability

### 7.1 Metrics

| Metric Type | Implementation | Export |
|-------------|---------------|--------|
| Counter | `MetricsRegistry` | Prometheus text exposition |
| Gauge | `MetricsRegistry` | Prometheus text exposition |
| Histogram | `MetricsRegistry` | Prometheus text exposition |
| Timer | `MetricsRegistry` | Prometheus text exposition |
| Labelled variants | All of the above | Prometheus labels |

### 7.2 Health Checks

| Endpoint | Purpose | Implementation |
|----------|---------|---------------|
| `/healthz` | Liveness | `HttpObservabilityServer` |
| `/readyz` | Readiness | `authenticated_readiness_probe()` — real API call |
| `/metrics` | Prometheus | Full metrics export |

### 7.3 Alerting

| Rule | Condition | Level |
|------|-----------|-------|
| 6 default production rules | Glob-pattern metric rules | Configurable |
| `AlertingEngine` | Periodic evaluation | Threshold + rate-based |

### 7.4 Tracing

| Feature | Implementation |
|---------|---------------|
| OpenTelemetry | `tracing.py` — optional integration |
| Fallback | Log-only when OTel not available |
| `trace_operation()` | Context manager for operation tracing |
| `trace_event_handler()` | Event handler tracing |

### 7.5 Observability Gaps

| Gap | Severity |
|-----|----------|
| No distributed tracing across broker calls | MEDIUM |
| No SLO/SLI definitions | MEDIUM |
| No error budget tracking | LOW |
| Metrics are in-memory only (no persistent TSDB) | LOW — Prometheus scrape handles this |

---

## 8. Performance

### 8.1 Startup Time

| Phase | Estimated Cost | Bottleneck |
|-------|---------------|-----------|
| Environment bootstrap | LOW | .env file loading |
| Credential validation | LOW | In-memory checks |
| Token acquisition | HIGH (if login needed) | Network round-trip + TOTP |
| Connection pool init | LOW | Socket creation |
| Instrument download | HIGH (if stale) | Network + file I/O |
| Lifecycle start | MEDIUM | Background service startup |
| WebSocket connect | MEDIUM | Network + auth |
| Production readiness | MEDIUM | 13+ pre-flight checks |

### 8.2 Memory Usage

| Component | Memory Profile | Concern |
|-----------|---------------|---------|
| Instrument registry | HIGH — full instrument master in memory | Could be large (100K+ instruments) |
| `CanonicalInstrumentRegistry` | HIGH — cross-broker instrument map | Mitigated by lazy loading? NEEDS VERIFICATION |
| `ProcessedTradeRepository` | MEDIUM — in-memory set + JSONL | TTL cleanup daemon helps |
| `DeadLetterQueue` | LOW — bounded FIFO | Good — bounded |
| `MetricsRegistry` | LOW — counters/gauges | Minimal |
| Frozen dataclasses | LOW — immutable, shareable | Good — no defensive copies needed |

### 8.3 Concurrency Performance

| Pattern | Performance Impact |
|---------|-------------------|
| `RLock` in MetricsRegistry | LOW contention — metrics are append-only |
| `ThreadPoolExecutor` for batch | GOOD — parallel I/O |
| `asyncio.to_thread()` for sync bridge | GOOD — doesn't block event loop |
| Double-checked locking singleton | LOW overhead — one-time cost |
| `ContextVar` for correlation | ZERO overhead — native async support |

### 8.4 Bottlenecks

| Bottleneck | Severity | Mitigation |
|-----------|----------|-----------|
| Instrument master download | HIGH on first start | Parquet cache, stale detection |
| Single HTTP connection pool | MEDIUM | Pool of 50 connections, max 100 |
| Sync→async bridge | LOW | `to_thread()` is efficient |
| JSON parsing for large responses | LOW | Standard library, adequate |

---

## 9. Cross-Cutting Summary

| Concern | Score | Key Strength | Key Gap |
|---------|-------|-------------|---------|
| Exception Hierarchy | **A-** | Comprehensive, retryable/non-retryable split | Missing domain-specific exceptions |
| Error Reporting | **B+** | Correlation IDs, structured audit events | Root-cause chaining needs verification |
| Fault Tolerance | **A-** | Retry + CB + rate limit + fallback + degraded mode | Some retry configs not verified |
| Logging | **A** | 9-pattern token redaction, JSON + human formatters | None significant |
| Configuration | **B** | Per-broker .env, validation, profiles | No vault integration |
| Security | **B+** | TLS hardening, token redaction, atomic writes | No vault, no cert pinning |
| Observability | **A-** | Prometheus, health checks, alerting, tracing | No SLO/SLI definitions |
| Performance | **B** | Good concurrency, bounded queues | Instrument master memory, startup time |
