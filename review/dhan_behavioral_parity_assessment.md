# Elite Quantitative Engineering Review Board – Dhan Behavioral Parity Assessment

**Scope:** Dhan broker implementation comparison between archived (`archive/brokers/dhan/`) and greenfield (`brokers/adapters/dhan/`) codebases.

**Assessment Type:** Production-readiness audit focused on behavioral contracts, NOT file comparisons or code style.

---

## Review Status Legend

| Status | Meaning |
|--------|---------|
| ✅ VERIFIED | Greenfield replicates archive behavior 1:1 with no material difference |
| ⚠️ PARTIAL | Greenfield covers core behavior but omits edge cases, validation, or auxiliary features |
| ❌ DIVERGENT | Greenfield implements a materially different approach |
| ❎ NOT_PORTED | Archive behavior has no greenfield counterpart |
| 🔧 IMPROVED | Greenfield intentionally improves on the archive |

---

## 1. Gateway Lifecycle & Composition

| Behavior | Archive Evidence | Greenfield Evidence | Status | Notes |
|----------|------------------|-------------------|--------|-------|
| Gateway construction pattern | `BrokerGateway(connection)` receives `DhanConnection` built by factory; external composition | `DhanGateway.__init__()` builds all adapters internally | ❌ DIVERGENT | Archive: factory creates connection, gateway wraps it. Greenfield: gateway is the factory. This is an architectural divergence affecting testability and lifecycle management. |
| `close()` stops all subsystems | `self._conn.close()` delegates to connection lifecycle helper | Stops scheduler, streaming, order_stream, depth20_stream, depth200_stream explicitly | 🔧 IMPROVED | Greenfield explicitly stops each stream; archive delegates through connection. Both achieve same outcome. |
| Health/status reporting | `describe()` returns static dict; `get_connection_status()` via `ObservabilityProvider` protocol | `health()` returns auth validity, scheduler health, broadcast metrics | ⚠️ PARTIAL | Greenfield omits per-feed connection status (`market_feed`, `order_stream`), circuit breaker states, token refresh metrics via protocol. Archive has full `ObservabilityProvider` implementation. |
| Stream handle lifecycle | `_DhanStreamHandle` with `disconnect()`, `is_connected()`, session tracking | Not implemented | ❎ NOT_PORTED | Greenfield has no stream handle abstraction. Archive provides `BrokerStreamHandle` compatible with async infrastructure. |

**Critical Finding:** The gateway composition pattern is fundamentally different. Archive uses factory-based external composition enabling singleton registry patterns; greenfield uses internal composition which cannot easily support process-wide connection pooling.

---

## 2. Authentication & Token Lifecycle

| Behavior | Archive Evidence | Greenfield Evidence | Status | Notes |
|----------|------------------|-------------------|--------|-------|
| TOTP token generation | `DhanTotpClient` with `TotpCooldownGuard` for rate-limit protection | `DhanAuth.generate_token()` inline | ❌ DIVERGENT | Archive has separate `DhanTotpClient` class with cooldown guard to prevent "once every 2 minutes" errors. Greenfield inlines TOTP without cooldown guard. |
| Token state tracking | `AuthManager` + `TokenState` + `JsonTokenStateStore` | `DhanAuth` with `TokenState` + `JsonTokenStateStore` | ✅ VERIFIED | Both use same `TokenState` model and JSON persistence. |
| Token broadcast to consumers | `ConnectionTokenManager` with weak refs, idempotent registration, dead-ref cleanup | `TokenBroadcast` with weak refs, idempotent registration, dead-ref cleanup | ✅ VERIFIED | Both use weak references with identical semantics. |
| Refresh lock sharing | `threading.Lock` created in factory, shared across HTTP client and scheduler | `self._refresh_lock` in gateway, shared across HTTP client and scheduler | ✅ VERIFIED | Same pattern for preventing concurrent refresh race conditions. |
| Env file atomic token update | `_update_env_token()` with `fcntl.flock`, temp file, `os.replace` | `update_env_token()` from shared infrastructure module | ✅ VERIFIED | Moved to shared module but behavior preserved. |
| IPv4 preference patch | Not in archive | `_prefer_ipv4()` patches `socket.getaddrinfo` at module load | 🔧 IMPROVED | Greenfield adds IPv4 workaround for auth.dhan.co IPv6 connectivity issues. This is an improvement. |
| Token regeneration timing | Only after expiry detection | Only after expiry detection | ✅ VERIFIED | Both regenerate tokens only when expired. |
| Refresh storm prevention | Via `TotpCooldownGuard` | No explicit storm prevention | ⚠️ PARTIAL | Archive's cooldown guard is missing in greenfield. Under high load, greenfield could trigger rate limits. |
| Concurrent refresh protection | Lock with 5-second timeout wait | Lock (behavior unspecified timeout) | ⚠️ PARTIAL | Archive explicitly waits for in-flight refresh; greenfield lock behavior needs verification. |

