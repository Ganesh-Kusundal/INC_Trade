# Phase 7 — Failure Analysis: Portfolio & Margin
> Greenfield Broker Replication Protocol — Dhan
> Phase 7: Portfolio & Margin
> Sources: archive `portfolio.py` (103 lines), `margin.py` (116 lines); greenfield `adapters/dhan/portfolio.py` (55 lines), `ports/portfolio.py` (19 lines), `services/portfolio_service.py` (51 lines), `domain/entities.py`, `domain/enums.py`, `domain/exceptions.py`

---

## 1. Timeout Policies

### 1.1 Archive
**No explicit timeout policy for portfolio or margin requests.**

`PortfolioAdapter` and `MarginAdapter` delegate to `DhanHttpClient.get()` / `DhanHttpClient.post()`. Timeout behavior is inherited from the HTTP client's default configuration. There is:
- No per-endpoint timeout override for `/positions`, `/holdings`, `/fundlimit`, `/margincalculator`.
- No timeout parameter exposed on `get_positions()`, `get_holdings()`, `get_balance()`, or `MarginAdapter.calculate()`.
- No client-side deadline enforcement.

**Risk:** A slow Dhan API will block the calling thread indefinitely. Portfolio reads are typically called at strategy startup and periodically — a hang here can stall strategy initialization.

### 1.2 Greenfield
**Same situation — no explicit timeout policy.**

`DhanPortfolio` delegates to `DhanHttpClient.get(ENDPOINTS[...])`. The `ENDPOINTS` config defines URLs but not timeouts. `PortfolioPort` has no timeout parameter on any method. `PortfolioService` adds no timeout wrapper.

**Rate limits** in `config.py` define inter-request intervals for `/orders` (25 req/s) but do not cover portfolio endpoints (`/positions`, `/holdings`, `/fundlimit`, `/margincalculator`).

### 1.3 Gap Assessment

| Requirement | Status | Risk |
|---|---|---|
| Per-request timeout | **MISSING** | Thread blocked indefinitely on portfolio read |
| Connect timeout | **MISSING** | DNS/TCP hang at strategy startup |
| Read timeout | **MISSING** | API hangs after connect |
| Portfolio-specific timeout | **MISSING** | Portfolio reads are bursty at startup; need tighter bounds |
| Margin calculator timeout | **MISSING** | Pre-order margin check can stall order submission |
| Timeout propagation from port | **MISSING** | `PortfolioPort` has no timeout parameter |

---

## 2. Exception Hierarchy for Portfolio

### 2.1 Domain Exception Tree

```
TradeXV2Error
├── ConfigError
├── DataError
├── ValidationError
├── BrokerError(code: str)
│   ├── RetryableError
│   │   └── NetworkError          ← connection reset, timeout, DNS
│   ├── NonRetryableError
│   ├── BrokerServerError         ← HTTP 5xx
│   ├── RateLimitError(retry_after)  ← HTTP 429
│   ├── CircuitOpenError          ← circuit breaker open
│   ├── AuthenticationError       ← token expired/invalid
│   ├── TokenRateLimitError       ← token generation cooldown
│   ├── InstrumentNotFoundError(symbol)
│   ├── NotSupportedError         ← operation not supported
│   ├── BrokerDegradedError(health_status)
│   └── OrderRejectedError(order_id)
```

### 2.2 Exceptions Actually Raised by Portfolio/Margin Code

| Component | Exception | Condition | Caught by caller? |
|---|---|---|---|
| Archive `PortfolioAdapter.get_positions()` | (none) | Bad data → silently skipped | N/A — graceful |
| Archive `PortfolioAdapter.get_holdings()` | (none) | Bad data → silently skipped | N/A — graceful |
| Archive `PortfolioAdapter.get_balance()` | (none) | Bad data → returns empty `Balance()` | N/A — graceful |
| Archive `_parse_product()` | (none) | Unknown product → defaults to `INTRADAY` | N/A — silent fallback |
| Archive `MarginAdapter.calculate()` | `ValueError` | Request validation fails (qty ≤ 0, missing price) | Not in adapter; caller must handle |
| Archive `MarginAdapter.calculate()` | `AssertionError` | `assert_dhan_payload` fails | Should never happen (bug) |
| Greenfield `DhanPortfolio.positions()` | (none) | Bad data → silently skipped via mapper | N/A — graceful |
| Greenfield `DhanPortfolio.holdings()` | (none) | Bad data → silently skipped via mapper | N/A — graceful |
| Greenfield `DhanPortfolio.funds()` | (none) | Bad data → returns `Balance(available_cash=Decimal("0"))` | N/A — silent zero |
| Greenfield `DhanPortfolio.trades()` | (none) | Bad data → silently skipped via mapper | N/A — graceful |
| Greenfield `PortfolioService.total_unrealized_pnl()` | (none) | Sums over positions; empty list → `Decimal("0")` | N/A — graceful |
| Both adapters | `NetworkError` | Connection failure | Caller must handle |
| Both adapters | `RateLimitError` | HTTP 429 | Caller must handle |
| Both adapters | `BrokerServerError` | HTTP 5xx | Caller must handle |
| Both adapters | `AuthenticationError` | Token expired | Caller must handle |

