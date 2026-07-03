# Phase 8 — Failure Analysis: Cross-Cutting Concerns

> **Greenfield Broker Replication Protocol — Dhan Adapter**
> Phase 8 failure analysis covers timeout policies, exception hierarchies,
> race conditions, recovery paths, secret exposure risks, configuration
> validation failures, and greenfield gaps for all cross-cutting modules.

---

## Table of Contents

1. [Timeout Policies](#1-timeout-policies)
2. [Exception Hierarchy Analysis](#2-exception-hierarchy-analysis)
3. [Race Conditions Inventory](#3-race-conditions-inventory)
4. [Recovery Paths](#4-recovery-paths)
5. [Secret Exposure Risks](#5-secret-exposure-risks)
6. [Configuration Validation Failures](#6-configuration-validation-failures)
7. [Greenfield Gaps](#7-greenfield-gaps)

---

## 1. Timeout Policies

### 1.1 Gateway Timeouts

| Component | Archive Timeout | Greenfield Timeout | Notes |
|-----------|----------------|-------------------|-------|
| HTTP client (default) | `settings.http_timeout` (default 15s) | `DhanHttpClient` timeout param | Configurable via `DHAN_HTTP_TIMEOUT` |
| TOTP generation POST | 15s (hardcoded in `_generate_totp_token`) | 15s (hardcoded in `DhanAuth.generate_token`) | Both hardcoded |
| Instrument CSV download | Not specified (uses HTTP default) | 30s (hardcoded in resolver) | Greenfield explicit |
| WebSocket connect | Not specified | Not specified | SDK-managed |
| `close()` | No timeout | No timeout | Could hang on blocked WS |

### 1.2 Factory Timeouts

| Step | Timeout | Failure Mode |
|------|---------|--------------|
| `DhanSettingsLoader.from_env()` | None (instant) | `ValueError` on missing `DHAN_CLIENT_ID` |
| `_create_auth()` → TOTP generation | 15s HTTP + 5s refresh_lock | `ConfigurationError` if no token |
| `_create_http_client()` | None (instant) | — |
| `_create_connection_and_gateway()` | None (instant) | — |
| `_wire_websocket_services()` | None (instant) | — |
| `_setup_token_refresh_scheduler()` | None (instant) | Scheduler start may fail silently |
| `load_instruments()` | CSV download (no explicit timeout) | Propagates loader exception |

### 1.3 Identity Timeouts

| Operation | Timeout | Failure Mode |
|-----------|---------|--------------|
| `resolve_ref()` | None (in-memory lookup) | `InstrumentNotFoundError` |
| `resolve_ref_from_security_id()` | None (in-memory lookup) | Returns `None` |
| Instrument CSV load | Network-dependent | Propagates download error |

### 1.4 Token Refresh Timeouts

| Component | Timeout | Notes |
|-----------|---------|-------|
| `refresh_lock.acquire()` | 5.0 seconds | Archive: `_refresh_via_auth()`. Greenfield: same pattern. |
| TOTP HTTP POST | 15 seconds | Hardcoded in both archive and greenfield |
| Scheduler interval | `settings.scheduler_interval_seconds` (default varies) | Configurable |
| Refresh buffer | `settings.refresh_buffer_seconds` (default 300) | Refresh if token expires within window |
| Cooldown guard | `TotpCooldownGuard.for_broker("dhan")` | Archive only; prevents rapid retries |

---

## 2. Exception Hierarchy Analysis

### 2.1 Archive Exception Map

| Exception | Base Classes | Raised By | Caught By | HTTP Mapping |
|-----------|-------------|-----------|-----------|--------------|
| `DhanError` | `BrokerError` | All Dhan adapters | Global handler | 500 |
| `InstrumentNotFoundError` | `DhanError` + `_CommonInstrumentNotFoundError` | Resolver, identity | Global handler | 404 |
| `MarketDataError` | `DhanError` | Market data adapter | Caller | 500 |
| `OrderError` | `DhanError` + `_CommonOrderError` | Orders adapter | Global handler | 400 |
| `AuthenticationError` | `DhanError` + `_CommonAuthenticationError` | Auth, HTTP 401 | HTTP retry | 401 |
| `ConfigurationError` | `DhanError` | Factory, settings | Bootstrap | 500 |
| `DhanIdentityError` | `DhanError` | Identity provider | Caller | 400 |
| `SuperOrderError` | `DhanError` | Super orders adapter | Caller | 400 |
| `ForeverOrderError` | `DhanError` | Forever orders adapter | Caller | 400 |
| `ConditionalTriggerError` | `DhanError` | Conditional triggers | Caller | 400 |
| `LedgerError` | `DhanError` | Ledger adapter | Caller | 500 |
| `UserProfileError` | `DhanError` | User profile adapter | Caller | 500 |
| `IPManagementError` | `DhanError` | IP management adapter | Caller | 400 |
| `ExitAllError` | `DhanError` + `_CommonExitAllError` | Exit all adapter | Global handler | 501 |
| `EDISError` | `DhanError` | EDIS adapter | Caller | 400 |
| `RateLimitError` | Re-exported from common | HTTP 429 handler | Retry framework | 429 |

**Design principle:** Multiple inheritance ensures `isinstance(exc, _CommonXxxError)` matches in the global exception handler while `isinstance(exc, DhanError)` matches in broker-specific code.

### 2.2 Greenfield Exception Map

| Exception | Base Class | Raised By | Gap vs Archive |
|-----------|-----------|-----------|----------------|
| `DhanError` | `BrokerError` | All adapters | Same root |
| `DhanAuthenticationError` | `AuthenticationError` | `DhanAuth` | Covers auth only |
| `DhanRateLimitError` | `RateLimitError` | HTTP 429 | Covers rate limit |
| `DhanOrderRejectedError` | `OrderRejectedError` | Orders adapter | Covers order rejection |
| `DhanConnectionError` | `NetworkError` | HTTP client | Covers transport |
| `DhanServerError` | `BrokerServerError` | HTTP 5xx | Covers server errors |

**Missing from greenfield (10 types):**
`InstrumentNotFoundError`, `ConfigurationError`, `DhanIdentityError`,
`MarketDataError`, `SuperOrderError`, `ForeverOrderError`,
`ConditionalTriggerError`, `LedgerError`, `UserProfileError`,
`IPManagementError`, `ExitAllError`, `EDISError`.

### 2.3 Domain Exception Hierarchy (Shared)

```
TradeXV2Error
├── ConfigError
├── DataError
├── ValidationError
└── BrokerError
    ├── RetryableError
    │   └── NetworkError
    ├── NonRetryableError
    ├── BrokerServerError
    ├── OrderRejectedError (has order_id)
    ├── RateLimitError (has retry_after)
    ├── CircuitOpenError
    ├── AuthenticationError
    ├── TokenRateLimitError
    ├── InstrumentNotFoundError (has symbol)
    ├── NotSupportedError
    └── BrokerDegradedError (has health_status)
```

---

## 3. Race Conditions Inventory

### 3.1 Concurrent Bootstrap (HIGH)

**Scenario:** Two threads call `BrokerFactory.create()` simultaneously for the same `(broker_id, account_id)`.

**Archive mitigation:** `AccountConnectionRegistry.get_or_create()` uses a class-level `threading.Lock()`. The second thread blocks until the first completes, then finds the cached gateway.

**Greenfield gap:** No registry. If two threads construct `DhanGateway` independently, both succeed, creating duplicate HTTP pools, WS connections, and schedulers. This wastes resources and may trigger Dhan's connection limits.

**Risk:** MEDIUM — duplicate token generation attempts may trigger Dhan's 2-minute rate limit.

### 3.2 Identity Refresh Race (HIGH)

**Scenario:** HTTP 401 handler and background scheduler both attempt token refresh simultaneously.

**Archive mitigation:** `refresh_lock` (threading.Lock) shared between `_refresh_via_auth()` and `TokenRefreshScheduler`. Lock has 5-second timeout. The scheduler holds the lock during refresh; the HTTP handler waits up to 5s.

**Greenfield mitigation:** Same pattern — `self._refresh_lock = threading.Lock()` shared between `_refresh_token_for_http()` and `TokenRefreshScheduler`.

**Residual risk:** If the lock holder crashes mid-refresh, the waiter gets `None` after 5s and proceeds without a token. The next HTTP call will also 401, triggering another refresh attempt.

### 3.3 Config Reload Race (LOW)

**Scenario:** Environment variables change while the factory is reading them.

**Archive:** `DhanConfigLoader.load()` reads env vars in a single pass. No locking. If `os.environ` changes mid-read, some values may come from the old state and some from the new.

**Greenfield:** Static constants — not subject to runtime changes.

**Risk:** LOW — configuration is loaded once at bootstrap.

### 3.4 Token Broadcast Ordering (MEDIUM)

**Scenario:** Token refresh fires broadcast while a streaming WS reconnect is in progress.

**Archive:** No broadcast mechanism. Token update is pushed directly via `gateway._conn.broadcast_token()`.

**Greenfield:** `TokenBroadcast.broadcast()` iterates receivers sequentially. Each receiver's `update_token()` is called synchronously. If a receiver raises, the exception is caught and logged (per-receiver isolation). Dead weak references are pruned.

**Risk:** If `_streaming.update_token()` succeeds but `_depth200_stream.update_token()` fails, the depth-200 stream continues with the old token. On next reconnect, it will use the stale token and likely 401.

### 3.5 .env File Atomic Write (LOW)

**Scenario:** Two processes attempt to update `.env.local` simultaneously.

**Archive mitigation:** `_update_env_token()` uses `fcntl.flock(LOCK_EX)` for cross-process exclusion + temp-file + `os.replace()` for atomicity. Directory fsync ensures durability.

**Greenfield mitigation:** Uses `update_env_token()` from `brokers.infrastructure.token_persistence` — same atomic pattern.

**Residual risk:** `fcntl` is Unix-only. On Windows, the fallback logs a warning and proceeds unprotected.

### 3.6 Account Registry Release During Use (MEDIUM)

**Scenario:** Thread A calls `AccountConnectionRegistry.release()` while Thread B is using the gateway.

**Archive:** `release()` pops the gateway from the dict and calls `close()`. Thread B's next API call will hit a closed connection.

**Mitigation:** None in archive. The caller must ensure release happens only after all users are done.

**Greenfield:** No registry, so this specific race doesn't apply. But the same issue exists if the caller calls `gateway.close()` while other threads are using it.

---

## 4. Recovery Paths

### 4.1 Bootstrap Failure Recovery

| Failure Point | Archive Recovery | Greenfield Recovery |
|---------------|-----------------|---------------------|
| Missing `DHAN_CLIENT_ID` | `ValueError` at `from_env()`. No recovery — fix env. | Same — `client_id` required. |
| TOTP generation fails | `ConfigurationError`. Fallback: provide `DHAN_ACCESS_TOKEN` directly. | `AuthenticationError`. Same fallback. |
| TOTP rate-limited | `RuntimeError("once every 2 minutes")`. Wait 130s and retry. | `TokenRateLimitError`. Wait and retry. |
| Instrument CSV download fails | Propagates exception. Fallback: stale cache (6h TTL). | Propagates exception. **No cache fallback.** |
| WS wiring fails | Logged as warning. Gateway still functional without streaming. | Same — scheduler start failure logged. |
| `AccountConnectionRegistry` cache hit | Returns existing gateway. No recovery needed. | N/A — no registry. |

### 4.2 Identity Failure Recovery

| Failure | Archive Recovery | Greenfield Recovery |
|---------|-----------------|---------------------|
| Symbol not found | `InstrumentNotFoundError`. Caller must normalise symbol. | Same. |
| Non-Dhan segment | `DhanIdentityError` at construction. Bug — fix code. | Same structural validation. |
| Expected segment mismatch | `InstrumentNotFoundError` or `DhanIdentityError`. Caller must specify correct contract. | No `expected_segment` check. May silently resolve to wrong instrument. |
| CSV not loaded | All resolutions fail. Call `load_instruments()` first. | Same — resolver must be loaded. |

### 4.3 Configuration Failure Recovery

| Failure | Archive Recovery | Greenfield Recovery |
|---------|-----------------|---------------------|
| Invalid env var value | `_parse_env_value` returns default on parse failure | N/A — static constants |
| Missing .env file | Silently skipped; uses defaults + env vars | N/A |
| Malformed JSON config | `json.JSONDecodeError` propagated | N/A |
| Unknown env var key | Ignored (not in `ENV_KEY_MAPPING`) | N/A |

### 4.4 Token Refresh Failure Recovery

| Failure | Archive Recovery | Greenfield Recovery |
|---------|-----------------|---------------------|
| TOTP rate limit | `TotpRateLimitError` caught by scheduler. Backoff 130s. | `TokenRateLimitError` caught in `refresh_token()`. Logged, returns old token. |
| Network failure during refresh | Returns `None`. Old token remains valid until expiry. | `AuthenticationError` caught. Returns old token. |
| Lock timeout (5s) | Returns `None`. HTTP call proceeds with old token, may 401 again. | Same pattern. |
| All refresh attempts exhausted | Gateway continues with expired token. All API calls will 401. | Same — no circuit breaker on auth failures. |

---

## 5. Secret Exposure Risks

### 5.1 Comprehensive Audit

| Secret | Storage | Exposure Vector | Severity | Mitigation |
|--------|---------|-----------------|----------|------------|
| `DHAN_CLIENT_ID` | Env var / .env | Logs, error messages | LOW | Not a secret per se |
| `DHAN_ACCESS_TOKEN` | Env var / .env / JSON store | Logs, error messages, process env | HIGH | Archive: atomic .env update. Both: never logged directly. |
| `DHAN_PIN` | Env var / file | Process env, core dumps | HIGH | `read_secret()` supports file-based secrets |
| `DHAN_TOTP_SECRET` | Env var / file | Process env, core dumps | CRITICAL | File-based secret preferred |
| TOTP code (runtime) | In-memory during generation | HTTP URL params (GET request) | HIGH | Archive uses POST with query params in URL — **visible in server logs** |

### 5.2 TOTP URL Parameter Risk (HIGH)

**Archive:** `_generate_totp_token()` constructs the URL as:
```python
params = {"dhanClientId": client_id, "pin": pin, "totp": totp_code}
url = f"{token_url}?{urlencode(params)}"
resp = _requests.post(url, timeout=15)
```

The PIN and TOTP code are sent as **URL query parameters on a POST request**. While the body is empty, the URL is visible in:
- Server access logs (Dhan's side)
- Proxy logs (if any)
- Python's `requests` debug logging
- Exception tracebacks (URL may be included)

**Greenfield:** Same pattern — `DhanAuth.generate_token()` uses identical URL construction.

**Recommendation:** Move PIN and TOTP to POST body. This is a Dhan API constraint that cannot be changed by the adapter.

### 5.3 Token Persistence Risks

| Vector | Archive | Greenfield |
|--------|---------|------------|
| .env file permissions | `os.open(..., 0o600)` — owner-only | Same atomic pattern |
| JSON token store | Written to `runtime/` directory | Same directory pattern |
| Process environment | `os.environ["DHAN_ACCESS_TOKEN"]` | Same |
| Log leakage | Token value never explicitly logged | `logger.info("dhan_token_generated")` — no token value |
| Exception messages | `ConfigurationError("DHAN_ACCESS_TOKEN not configured...")` | `AuthenticationError("pin and totp_secret are required...")` |

### 5.4 IPv4 Preference Side Effect (MEDIUM)

**Greenfield:** `auth.py` patches `socket.getaddrinfo` globally at import time:
```python
def _prefer_ipv4():
    if not hasattr(socket, "_dhan_ipv4_patched"):
        socket.getaddrinfo = getaddrinfo_ipv4
        socket._dhan_ipv4_patched = True
```

This affects **all** network connections in the process, not just Dhan. If another broker or service requires IPv6, this patch will break it.

**Archive:** No equivalent global patch.

### 5.5 `__all__` Export Audit

| Module | Exports Secrets? | Notes |
|--------|-----------------|-------|
| `archive/brokers/dhan/__init__.py` | Re-exports public API | No secrets |
| `archive/brokers/dhan/secret_utils.py` | `read_secret` function | Function itself is safe; callers must handle return value |
| `archive/brokers/dhan/token_manager.py` | `generate_totp_token`, `read_secret` | Token generation helpers |

---

## 6. Configuration Validation Failures

### 6.1 Archive Validation Matrix

| Setting | Validation | Failure Mode | Default |
|---------|-----------|--------------|---------|
| `DHAN_CLIENT_ID` | `if not client_id: raise ValueError` | Bootstrap abort | None (required) |
| `DHAN_ENVIRONMENT` | `if environment not in VALID_ENVIRONMENTS: raise ValueError` | Bootstrap abort | `"LIVE"` |
| `DHAN_HTTP_TIMEOUT` | `_get_float()` — silent fallback | Uses default on parse error | `15.0` |
| `DHAN_ENABLE_RETRY` | `_get_bool()` — silent fallback | Uses default on parse error | `True` |
| `DHAN_POOL_CONNECTIONS` | `_get_int()` — silent fallback | Uses default on parse error | `50` |
| `DHAN_RESILIENCE_*` | `_parse_env_value()` — type-specific parsing | Returns default/empty on failure | Varies |
| Rate limit limits dict | `json.loads()` with fallback to `{}` | Empty dict on malformed JSON | `DEFAULT_RATE_LIMITS` |
| Circuit breaker thresholds | `int(value)` — raises on non-integer | Propagates `ValueError` | `3` / `5` |
| ISIN format (EDIS) | Regex `^[A-Z]{2}[A-Z0-9]{9}[A-Z0-9]{1}$` | `ValueError` | — |
| IP address format | IPv4 dotted-quad regex | `ValueError` | — |
| Date format (ledger) | Regex `^\d{4}-\d{2}-\d{2}$` | `ValueError` | — |
| Alert trigger price | `trigger_price > 0` | `ValueError` via `_validate_request` | — |
| Alert condition | `∈ {LTP_CROSSES_ABOVE, LTP_CROSSES_BELOW}` | `ValueError` via `_validate_request` | — |
| `DhanInstrumentRef.exchange_segment` | `is_dhan_segment()` in `__post_init__` | `DhanIdentityError` | — |
| `DhanInstrumentRef.security_id` | `isdigit() and int > 0` in `__post_init__` | `DhanIdentityError` | — |

### 6.2 Greenfield Validation Matrix

| Setting | Validation | Gap vs Archive |
|---------|-----------|----------------|
| `client_id` | Implicit — empty string allowed | **Gap:** No `ValueError` on empty |
| `pin` / `totp_secret` | Checked in `generate_token()` — raises `AuthenticationError` | Deferred to first use |
| No resilience config | Static constants | **Gap:** No validation needed (compile-time) |
| No ISIN validation | Not implemented | **Gap:** EDIS adapter doesn't validate ISIN |
| No IP validation | Not implemented | **Gap:** IP management doesn't validate format |
| No date validation | Not implemented | **Gap:** Ledger doesn't validate date format |
| No alert validation | Not implemented | **Gap:** No trigger_price > 0 check |

---

## 7. Greenfield Gaps

### 7.1 Critical Gaps (P0)

| Gap | Archive Feature | Risk | Remediation Effort |
|-----|----------------|------|---------------------|
| No runtime configuration | `DhanConfigLoader` + `DhanResilienceConfig` with env var overrides | Cannot tune rate limits, retries, circuit breakers without code change | Medium — port config system |
| No instrument cache | `InstrumentLoader` with 6h TTL + stale-cache fallback | Every restart downloads full CSV; no fallback if Dhan CDN is down | Medium — add cache layer |
| Missing exception types | 14 archive exceptions vs 5 greenfield | Global exception handler cannot map broker-specific errors correctly | Low — add exception classes |
| No order reconciliation | `DhanReconciliationService` with order + position comparison | Cannot detect OMS drift | Medium — port reconciliation engine |

### 7.2 High-Priority Gaps (P1)

| Gap | Archive Feature | Risk | Remediation Effort |
|-----|----------------|------|---------------------|
| No symbol validation | Regex-based F&O parsing (4 patterns) + expired contract detection | Cannot validate user input before sending to broker | Low — port validator |
| No alert validation | trigger_price > 0, condition enum check | Invalid alerts sent to broker, wasting API calls | Low — add validation |
| No input validation (EDIS, IP, Ledger) | ISIN, IPv4, date format checks | Invalid requests sent to broker | Low — add validators |
| No account registry | `AccountConnectionRegistry` singleton | Duplicate gateways waste resources | Low — add registry or document singleton pattern |
| No session state machine | `DhanSessionManager` with AUTH_REQUIRED/DISCONNECTED/DEGRADED/HEALTHY | Cannot determine trading readiness | Medium — port session manager |

### 7.3 Medium-Priority Gaps (P2)

| Gap | Archive Feature | Risk | Remediation Effort |
|-----|----------------|------|---------------------|
| No capabilities detail | Rate limit profiles, historical windows, stream limits | Cannot programmatically query broker limits | Low — port capabilities |
| No segment SDK mapping | `to_sdk_int()`, `from_sdk_int()`, `DhanSegmentMapper` | Cannot interface with Dhan SDK | Low — if SDK needed |
| No identity audit trail | `DhanIdentitySource` enum + structured logging | Cannot trace security_id origin | Low — add source tracking |
| No `expected_segment` constraint | Index vs derivative disambiguation | May silently resolve to wrong instrument | Low — add constraint |
| IPv4 global side effect | `socket.getaddrinfo` patched at import time | Affects all network connections in process | Low — scope to Dhan-only |

### 7.4 Summary Risk Matrix

| Category | Archive Coverage | Greenfield Coverage | Gap Risk |
|----------|-----------------|--------------------|---------|
| Configuration | Full runtime config | Static constants | HIGH |
| Exception handling | 14 typed exceptions | 5 typed exceptions | HIGH |
| Instrument caching | 6h TTL + stale fallback | No cache | HIGH |
| Reconciliation | Order + position + auto-repair | Position only | HIGH |
| Symbol validation | 4 regex patterns + expiry detection | Resolve-only | HIGH |
| Input validation | ISIN, IP, date, alert checks | None | MEDIUM |
| Session management | 4-state lifecycle | Health dict only | MEDIUM |
| Identity audit | Source tracking + structured logs | No tracking | MEDIUM |
| Secret management | Env + file + atomic .env | Env + file + atomic .env | LOW |
| Metrics | 9 Prometheus metrics | 3 metrics + decorators | LOW |
| Token lifecycle | Full TOTP + scheduler + broadcast | Full TOTP + scheduler + broadcast | LOW |