**Critical Finding:** The TOTP cooldown guard is missing in greenfield. This can cause "Token can be generated once every 2 minutes" errors under concurrent refresh scenarios.

---

## 3. Identity & Instrument Resolution

| Behavior | Archive Evidence | Greenfield Evidence | Status | Notes |
|----------|------------------|-------------------|--------|-------|
| DhanInstrumentRef validation | Validates segment ∈ DHAN_SEGMENTS, security_id is digit string, > 0 | Same validation in `__post_init__` | ✅ VERIFIED | Core invariants preserved. |
| Symbol resolution | `SymbolResolver.resolve()` with progressive lookup, index fallback | `DhanInstrumentResolver.resolve()` with simpler lookup | ⚠️ PARTIAL | Archive has multi-step lookup, CALL→CE conversion, stripped variants. Greenfield has simpler lookup. |
| Unknown exchange handling | Raises `InstrumentNotFoundError` with clear message | Returns `None` (different error handling) | ❌ DIVERGENT | Archive uses explicit exception; greenfield returns None requiring caller to check. |
| Index fallback prevention | `expected_segment` parameter rejects index fallback for derivatives | No `expected_segment` parameter | ❎ NOT_PORTED | Archive prevents index/derivative misroutes; greenfield lacks this defense. |
| Audit logging | `security_id_issued` structured log with source tracking | No audit logging | ❎ NOT_PORTED | Archive tracks every security_id to its origin (CSV, MCX JSON, or hardcoded index). |
| Synthetic index tracking | `_synthetic_index_count` for coverage monitoring | Not implemented | ❎ NOT_PORTED | Archive detects when index fallback is used unexpectedly. |
| MCX detailed supplement | `_fetch_mcx_detailed()` with separate CSV download and merge | Not implemented | ❎ NOT_PORTED | Archive fetches MCX commodity details separately. Greenfield relies on main CSV only. |
| Instrument loader caching | 6-hour TTL, 7-day cleanup in `InstrumentLoader.load_cached()` | No caching - fetch on every `load()` | ❌ DIVERGENT | Archive caches to avoid repeated downloads; greenfield fetches fresh every time. |
| Index symbol handling | Hardcoded index table via `config.indices` | Not implemented (likely in resolver) | ⚠️ PARTIAL | Greenfield seems to rely on resolver lookup without index table. |

**Critial Finding:** The `expected_segment` constraint (PR-C) is missing in greenfield. This defense-in-depth feature prevents index/derivative confusion that could cause incorrect order placement.

---

## 4. Order Lifecycle