### 2.3 Exception Contract Gaps

1. **Archive raises `ValueError` for invalid margin requests** — should be `ValidationError` (domain exception).
2. **Greenfield silently returns zero balance** — caller cannot distinguish "zero funds" from "data unavailable."
3. **No `PortfolioError` or `MarginError` in domain** — portfolio/margin failures surface as generic `BrokerError`.
4. **No `DataError` usage** — `DataError` exists in domain but is never raised by portfolio or margin code.
5. **Archive `_parse_product` silently defaults to INTRADAY** — unknown product types are masked, not reported.
6. **Greenfield mapper has no validation** — `map_position`, `map_holding`, `map_balance`, `map_trade` accept any dict and silently default missing fields to zero/empty.

---

## 3. Race Conditions Inventory

### 3.1 Portfolio Service Race Conditions

**RC-1: Stale Position Snapshot**
```
Thread A: calls positions() → fetches from API
Thread B: submits order → position changes on broker
Thread A: returns stale positions list
```
**Impact:** Medium. Portfolio snapshots are point-in-time reads. If a strategy reads positions while simultaneously submitting orders, the snapshot may not reflect the just-submitted order. This is inherent to REST-based portfolio reads — not a bug, but a design limitation.

**Mitigation:** Document that `positions()` returns a snapshot at call time. Strategies should not assume consistency between `positions()` and subsequent order operations.

**RC-2: Concurrent Balance Reads**
```
Thread A: calls funds() → fetches from API
Thread B: calls funds() → fetches from API
Both threads hit the API simultaneously
```
**Impact:** Low. Both reads are idempotent. Wastes 1 API call. No caching in `PortfolioService` to prevent this.

**Mitigation:** Add TTL cache in `PortfolioService` (similar to `MarketDataService`).

**RC-3: PnL Aggregation During Position Update**
```
Thread A: calls total_unrealized_pnl() → iterates positions
Thread B: calls positions() → returns new list
Thread A: still iterating old list → computes PnL from stale data
```
**Impact:** Low. `total_unrealized_pnl()` fetches positions once and iterates. The list is immutable (frozen dataclasses). No corruption, just stale data.

**RC-4: Margin Calculate vs Order Submit**
```
Thread A: calls MarginAdapter.calculate() → gets margin requirement
Thread B: submits order → consumes margin
Thread A: submits order based on stale margin calculation
```
**Impact:** Medium. Margin calculation is point-in-time. Between calculation and order submission, available margin may change. This is inherent to pre-trade margin checks.

**Mitigation:** Document that margin calculation is advisory. Final validation happens at broker.

### 3.2 Shared HTTP Client Race Conditions

**RC-5: Shared DhanHttpClient**
Multiple threads using the same `DhanHttpClient` instance. If the client maintains session state (cookies, tokens), concurrent requests could interfere.

**Impact:** Depends on HTTP client implementation. If using `requests.Session`, it is thread-safe for most operations but not for connection pooling under heavy load.

### 3.3 Mapper Race Conditions

**RC-6: Mapper is Pure Function**
`map_position`, `map_holding`, `map_balance`, `map_trade` are pure functions with no shared state. No race conditions.

**Impact:** None. Thread-safe by design.

---

## 4. Recovery Paths

### 4.1 Network Failure

