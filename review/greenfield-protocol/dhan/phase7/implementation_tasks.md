# Phase 7 — Implementation Tasks: Portfolio & Margin
## Greenfield Broker Replication Protocol — Dhan Broker

**Protocol:** Greenfield Broker Replication Protocol
**Phase:** 7 — Portfolio & Margin
**Date:** 2026-07-03
**Status:** Implementation Plan

---

## 1. Task Dependency Graph

```
Layer 0 (No Dependencies) — Critical Data-Correctness Fixes
├── T0.1: Port margin calculator adapter
├── T0.2: Extend Holding entity (ltp, pnl, available_quantity)
└── T0.3: Extend Balance entity (sod_limit, collateral_amount, withdrawable_balance)

Layer 1 (Depends on Layer 0) — Behavioral Parity Fixes
├── T1.1: Fix balance error handling [depends on T0.3]
├── T1.2: Add post-fetch logging [independent]
├── T1.3: Fix product type parsing [independent]
└── T1.4: Add @runtime_checkable to PortfolioPort [independent]

Layer 2 (Depends on Layer 1) — Missing Features
├── T2.1: Add portfolio caching [depends on T1.1, T1.2]
├── T2.2: Add request timeout [depends on T1.1]
└── T2.3: Add retry at adapter level [depends on T1.1]

Layer 3 (Depends on Layer 2) — Enhancements & Polish
├── T3.1: Add portfolio metrics [depends on T2.1]
├── T3.2: Add circuit breaker at adapter level [depends on T2.3]
└── T3.3: Add positions_to_dataframe utility [depends on T0.2]
```

**Dependency Rationale:**
- Layer 0: Critical missing functionality (margin calculator) and data model gaps
- Layer 1: Observability and behavioral alignment
- Layer 2: Performance and reliability enhancements
- Layer 3: Metrics and convenience features

---

## 2. Layer 0 — No Dependencies (Critical Data-Correctness Fixes)

### T0.1: Port Margin Calculator Adapter

**Priority:** CRITICAL
**Gap Reference:** Evidence Matrix #32-37; Design Doc G-1, G-2
**Estimated Effort:** 3 hours

**Problem:**
Archive has `MarginAdapter` with `calculate()` method that POSTs to `/margincalculator`. Includes request validation (`_validate_request`) and invariant assertion (`assert_dhan_payload`). Greenfield has no margin adapter. Pre-trade margin checking is impossible.

**Implementation Steps:**

1. **Create MarginPort**
   ```python
   # brokers/ports/margin.py
   from typing import Protocol
   from decimal import Decimal
   
   class MarginRequest:
       symbol: str
       exchange: str
       quantity: int
       order_type: str
       product_type: str
       price: Decimal | None = None
       trigger_price: Decimal | None = None
   
   class MarginResponse:
       total_margin: Decimal
       order_margin: Decimal
       exposure_margin: Decimal
       available_margin: Decimal | None = None
       span_margin: Decimal | None = None
   
   class MarginPort(Protocol):
       def calculate(self, request: MarginRequest) -> MarginResponse: ...
   ```

2. **Create DhanMargin adapter**
   ```python
   # brokers/adapters/dhan/margin.py
   class DhanMargin:
       def __init__(self, client: DhanHttpClient, resolver: DhanInstrumentResolver):
           self._client = client
           self._resolver = resolver
       
       def calculate(self, request: MarginRequest) -> MarginResponse:
           errors = self._validate_request(request)
           if errors:
               raise ValidationError(f"Margin request validation failed: {'; '.join(errors)}")
           
           ref = self._resolver.resolve(request.symbol, request.exchange)
           payload = {
               "dhanClientId": self._client.client_id,
               "exchangeSegment": ref.exchange_segment,
               "securityId": ref.security_id_str(),
               "transactionType": "BUY",
               "orderType": request.order_type,
               "productType": request.product_type,
               "quantity": request.quantity,
           }
           if request.price and request.price > 0:
               payload["price"] = to_wire_float(request.price)
           if request.trigger_price and request.trigger_price > 0:
               payload["triggerPrice"] = to_wire_float(request.trigger_price)
           
           assert_valid_dhan_payload(payload, context="margin.calculate")
           data = self._client.post(ENDPOINTS["margincalculator"], json=payload)
           return self._parse_response(data)
       
       def _validate_request(self, request: MarginRequest) -> list[str]:
           errors = []
           if request.quantity <= 0:
               errors.append(f"Quantity must be positive, got {request.quantity}")
           if request.order_type in ("LIMIT", "STOP_LOSS") and (not request.price or request.price <= 0):
               errors.append("LIMIT/STOP_LOSS orders require price > 0")
           return errors
       
       def _parse_response(self, data: dict) -> MarginResponse:
           response_data = data.get("data", data)
           return MarginResponse(
               total_margin=to_decimal(response_data.get("totalMargin", 0)),
               order_margin=to_decimal(response_data.get("orderMargin", 0)),
               exposure_margin=to_decimal(response_data.get("exposureMargin", 0)),
               available_margin=to_decimal(response_data["availableMargin"]) if "availableMargin" in response_data else None,
               span_margin=to_decimal(response_data["spanMargin"]) if "spanMargin" in response_data else None,
           )
   ```