| Behavior | Archive Evidence | Greenfield Evidence | Status | Notes |
|----------|------------------|-------------------|--------|-------|
| Pre-trade validation | Lot size check, product type x segment check, tick size alignment | Only order type/price validation | ⚠️ PARTIAL | Archive validates lot size multiples, tick alignment, product-segment compatibility. Greenfield lacks these. |
| Idempotency | `SimpleIdempotencyCache` with correlation ID, atomic check-then-act | Not implemented | ❎ NOT_PORTED | Archive prevents duplicate orders on retry using correlation IDs. Greenfield has no idempotency. |
| Place order API | Accepts `BrokerOrderPayload` with all order fields | Accepts individual parameters | ⚠️ PARTIAL | Different API signatures but same core behavior. |
| Cancel order verification | Post-cancel order check, detects filled-before-cancel race | Same pattern | ✅ VERIFIED | Both verify order state after cancel. |
| Cancel using DELETE vs POST | Uses `DELETE /orders/{order_id}` | Uses `POST` to cancel endpoint | ❌ DIVERGENT | Different HTTP methods. Archive follows REST semantics; greenfield may follow Dhan API exactly. |
| Order response mapping | Full `OrderResponse` with status, error codes, correlation_id | `OrderResponse` via mapper | ✅ VERIFIED | Same response structure. |
| Risk manager check | Pre-trade check via `RiskManagerPort` | Not implemented | ❎ NOT_PORTED | Archive enforces risk checks at broker boundary. |
| Event publishing | `DomainEvent` on `ORDER_PLACED` | Not implemented | ❎ NOT_PORTED | Archive publishes events for downstream processing. |
| Kill switch | `kill_switch()` endpoint | Not implemented | ❎ NOT_PORTED | Archive can activate/deactivate kill switch. |
| Trade history pagination | `get_trade_history(from_date, to_date, page)` | Not implemented | ❎ NOT_PORTED | Archive supports paginated trade history. |
| Slice orders | `place_slice_order()` with auto-splitting | Not implemented | ❎ NOT_PORTED | Archive supports broker-managed slice orders. |

**Critical Finding:** **No idempotency in greenfield orders.** This is a PRODUCTION BLOCKER - duplicate order placement on network retries can cause catastrophic losses.

---

## 5. Reconciliation

| Behavior | Archive Evidence | Greenfield Evidence | Status | Notes |
|----------|------------------|-------------------|--------|-------|
| Position drift detection | Full `ReconciliationEngine.compare_positions()` | Simple dict quantity comparison | ❌ DIVERGENT | Archive has sophisticated drift detection with severity classification. Greenfield has basic matching. |
| Order drift detection | Full `ReconciliationEngine.compare_orders()` | Not implemented | ❎ NOT_PORTED | Archive compares orders by status, quantity, price. Greenfield lacks order reconciliation. |
| Auto-repair OMS state | `_repair_local_oms()` with upsert missing orders/positions | Not implemented | ❎ NOT_PORTED | Archive can repair local OMS from broker state. |
| Drift severity reporting | `HIGH`, `MEDIUM`, `LOW` severity levels via `DriftItem` | Simple match/mismatch lists | ❌ DIVERGENT | Archive provides structured severity for operational triage. |
| Reconciliation report | Full `ReconciliationReport` with counts and items | Simple dict with 4 lists | ⚠️ PARTIAL | Different output format; greenfield loses severity and counts. |

**Critical Finding:** Greenfield reconciliation is a simplified subset. The archive's full reconciliation with drift severity and auto-repair is NOT_PORTED.

---

## 6. Extended Features