| Scenario | Archive behavior | Greenfield behavior | Recommended |
|---|---|---|---|
| Connection refused | Exception propagates | Exception propagates | Retry with backoff |
| Connection reset mid-request | Exception propagates | Exception propagates | Idempotent retry (reads are safe) |
| DNS failure | Exception propagates | Exception propagates | Retry with backoff |
| TLS handshake failure | Exception propagates | Exception propagates | Retry, then alert |

**Current state:** No retry at adapter level. The infrastructure layer has `retry.py` but it is not wired into portfolio adapters.

### 4.2 Rate Limiting (HTTP 429)

| Scenario | Archive behavior | Greenfield behavior | Recommended |
|---|---|---|---|
| HTTP 429 on positions | `RateLimitError` propagates | `RateLimitError` propagates | Respect `retry_after`, exponential backoff |
| HTTP 429 on holdings | `RateLimitError` propagates | `RateLimitError` propagates | Queue and retry |
| HTTP 429 on fundlimit | `RateLimitError` propagates | `RateLimitError` propagates | Respect `retry_after` |
| HTTP 429 on margincalculator | `RateLimitError` propagates | `RateLimitError` propagates | Queue and retry |
| Token rate limit | `TokenRateLimitError` | `TokenRateLimitError` | Honor cooldown period |

**Current state:** `RateLimitError` carries `retry_after` but no caller respects it. `RATE_LIMITS` config does not cover portfolio endpoints.

### 4.3 Data Unavailability

| Scenario | Archive behavior | Greenfield behavior | Recommended |
|---|---|---|---|
| API returns empty list | Empty list `[]` | Empty list `[]` | Consistent — both return empty |
| API returns unexpected format | Empty list `[]` or empty `Balance()` | Empty list `[]` or zero `Balance` | **Divergence** — should raise or return explicit error |
| Balance API returns non-dict | Logs warning, returns empty `Balance()` | Returns `Balance(available_cash=Decimal("0"))` | **Divergence** — greenfield does not log warning |
| Margin request validation fails | `ValueError` raised | N/A — no greenfield margin adapter | **NOT PORTED** |

### 4.4 Data Parsing Errors

| Scenario | Archive behavior | Greenfield behavior |
|---|---|---|
| Unexpected response format | Empty list or empty `Balance()` | Empty list or zero `Balance` via mapper |
| Missing position fields | Defaults to zero/empty via `.get()` | Defaults to zero/empty via mapper `.get()` |
| Missing holding fields | Defaults to zero/empty via `.get()` with fallbacks | Defaults to zero/empty via mapper `.get()` with fallbacks |
| Missing balance fields | Defaults to zero via `.get()` | Defaults to zero via mapper `.get()` |
| Unknown product type | Defaults to `INTRADAY` | Defaults to `INTRADAY` via `_PRODUCT_MAP.get()` |

**Both implementations are robust** in parsing — they handle missing fields gracefully with defaults.

---

## 5. Data Validation Errors

### 5.1 Margin Request Validation

**Archive:** `MarginAdapter._validate_request()` validates:
- `quantity > 0`
- `LIMIT`/`STOP_LOSS` orders require `price > 0`

**Greenfield:** No margin adapter exists. No validation.

**Gap:** Margin calculation is NOT PORTED to greenfield.

### 5.2 Position/Holding/Balance Validation

Neither implementation validates input parameters before making API calls. There are no input parameters to validate — these are read-only operations with no arguments.

### 5.3 Product Type Parsing

**Archive:** `_parse_product(pt: str)` attempts `ProductType(str(pt))`. Falls back to `INTRADAY` on `ValueError`.

**Greenfield:** `_PRODUCT_MAP.get(data.get("productType", "INTRADAY"), ProductType.INTRADAY)` in mapper. Falls back to `INTRADAY` for unknown products.

**Gap:** Both silently default to `INTRADAY` for unknown product types. This masks data quality issues.

### 5.4 Exchange Segment Mapping

**Archive:** Uses `segment_to_exchange()` from `brokers.dhan.segments`.

**Greenfield:** Uses `_normalize_exchange()` in `mapper.py` with hardcoded mapping dict.

**Gap:** Different function names and implementations. Greenfield mapping is more complete (includes `IDX_I` → `INDEX`).

---

## 6. Secret Exposure Risks

### 6.1 Analysis

Portfolio and margin APIs require authentication (access token in HTTP headers). The risk surface:

| Risk | Archive | Greenfield | Assessment |
|---|---|---|---|
| Token in URL | No — GET/POST body | No — GET/POST body | Safe |
| Token in logs | Possible if `DhanHttpClient` logs headers | Possible if `DhanHttpClient` logs headers | **Review HTTP client** |
| Symbol/exchange in logs | Yes — `logger.info("positions_fetched", ...)` | No post-fetch logging | Acceptable (no secrets) |
| Client ID in logs | Archive margin logs `symbol`, `quantity`, `total_margin` | No margin adapter | Low risk |
| Payload in error messages | `ValueError(f"Margin request validation failed: {msg}")` | No equivalent | Safe — no sensitive data |
| Exception stack traces | `KeyError` on missing data (not raised — `.get()` used) | No KeyError — silent | Safe |

### 6.2 Recommendations

1. Ensure `DhanHttpClient` redacts `Authorization` headers in log output.
2. Avoid including full API response bodies in exception messages.
3. The greenfield's silent-zero approach avoids secret exposure but creates a different class of problems (data integrity).

---

## 7. Greenfield Gaps Summary

### 7.1 Critical Gaps

| ID | Gap | Impact | Recommendation |
|---|---|---|---|
| G-1 | No margin calculator adapter | Pre-trade margin checking is impossible | Port `MarginAdapter` to greenfield |
| G-2 | No margin request validation | Cannot validate margin requests before API call | Port `_validate_request()` logic |

### 7.2 High Severity Gaps

| ID | Gap | Impact | Recommendation |
|---|---|---|---|
| G-3 | Balance returns zero instead of erroring | Caller cannot detect data unavailability | Raise `DataError` or return `Optional[Balance]` |
| G-4 | No post-fetch logging for portfolio data | Lost observability: cannot audit position/holding counts | Add structured logging after fetch |
| G-5 | No `available_quantity` on `Holding` entity | Archive tracks available qty separately from total qty | Add `available_quantity: int = 0` to `Holding` |
| G-6 | No `ltp` or `pnl` fields on `Holding` entity | Archive computes PnL and tracks LTP for holdings | Add `ltp: Decimal` and `pnl: Decimal` to `Holding` |

### 7.3 Moderate Gaps

| ID | Gap | Impact | Recommendation |
|---|---|---|---|
| G-7 | No request timeout | Thread can block indefinitely | Add timeout parameter to port methods |
| G-8 | No retry at adapter level | Transient failures propagate | Wire infrastructure retry into adapters |
| G-9 | Product type silently defaults to INTRADAY | Unknown product types are masked | Log warning on unknown product type |
| G-10 | No `sod_limit`, `collateral_amount`, `withdrawable_balance` on `Balance` | Archive tracks 5 balance fields; greenfield tracks 3 | Extend `Balance` entity |
| G-11 | No portfolio caching | Every call hits the API | Add TTL cache in `PortfolioService` |

### 7.4 Low-Priority Gaps

| ID | Gap | Impact | Recommendation |
|---|---|---|---|
| G-12 | `PortfolioPort` not `@runtime_checkable` | Cannot use `isinstance()` checks | Add `@runtime_checkable` for consistency |
| G-13 | No async support | Cannot use in async contexts | Document as sync-only or add async port |
| G-14 | No portfolio metrics | Cannot observe fetch latency | Add counters via observability infrastructure |
| G-15 | No circuit breaker at adapter level | Repeated failures waste resources | Rely on infrastructure circuit breaker |

---

## 8. Risk Matrix

```
                        Impact
                  Low      Medium    High
              ┌─────────┬─────────┬─────────┐
    Certain   │         │ G-3,G-4 │ G-1     │
              │         │ G-5,G-6 │ G-2     │
              ├─────────┼─────────┼─────────┤
Likely        │ G-11    │ G-7     │         │
              │         │ G-8     │         │
              ├─────────┼─────────┼─────────┤
Unlikely      │ G-12    │ G-9     │ G-10    │
              │ G-13    │ G-15    │         │
              │ G-14    │         │         │
              └─────────┴─────────┴─────────┘
```

**Top 3 priorities:**
1. **G-1/G-2:** Port margin calculator — pre-trade risk check is critical.
2. **G-3:** Stop returning silent zeros for missing balance — data integrity issue.
3. **G-5/G-6:** Add missing fields to `Holding` entity — data completeness issue.