3. **Add margincalculator endpoint to config**
   ```python
   # brokers/adapters/dhan/config.py — add to ENDPOINTS dict
   "margincalculator": f"{REST_BASE}/margincalculator",
   ```

4. **Add unit tests**
   ```python
   # brokers/tests/test_margin.py
   def test_margin_calculate_success():
       # Mock client, verify payload and response parsing
   
   def test_margin_validate_quantity():
       # Verify quantity <= 0 raises ValidationError
   
   def test_margin_validate_limit_price():
       # Verify LIMIT order without price raises ValidationError
   ```

**Acceptance Criteria:**
- `DhanMargin.calculate()` POSTs to `/margincalculator` with correct payload
- Request validation rejects qty ≤ 0 and missing price for LIMIT/STOP_LOSS
- Invariant assertion validates payload before API call
- Response parsing extracts all margin fields
- Unit tests pass for success and validation failure paths

---

### T0.2: Extend Holding Entity

**Priority:** HIGH
**Gap Reference:** Evidence Matrix #15-17; Design Doc G-5, G-6
**Estimated Effort:** 1 hour

**Problem:**
Archive reads `ltp`, computes `pnl`, reads `availableQty` for holdings. Greenfield `Holding` entity has no `ltp`, `pnl`, `available_quantity` fields. This data is lost.

**Implementation Steps:**

1. **Extend Holding dataclass**
   ```python
   # brokers/domain/entities.py
   @dataclass(frozen=True)
   class Holding:
       symbol: str
       exchange: str
       quantity: int
       average_price: Decimal = Decimal("0")
       isin: str = ""
       t1_quantity: int = 0
       ltp: Decimal = Decimal("0")                    # NEW
       pnl: Decimal = Decimal("0")                    # NEW
       available_quantity: int = 0                    # NEW
   ```

2. **Update map_holding to populate new fields**
   ```python
   # brokers/adapters/dhan/mapper.py — map_holding()
   def map_holding(data: dict) -> Holding:
       qty = int(data.get("holdingQty", data.get("quantity", 0)))
       avg_px = to_decimal(data.get("avgBuyPrice", data.get("costPrice", 0)))
       ltp = to_decimal(data.get("lastTradedPrice", data.get("lastPrice", 0)))
       available_qty = int(data.get("availableQty", data.get("availableQuantity", 0)))
       
       # Compute PnL if not provided
       pnl_raw = data.get("pnlValue")
       if pnl_raw is not None:
           pnl = to_decimal(pnl_raw)
       elif avg_px > 0 and ltp > 0:
           pnl = (ltp - avg_px) * qty
       else:
           pnl = Decimal("0")
       
       return Holding(
           symbol=data.get("tradingSymbol", ""),
           exchange=_normalize_exchange(data.get("exchangeSegment", "")),
           quantity=qty,
           average_price=avg_px,
           isin=data.get("isin", ""),
           t1_quantity=int(data.get("t1Qty", 0)),
           ltp=ltp,
           pnl=pnl,
           available_quantity=available_qty,
       )
   ```

3. **Add unit tests**
   ```python
   def test_holding_includes_ltp_and_pnl():
       # Verify ltp and pnl populated from API response
   
   def test_holding_pnl_computed_when_missing():
       # Verify PnL computed from (ltp - avg_px) * qty when pnlValue is None
   
   def test_holding_available_quantity():
       # Verify available_quantity populated from API response
   ```