| Feature | Archive Evidence | Greenfield Evidence | Status | Notes |
|---------|------------------|-------------------|--------|-------|
| Super Orders | `SuperOrdersAdapter` with full CRUD | `DhanSuperOrders` extension | ✅ VERIFIED | Same functionality. |
| Forever Orders | `ForeverOrdersAdapter` with SINGLE/OCO support | `DhanForeverOrders` extension | ✅ VERIFIED | Same functionality. |
| Conditional Triggers | `ConditionalTriggersAdapter` | `DhanConditionalTriggers` | ✅ VERIFIED | Same functionality. |
| EDIS TPIN generation | `generate_tpin()` via POST | Same implementation | ✅ VERIFIED | Same behavior. |
| EDIS authorization | `authorize_edis()` with ISIN validation | Not implemented (`get_edis_form()` instead) | ❌ DIVERGENT | Different API surface - archive has full authorization flow. |
| EDIS status check | Per-ISIN status via `check_status(isin)` | General `get_tpin_status()` | ❌ DIVERGENT | Different method signatures. |
| IP Management | `IPManagementAdapter` with IPv4 validation, type management | `DhanIpManagement` with whitelist methods | ⚠️ PARTIAL | Archive has IP modification + PRIMARY/SECONDARY types; greenfield has whitelist add/remove only. |
| Ledger | `LedgerAdapter.get_ledger()` with date validation, typed entries | `DhanLedger.get_ledger()` returns raw dicts | ⚠️ PARTIAL | Archive has typed `LedgerEntry` dataclass; greenfield returns raw dicts. |
| User Profile | `UserProfileAdapter` → typed `UserProfile` | `DhanUserProfile` returns raw dicts | ⚠️ PARTIAL | Archive has structured profile; greenfield returns raw dicts. |
| Futures chain | `FuturesAdapter.get_contracts()` from resolver cache | `DhanFutures.get_contract()` with expiry parsing | ❌ DIVERGENT | Different approaches: archive uses cached futures list, greenfield parses symbol strings. |
| Futures expiry listing | `FuturesAdapter.get_expiries()` | Not implemented | ❎ NOT_PORTED | Archive provides expiry listing; greenfield resolves contracts directly. |
| MTF orders | Via product type in orders | Dedicated `DhanMTF` adapter | 🔧 IMPROVED | Greenfield has dedicated MTF adapter. |

---

## 7. API Contract Compatibility

| Contract Element | Archive Behavior | Greenfield Behavior | Status | Notes |
|------------------|------------------|-------------------|--------|-------|
| `place_order()` parameters | symbol, exchange, side, quantity, price, order_type, product_type, validity, trigger_price, correlation_id | Same parameters | ✅ VERIFIED | Method signature compatible. |
| `place_order()` return type | `OrderResponse` with correlation_id, raw_payload | `OrderResponse` | ⚠️ PARTIAL | Archive includes more metadata. |
| `cancel_order()` return | `OrderResponse` with race detection | `OrderResponse` with race detection | ✅ VERIFIED | Same behavior. |
| `modify_order()` parameters | `**changes` dict with all optional fields | Individual optional parameters | ⚠️ PARTIAL | Different but compatible API. |
| `get_order()` return | `Order` or None | `Order` or None | ✅ VERIFIED | Same behavior. |
| `positions()` return | `list[Position]` | `list[Position]` | ✅ VERIFIED | Same behavior. |
| `holdings()` return | `list[Holding]` | `list[Holding]` | ✅ VERIFIED | Same behavior. |
| `market data` LTP | `Decimal` return | Same | ✅ VERIFIED | Same behavior. |
| `historical` return | `pd.DataFrame` with OHLCV | Same | ✅ VERIFIED | Same behavior. |
| Exception hierarchy | 14 specialized exception classes | 6 generic exception classes | ⚠️ PARTIAL | Archive has per-feature exceptions (`InstrumentNotFoundError`, `SuperOrderError`, etc.). Greenfield consolidates. |

---

## 8. Cross-Cutting Concerns

| Concern | Archive Evidence | Greenfield Evidence | Status | Notes |
|---------|------------------|-------------------|--------|-------|
| ObservabilityProvider protocol | Full implementation in `BrokerGateway` | Not implemented | ❎ NOT_PORTED | Archive exposes connection status, metadata, circuit breaker states programmatically. |
| Prometheus metrics | 9 metrics: requests, duration, errors, rate limit retries, WS subs, callbacks, reconnects, ticks, dropped ticks | 3 metrics: requests total, errors, duration | ⚠️ PARTIAL | Greenfield covers HTTP metrics but drops all WebSocket metrics. |
| Circuit breakers | Per-category breakers (orders, market_data, portfolio, admin) with adaptive rate limiting | Per-category breakers via `BaseResilientHttpClient` + `create_circuit_breakers()` | ✅ VERIFIED | Greenfield has circuit breakers integrated via base class. Both use read/write/admin categories. |
| Retry logic | Configurable via `DhanResilienceConfig`, retry executor | `RetryPolicy` via `BaseResilientHttpClient` with 3 retries, exponential backoff | ✅ VERIFIED | Both have retry logic; greenfield uses `RetryPolicy` from resilience module. |
| TTL/caching | `InstrumentLoader` with TTL, cleanup | No caching | ❌ DIVERGENT | Archive has proper TTL-based caching. |
| Configuration loading | Multi-source: env vars, JSON, .env files with deep merge | Hardcoded in `config.py` | ❌ DIVERGENT | Archive supports dynamic configuration; greenfield is static. |
| Structured logging | Full audit trail on every order, token refresh, instrument resolution | Basic logging | ⚠️ PARTIAL | Archive has richer structured logging. |

---

## 9. Behavioral Traceability Matrix

| Feature | Archive Implementation | Archive Tests | Greenfield Implementation | Greenfield Tests | Status |
|---------|-----------------------|--------------|------------------------|-----------------|--------|
| Place order with idempotency | `OrdersAdapter.place_order()` + `IdempotencyCache` | test_dhan_auth_state.py lines 45-60 | `DhanOrders.place_order()` | test_dhan_adapter.py lines 12-25 | ❎ NOT_PORTED (missing idempotency) |
| TOTP rate limit guard | `TotpCooldownGuard` + `TotpRateLimitError` | test_order_factory_dhan_resolver.py | None | Not verified | ❎ NOT_PORTED |
| Index derivative disambiguation | `expected_segment` in `resolve_ref()` | Covered in resolver tests | None | Not verified | ❎ NOT_PORTED |
| Reconciliation auto-repair | `DhanReconciliationService._repair_local_oms()` | Covered in reconciliation tests | None | Not verified | ❎ NOT_PORTED |
| Session lifecycle states | `DhanSessionManager.lifecycle_state()` | test_dhan_auth_state.py lines 30-40 | None | Not verified | ❎ NOT_PORTED |
| Circuit breaker states | `circuit_breaker_states` property | test_dhan_websockets.py lines 18-25 | Unknown | Not verified | ⚠️ UNKNOWN |
| Account registry singleton | `AccountConnectionRegistry` with thread-safe get_or_create | test_order_factory_dhan_resolver.py | None | Not verified | ❎ NOT_PORTED |

---

## 10. Risk Assessment

| Finding | Severity | Likelihood | Impact | Detection | Mitigation |
|---------|----------|------------|--------|-----------|------------|
| No idempotency in place_order | CRITICAL | HIGH | Catastrophic (duplicate orders → unintended positions) | Automated testing with network fault injection | Add `SimpleIdempotencyCache` integration with correlation ID |
| Missing TOTP cooldown guard (shared lock) | HIGH | MEDIUM | Token generation lockout for 2 minutes | Stress testing with concurrent requests | Verify `TotpCooldownGuard` integration or implement shared lock cooldown |
| No index/derivative disambiguation | HIGH | HIGH | Wrong order placement (index instead of futures) | Normal usage with derivative symbols | Add `expected_segment` parameter in identity resolution |
| No ObservabilityProvider protocol | HIGH | MEDIUM | No programmatic health checks for infra bootstrap | Infrastructure integration testing | Implement protocol methods in `DhanGateway` |
| No session manager | MEDIUM | LOW | Operational visibility gaps | Monitoring review | Implement `DhanSessionManager` or expose connection states |
| Reconciliation lacks auto-repair | MEDIUM | LOW | Stale OMS state during network partitions | Reconciliation testing | Add drift severity and optional auto-repair |
| No instrument caching | LOW | HIGH | Performance degradation, unnecessary CSV downloads | Load testing | Add TTL-based caching with 6-hour expiry |
| Missing audit logging | LOW | MEDIUM | No forensic trail for security_id resolution | Security audit | Add structured logging for every security_id issuance |

---

## 11. Production Readiness Checklist