**Acceptance Criteria:**
- `Holding` entity includes `ltp`, `pnl`, `available_quantity` fields
- `map_holding()` populates new fields from API response
- PnL computed client-side when not provided by API (matches archive behavior)
- Existing tests still pass (backward compatible defaults)

---

### T0.3: Extend Balance Entity

**Priority:** MEDIUM
**Gap Reference:** Evidence Matrix #23-26; Design Doc G-10
**Estimated Effort:** 0.5 hours

**Problem:**
Archive reads 5 balance fields: `availabelBalance`, `sodLimit`, `collateralAmount`, `utilizedAmount`, `withdrawableBalance`. Greenfield `Balance` entity has only 3 fields: `available_cash`, `utilized_margin`, `total_margin`. Missing: `sod_limit`, `collateral_amount`, `withdrawable_balance`.

**Implementation Steps:**

1. **Extend Balance dataclass**
   ```python
   # brokers/domain/entities.py
   @dataclass(frozen=True)
   class Balance:
       available_cash: Decimal
       utilized_margin: Decimal = Decimal("0")
       total_margin: Decimal = Decimal("0")
       sod_limit: Decimal = Decimal("0")              # NEW
       collateral_amount: Decimal = Decimal("0")      # NEW
       withdrawable_balance: Decimal = Decimal("0")   # NEW
   ```

2. **Update map_balance to populate new fields**
   ```python
   # brokers/adapters/dhan/mapper.py — map_balance()
   def map_balance(data: dict) -> Balance:
       return Balance(
           available_cash=to_decimal(data.get("availabelBalance", data.get("availableMargin", 0))),
           utilized_margin=to_decimal(data.get("utilizedAmount", data.get("utilizedMargin", 0))),
           total_margin=to_decimal(data.get("totalMargin", 0)),
           sod_limit=to_decimal(data.get("sodLimit", 0)),
           collateral_amount=to_decimal(data.get("collateralAmount", 0)),
           withdrawable_balance=to_decimal(data.get("withdrawableBalance", 0)),
       )
   ```

3. **Add unit tests**
   ```python
   def test_balance_includes_all_fields():
       # Verify all 6 fields populated from API response
   ```

**Acceptance Criteria:**
- `Balance` entity includes `sod_limit`, `collateral_amount`, `withdrawable_balance` fields
- `map_balance()` populates new fields from API response
- Existing tests still pass (backward compatible defaults)

---

## 3. Layer 1 — Depends on Layer 0 (Behavioral Parity Fixes)

### T1.1: Fix Balance Error Handling

**Priority:** HIGH
**Gap Reference:** Evidence Matrix #27; Design Doc G-3
**Estimated Effort:** 0.5 hours
**Depends on:** T0.3

**Problem:**
Greenfield returns `Balance(available_cash=Decimal("0"))` when balance API returns unexpected format. Archive logs warning and returns empty `Balance()`. Silent zero masks data availability issues.

**Implementation Steps:**

1. **Raise on unexpected balance format**
   ```python
   # brokers/adapters/dhan/portfolio.py — funds()
   def funds(self) -> Balance:
       data = self._client.get(ENDPOINTS["fund_limit"])
       if isinstance(data, dict):
           if "availabelBalance" in data or "sodLimit" in data:
               return map_balance(data)
           items = data.get("data", [])
           if isinstance(items, list) and items:
               return map_balance(items[0])
       logger.warning("balance_fetch_failed", extra={"reason": "unexpected_response_type"})
       raise DataError("Balance API returned unexpected format")
   ```

2. **Add unit test**
   ```python
   def test_funds_raises_on_unexpected_format():
       # Mock client returning non-dict
       # Assert DataError raised
   ```

**Acceptance Criteria:**
- Unexpected balance format raises `DataError`
- Warning logged before raising
- Unit test verifies error is raised for unexpected format

---

### T1.2: Add Post-Fetch Logging

**Priority:** MEDIUM
**Gap Reference:** Evidence Matrix #11, #20, #29; Design Doc G-4
**Estimated Effort:** 0.5 hours

**Problem:**
Archive logs every portfolio fetch with counts and balance. Greenfield has no post-fetch logging.

**Implementation Steps:**