| Category | Status | Evidence |
|----------|--------|----------|
| Authentication | ⚠️ PARTIAL | TOTP works but no rate-limit guard; refresh lock needs timeout verification |
| Instrument Download | ❌ DIVERGENT | No caching; no MCX supplement; no index table |
| Caching | ❎ NOT_PORTED | Archive has TTL-based caching; greenfield has none |
| Orders | ❌ DIVERGENT | No idempotency; missing validation; no risk checks |
| Market Data | ⚠️ PARTIAL | Basic implementation; needs circuit breaker verification |
| Historical Data | ✅ VERIFIED | Same DataFrame-based return |
| Portfolio | ✅ VERIFIED | Position/holding fetch works |
| Rate Limits | ✅ VERIFIED | Rate limiter integrated via `BaseResilientHttpClient` with token bucket |
| Retry Logic | ✅ VERIFIED | `RetryPolicy` with 3 retries, 500ms base, 5s max |
| Timeouts | ✅ VERIFIED | 10s default timeout configured |
| Fault Tolerance | ⚠️ PARTIAL | Some resilience patterns; missing idempotency, cooldown |
| Logging | ⚠️ PARTIAL | Basic logging; no audit trail on security_id issuance |
| Metrics | ⚠️ PARTIAL | HTTP metrics; no WebSocket metrics |
| Tracing | ⚠️ PARTIAL | Correlation ID not verified in all paths; needs audit trail enhancement |
| Configuration | ❌ DIVERGENT | Static config vs dynamic loader |
| Security | ✅ VERIFIED | Token persistence, IPv4 patch |
| Observability | ❎ NOT_PORTED | No ObservabilityProvider protocol |

---

## 12. Final Verdict

### NOT READY FOR PRODUCTION

**Reasons:**

1. **CRITICAL:** No idempotency in order placement - network retries will create duplicate orders
2. **CRITICAL:** Missing TOTP cooldown guard - can trigger rate limits and lock out token generation
3. **HIGH:** No index/derivative disambiguation (PR-C) - can cause wrong order placement
4. **HIGH:** Missing observability provider protocol - no programmatic health/status access
5. **MEDIUM:** No session manager - operational visibility gaps
6. **MEDIUM:** Reconciliation lacks auto-repair and drift severity
7. **LOW:** No instrument caching - performance and rate limit concerns

**Required Before Production:**

- [ ] Add `SimpleIdempotencyCache` to `DhanOrders` with correlation ID tracking (CRITICAL)
- [ ] Add `TotpCooldownGuard` or shared lock cooldown to `DhanAuth` for rate limit protection (HIGH)
- [ ] Add `expected_segment` parameter in identity resolution to prevent index/derivative confusion (HIGH)
- [ ] Implement `ObservabilityProvider` protocol methods in `DhanGateway` (HIGH)
- [ ] Add `DhanSessionManager` or expose connection states via health endpoint (MEDIUM)
- [ ] Enhance reconciliation with drift severity and optional auto-repair (MEDIUM)
- [ ] Add TTL-based instrument caching (6-hour expiry) (LOW)
- [ ] Add structured audit logging for security_id issuance (LOW)

---

## Evidence References

- Archive gateway: `/Users/apple/Downloads/INC_Trade/archive/brokers/dhan/gateway.py` (lines 27-32 for ObservabilityProvider, 549-565 for idempotency)
- Archive TOTP: `/Users/apple/Downloads/INC_Trade/archive/brokers/dhan/totp_client.py` (lines 20-27 for cooldown guard)
- Archive identity: `/Users/apple/Downloads/INC_Trade/archive/brokers/dhan/identity.py` (lines 322-368 for resolve_ref with expected_segment)
- Archive reconciliation: `/Users/apple/Downloads/INC_Trade/archive/brokers/dhan/reconciliation.py` (lines 76-145 for full reconciliation)
- Greenfield orders: `/Users/apple/Downloads/INC_Trade/brokers/adapters/dhan/orders.py` (no idempotency cache)
- Greenfield auth: `/Users/apple/Downloads/INC_Trade/brokers/adapters/dhan/auth.py` (no cooldown guard)
- Evidence matrix: `/Users/apple/Downloads/INC_Trade/review/greenfield-protocol/dhan/phase8/evidence_matrix.md`