1. **Add structured logging after fetch**
   ```python
   # brokers/adapters/dhan/portfolio.py
   def positions(self) -> list[Position]:
       data = self._client.get(ENDPOINTS["positions"])
       items = data if isinstance(data, list) else data.get("data", [])
       positions = [map_position(p) for p in items] if isinstance(items, list) else []
       logger.info("positions_fetched", extra={"count": len(positions)})
       return positions
   
   def holdings(self) -> list[Holding]:
       data = self._client.get(ENDPOINTS["holdings"])
       items = data if isinstance(data, list) else data.get("data", [])
       holdings = [map_holding(h) for h in items] if isinstance(items, list) else []
       logger.info("holdings_fetched", extra={"count": len(holdings)})
       return holdings
   
   def funds(self) -> Balance:
       # ... existing logic ...
       balance = map_balance(data)
       logger.info("balance_fetched", extra={"available_balance": str(balance.available_cash)})
       return balance
   ```

**Acceptance Criteria:**
- Every successful portfolio fetch logs count or balance
- Log level is INFO
- No sensitive data (tokens, client IDs) in log output

---

### T1.3: Fix Product Type Parsing

**Priority:** MEDIUM
**Gap Reference:** Evidence Matrix #9; Design Doc G-9
**Estimated Effort:** 0.25 hours

**Problem:**
Both archive and greenfield silently default to `INTRADAY` for unknown product types. This masks data quality issues.

**Implementation Steps:**

1. **Log warning on unknown product type**
   ```python
   # brokers/adapters/dhan/mapper.py — map_position()
   product_type = _PRODUCT_MAP.get(data.get("productType", "INTRADAY"))
   if product_type is None:
       logger.warning("unknown_product_type", extra={"product_type": data.get("productType")})
       product_type = ProductType.INTRADAY
   ```

2. **Update _PRODUCT_MAP to return None for unknown**
   ```python
   _PRODUCT_MAP = {
       "INTRADAY": ProductType.INTRADAY,
       "MARGIN": ProductType.DELIVERY,
       "CNC": ProductType.DELIVERY,
   }
   ```

**Acceptance Criteria:**
- Unknown product types log warning
- Unknown product types still default to INTRADAY (backward compatible)
- Unit test verifies warning logged

---

### T1.4: Add @runtime_checkable to PortfolioPort

**Priority:** LOW
**Gap Reference:** Evidence Matrix #44
**Estimated Effort:** 0.1 hours

**Problem:**
`HistoricalPort` and `MarketDataPort` are `@runtime_checkable`. `PortfolioPort` is not. Inconsistent.

**Implementation Steps:**

1. **Add @runtime_checkable decorator**
   ```python
   # brokers/ports/portfolio.py
   from typing import Protocol, runtime_checkable
   
   @runtime_checkable
   class PortfolioPort(Protocol):
       def positions(self) -> list[Position]: ...
       def holdings(self) -> list[Holding]: ...
       def funds(self) -> Balance: ...
       def trades(self) -> list[Trade]: ...
   ```

**Acceptance Criteria:**
- `PortfolioPort` is `@runtime_checkable`
- `isinstance(obj, PortfolioPort)` works

---

## 4. Layer 2 — Depends on Layer 1 (Missing Features)

### T2.1: Add Portfolio Caching

**Priority:** MEDIUM
**Gap Reference:** Design Doc G-11
**Estimated Effort:** 2 hours
**Depends on:** T1.1, T1.2

**Problem:**
`PortfolioService` has no caching. Every call hits the API. `MarketDataService` has TTL cache.

**Implementation Steps:**

1. **Add TTL cache to PortfolioService**
   ```python
   # brokers/services/portfolio_service.py
   import threading
   import time
   
   class PortfolioService:
       def __init__(self, portfolio: PortfolioPort, cache_ttl: float = 5.0):
           self._portfolio = portfolio
           self._ttl = cache_ttl
           self._cache: dict[str, tuple[float, object]] = {}
           self._lock = threading.Lock()
       
       def positions(self) -> list[Position]:
           return self._get_or_fetch("positions", self._portfolio.positions)
       
       def holdings(self) -> list[Holding]:
           return self._get_or_fetch("holdings", self._portfolio.holdings)
       
       def funds(self) -> Balance:
           return self._get_or_fetch("funds", self._portfolio.funds)
       
       def _get_or_fetch(self, key: str, fetcher):
           with self._lock:
               entry = self._cache.get(key)
               if entry and time.monotonic() - entry[0] < self._ttl:
                   return entry[1]
           result = fetcher()
           with self._lock:
               self._cache[key] = (time.monotonic(), result)
           return result
       
       def invalidate(self, key: str | None = None):
           with self._lock:
               if key:
                   self._cache.pop(key, None)
               else:
                   self._cache.clear()
   ```

2. **Add unit tests for cache hit/miss/expiry**

**Acceptance Criteria:**
- Repeated calls within TTL return cached data
- Expired entries trigger fresh fetch
- Different keys (positions, holdings, funds) cached independently
- Default TTL = 5s
- Invalidation API works

---

### T2.2: Add Request Timeout

**Priority:** MEDIUM
**Gap Reference:** Design Doc G-7
**Estimated Effort:** 1 hour
**Depends on:** T1.1

**Problem:**
No request timeout for portfolio reads. Thread can block indefinitely.

**Implementation Steps:**

1. **Add timeout parameter to PortfolioPort**
   ```python
   # brokers/ports/portfolio.py
   class PortfolioPort(Protocol):
       def positions(self, timeout: float | None = None) -> list[Position]: ...
       def holdings(self, timeout: float | None = None) -> list[Holding]: ...
       def funds(self, timeout: float | None = None) -> Balance: ...
       def trades(self, timeout: float | None = None) -> list[Trade]: ...
   ```

2. **Propagate timeout to HTTP client**
   ```python
   # brokers/adapters/dhan/portfolio.py
   def positions(self, timeout: float | None = None) -> list[Position]:
       data = self._client.get(ENDPOINTS["positions"], timeout=timeout)
       # ...
   ```

3. **Add unit test**

**Acceptance Criteria:**
- Timeout parameter accepted by all port methods
- Timeout propagated to HTTP client
- Unit test verifies timeout honored

---

### T2.3: Add Retry at Adapter Level

**Priority:** MEDIUM
**Gap Reference:** Design Doc G-8
**Estimated Effort:** 1 hour
**Depends on:** T1.1

**Problem:**
No retry at adapter level. Transient failures propagate to caller.

**Implementation Steps:**

1. **Wire infrastructure retry into portfolio adapters**
   ```python
   # brokers/adapters/dhan/portfolio.py
   from brokers.resilience.retry import retry
   
   class DhanPortfolio:
       @retry(max_attempts=3, retryable_exceptions=(NetworkError, RateLimitError))
       def positions(self) -> list[Position]:
           # ...
   ```

2. **Add unit test**

**Acceptance Criteria:**
- Portfolio reads retry on `NetworkError` and `RateLimitError`
- Max 3 attempts
- Exponential backoff
- Unit test verifies retry behavior

---

## 5. Layer 3 — Depends on Layer 2 (Enhancements & Polish)

### T3.1: Add Portfolio Metrics

**Priority:** LOW
**Gap Reference:** Design Doc G-14
**Estimated Effort:** 1 hour
**Depends on:** T2.1

**Implementation Steps:**

1. **Add metrics to PortfolioService**
   ```python
   # brokers/services/portfolio_service.py
   def positions(self) -> list[Position]:
       start = time.monotonic()
       result = self._get_or_fetch("positions", self._portfolio.positions)
       duration = time.monotonic() - start
       metrics.histogram("portfolio.positions.latency", duration)
       metrics.counter("portfolio.positions.calls").inc()
       return result
   ```

2. **Add unit test**

**Acceptance Criteria:**
- Fetch latency and call count observed
- Metrics exported via observability infrastructure

---

### T3.2: Add Circuit Breaker at Adapter Level

**Priority:** LOW
**Gap Reference:** Design Doc G-15
**Estimated Effort:** 1 hour
**Depends on:** T2.3

**Implementation Steps:**

1. **Wire infrastructure circuit breaker into portfolio adapters**
   ```python
   # brokers/adapters/dhan/portfolio.py
   from brokers.resilience.circuit_breaker import circuit_breaker
   
   class DhanPortfolio:
       @circuit_breaker(failure_threshold=5, recovery_timeout=60)
       def positions(self) -> list[Position]:
           # ...
   ```

2. **Add unit test**

**Acceptance Criteria:**
- Circuit breaker opens after 5 consecutive failures
- Requests blocked for 60s
- Half-open state allows test request
- Unit test verifies circuit breaker behavior

---

### T3.3: Add positions_to_dataframe Utility

**Priority:** LOW
**Gap Reference:** Evidence Matrix #6 (return type divergence)
**Estimated Effort:** 0.5 hours
**Depends on:** T0.2

**Implementation Steps:**

1. **Add utility function**
   ```python
   # brokers/utils/dataframe.py
   import pandas as pd
   from brokers.domain.entities import Position, Holding, Balance
   
   def positions_to_dataframe(positions: list[Position]) -> pd.DataFrame:
       if not positions:
           return pd.DataFrame(columns=["symbol", "exchange", "quantity", "average_price", "realized_pnl", "unrealized_pnl"])
       return pd.DataFrame([p.__dict__ for p in positions])
   
   def holdings_to_dataframe(holdings: list[Holding]) -> pd.DataFrame:
       if not holdings:
           return pd.DataFrame(columns=["symbol", "exchange", "quantity", "average_price", "isin", "t1_quantity", "ltp", "pnl", "available_quantity"])
       return pd.DataFrame([h.__dict__ for h in holdings])
   ```

2. **Add unit test**

**Acceptance Criteria:**
- Converts `list[Position]` and `list[Holding]` to DataFrame
- Empty list returns empty DataFrame with correct columns
- Optional dependency: pandas not required unless function is called

---

## 6. Parallelization Opportunities

### Fully Parallel (No Dependencies Between Tasks)

| Group | Tasks | Rationale |
|---|---|---|
| **Layer 0** | T0.1, T0.2, T0.3 | Independent: margin adapter, Holding entity, Balance entity |
| **Layer 1** | T1.1, T1.2, T1.3, T1.4 | T1.1 depends on T0.3; T1.2, T1.3, T1.4 are independent |
| **Layer 2** | T2.1, T2.2, T2.3 | All add independent features |
| **Layer 3** | T3.1, T3.2, T3.3 | Independent enhancements |

### Maximum Parallelism Schedule

```
Wave 1: T0.1 + T0.2 + T0.3           (3 tasks parallel)
Wave 2: T1.1 + T1.2 + T1.3 + T1.4    (4 tasks parallel)
Wave 3: T2.1 + T2.2 + T2.3           (3 tasks parallel)
Wave 4: T3.1 + T3.2 + T3.3           (3 tasks parallel)
```

**Theoretical minimum wall-clock:** Sum of longest task per wave ≈ 3h + 0.5h + 2h + 1h = **6.5 hours** (vs 12.85 hours sequential)

---

## 7. Critical Path Analysis

```
T0.1 (3h)                                                    = 3h
T0.2 (1h) → T3.3 (0.5h)                                    = 1.5h
T0.3 (0.5h) → T1.1 (0.5h) → T2.1 (2h) → T3.1 (1h)        = 4h
T0.3 (0.5h) → T1.1 (0.5h) → T2.2 (1h)                    = 2h
T0.3 (0.5h) → T1.1 (0.5h) → T2.3 (1h) → T3.2 (1h)        = 3h
T1.2 (0.5h) → T2.1 (2h)                                   = 2.5h
```

**Critical path:** T0.3 → T1.1 → T2.1 → T3.1 = **4 hours**

The critical path runs through the Balance entity extension → balance error handling → portfolio caching → portfolio metrics. Any delay on this path delays the entire phase.

---

## 8. Execution Summary

| Layer | Tasks | Total Effort | Parallel Min | Priority |
|---|---|---|---|---|
| Layer 0 | T0.1, T0.2, T0.3 | 4.5 hours | 3 hours | CRITICAL + HIGH + MEDIUM |
| Layer 1 | T1.1–T1.4 | 1.35 hours | 0.5 hours | HIGH + MEDIUM + LOW |
| Layer 2 | T2.1–T2.3 | 4 hours | 2 hours | MEDIUM |
| Layer 3 | T3.1–T3.3 | 2.5 hours | 1 hour | LOW |
| **Total** | **13 tasks** | **12.35 hours** | **~6.5 hours** | — |

### Risk-Adjusted Recommendation

1. **Must-fix before production:** Layer 0 (T0.1, T0.2, T0.3) — margin calculator and entity field gaps
2. **Should-fix for parity:** Layer 1 (T1.1–T1.4) — error handling and observability
3. **Nice-to-have:** Layer 2 (T2.1–T2.3) — caching, timeout, retry
4. **Deferred:** Layer 3 (T3.1–T3.3) — metrics and convenience

**Minimum viable phase:** Layer 0 + Layer 1 = **5.85 hours** achieves margin calculator, entity completeness, and error handling.

---

*End of implementation_tasks.md*
