# Phase 7 — Greenfield Design Document: Portfolio & Margin
## Greenfield Broker Replication Protocol — Dhan Broker

**Protocol:** Greenfield Broker Replication Protocol
**Phase:** 7 — Portfolio & Margin
**Date:** 2026-07-03
**Status:** Design Review

---

## 1. Architecture Overview

### 1.1 Archive Architecture (Flat Adapter)

```
archive/brokers/dhan/
├── portfolio.py (103 lines)
│   ├── PortfolioAdapter class
│   ├── get_positions() — inline parsing
│   ├── get_holdings() — inline parsing with PnL calculation
│   ├── get_balance() — inline parsing with typo handling
│   └── _parse_product() — ProductType coercion helper
│
├── margin.py (116 lines)
│   ├── MarginAdapter class
│   ├── calculate() — POST to /margincalculator
│   ├── _validate_request() — qty/price validation
│   └── assert_dhan_payload — invariant check
│
No service layer. No port abstraction. No caching.
```

**Characteristics:**
- Two monolithic adapter classes with all logic inline
- Returns domain objects (`Position`, `Holding`, `Balance`)
- Margin calculator includes request validation and invariant assertion
- Holdings PnL computed client-side from LTP/avg/qty
- Balance tracks 5 fields: available, sod_limit, collateral, utilized, withdrawable
- Identity provider used for instrument resolution

### 1.2 Greenfield Architecture (Layered with Ports)

```
brokers/
├── ports/
│   └── portfolio.py (19 lines) — PortfolioPort Protocol
│       ├── positions() → list[Position]
│       ├── holdings() → list[Holding]
│       ├── funds() → Balance
│       └── trades() → list[Trade]
│
├── adapters/dhan/
│   ├── portfolio.py (55 lines)
│   │   ├── DhanPortfolio class
│   │   ├── positions() — via map_position helper
│   │   ├── holdings() — via map_holding helper
│   │   ├── funds() — via map_balance helper
│   │   └── trades() — via map_trade helper
│   │
│   └── mapper.py (202 lines) — DTO → domain entity mapping
│       ├── map_position, map_holding, map_balance, map_trade
│       └── _normalize_exchange helper
│
├── services/
│   └── portfolio_service.py (51 lines)
│       ├── Pass-through to PortfolioPort
│       ├── total_unrealized_pnl() — aggregation
│       ├── total_realized_pnl() — aggregation
│       └── net_exposure() — aggregation
│
└── domain/
    └── entities.py
        ├── Position (frozen dataclass) — symbol, exchange, qty, avg_price, realized/unrealized PnL
        ├── Holding (frozen dataclass) — symbol, exchange, qty, avg_price, isin, t1_qty
        ├── Balance (frozen dataclass) — available_cash, utilized_margin, total_margin
        └── Trade (frozen dataclass) — trade_id, order_id, symbol, exchange, side, qty, price
```

**Characteristics:**
- Clean port → adapter → service layering
- Domain entities (frozen dataclasses) with zero external dependencies
- Dedicated mapper module for DTO → entity conversion
- Service layer adds PnL aggregation transparently
- Narrow port interface (ISP compliance)
- Adapter depends on HTTP client only (no identity provider)
- Trade retrieval added (not in archive portfolio)

---

## 2. Improvements Over Archive

### 2.1 Port Abstractions

**Archive:** No port/interface definitions. Callers depend on concrete `PortfolioAdapter` and `MarginAdapter` classes.

**Greenfield:** `PortfolioPort` Protocol with `positions()`, `holdings()`, `funds()`, `trades()`. Enables dependency inversion, testing with fakes, and multi-broker support.

**Impact:** Clean architecture dependency rule. Adapters are swappable.

### 2.2 Service-Layer Aggregation

**Archive:** No service layer. Callers must manually aggregate PnL across positions.

**Greenfield:** `PortfolioService` wraps `PortfolioPort` with `total_unrealized_pnl()`, `total_realized_pnl()`, `net_exposure()`. Provides high-level portfolio metrics.

**Impact:** Eliminates duplicated aggregation logic in strategy code. Single source of truth for portfolio metrics.

### 2.3 Trade Retrieval

**Archive:** `PortfolioAdapter` has no `trades()` method. Trade retrieval requires separate adapter or direct API call.

**Greenfield:** `DhanPortfolio.trades()` retrieves tradebook via `ENDPOINTS["tradebook"]`. `map_trade()` maps DTO to `Trade` entity.

**Impact:** Unified portfolio API includes trades. Strategies can access full portfolio state via single port.

### 2.4 ISIN and T1 Quantity on Holdings

**Archive:** Does not read `isin` or `t1Qty` from holdings response.

**Greenfield:** `map_holding()` reads `isin` and `t1Qty` fields. `Holding` entity includes `isin: str` and `t1_quantity: int`.

**Impact:** Enables delivery tracking (T1 quantity) and security identification (ISIN). Critical for settlement workflows.

### 2.5 Dedicated Mapper Module

**Archive:** Parsing logic embedded in adapter methods.

**Greenfield:** `mapper.py` centralizes all DTO → domain entity conversions (`map_position`, `map_holding`, `map_balance`, `map_trade`). Single place to update when Dhan API changes.

**Impact:** Separation of concerns. Adapter focuses on HTTP orchestration; mapper focuses on field mapping.

### 2.6 Frozen Value Objects

**Archive:** Returns domain objects that are mutable (standard dataclasses).

**Greenfield:** All domain entities are `frozen=True` dataclasses. Thread-safe by construction. No accidental mutation.

**Impact:** Safe to share across threads. No race conditions from mutation.

---

## 3. Dropped Behaviors (Gaps)

### 3.1 CRITICAL Severity

| Gap ID | Behavior | Archive Reference | Impact |
|---|---|---|---|
| G-1 | No margin calculator adapter | `archive/brokers/dhan/margin.py:17-101` | Pre-trade margin checking is impossible. Strategies cannot validate margin requirements before order submission. |
| G-2 | No margin request validation | `archive/brokers/dhan/margin.py:103-115` | Cannot validate margin requests (qty > 0, price > 0 for LIMIT/STOP_LOSS). Invalid requests hit the API. |

### 3.2 HIGH Severity

| Gap ID | Behavior | Archive Reference | Impact |
|---|---|---|---|
| G-3 | Balance returns zero instead of erroring | `archive/brokers/dhan/portfolio.py:82-84` | Silent zero masks data availability issues. Strategies may act on missing balance data without knowing. |
| G-4 | No post-fetch logging for portfolio data | `archive/brokers/dhan/portfolio.py:45,76,94` | Lost observability: cannot audit position/holding/balance counts or verify fetch success. |
| G-5 | No `available_quantity` on `Holding` entity | `archive/brokers/dhan/portfolio.py:68-69` | Cannot distinguish total quantity from available quantity. T+1 settlement tracking impossible. |
| G-6 | No `ltp` or `pnl` fields on `Holding` entity | `archive/brokers/dhan/portfolio.py:55-62` | Archive computes PnL and tracks LTP for holdings. Greenfield drops this data. |

### 3.3 MEDIUM Severity

| Gap ID | Behavior | Archive Reference | Impact |
|---|---|---|---|
| G-7 | No request timeout | N/A | Thread can block indefinitely on portfolio read |
| G-8 | No retry at adapter level | N/A | Transient failures propagate to caller |
| G-9 | Product type silently defaults to INTRADAY | `archive/brokers/dhan/portfolio.py:98-102` | Unknown product types are masked. Data quality issues hidden. |
| G-10 | No `sod_limit`, `collateral_amount`, `withdrawable_balance` on `Balance` | `archive/brokers/dhan/portfolio.py:89-92` | Balance entity tracks only 3 fields vs archive's 5. SOD limit, collateral, withdrawable balance lost. |
| G-11 | No portfolio caching | N/A | Every call hits the API. No TTL cache in `PortfolioService`. |

### 3.4 LOW Severity

| Gap ID | Behavior | Archive Reference | Impact |
|---|---|---|---|
| G-12 | `PortfolioPort` not `@runtime_checkable` | N/A | Cannot use `isinstance()` checks for port conformance |
| G-13 | No async support | N/A | Cannot use in async contexts |
| G-14 | No portfolio metrics | N/A | Cannot observe fetch latency or error rates |
| G-15 | No circuit breaker at adapter level | N/A | Repeated failures waste resources |

---

## 4. Key Architectural Decisions

### 4.1 Service Layer vs Direct Adapter Calls

**Decision:** Greenfield introduces `PortfolioService` between callers and `PortfolioPort`.

**Rationale:**
- Archive has no service layer — callers invoke adapter methods directly
- Service layer enables cross-cutting concerns (caching, logging, metrics) without polluting adapters
- Follows dependency inversion: callers depend on service, not adapter
- Aggregation methods (`total_unrealized_pnl`, `net_exposure`) belong in service layer

**Trade-off:**
- Adds indirection for simple pass-through cases
- `PortfolioService.positions()` just delegates to `self._portfolio.positions()` — no value-add
- **Recommendation:** Service should add caching, logging, or validation to justify its existence

### 4.2 Caching Strategy

**Decision:** No caching in `PortfolioService`.

**Analysis:**
- Archive has no caching — every call hits the API
- `MarketDataService` has TTL cache (1s default) for market data
- Portfolio data changes less frequently than market data (positions change on trade, not on tick)
- **Recommendation:** Add TTL cache (5-10s) for positions/holdings/funds to reduce API load

### 4.3 Margin Calculator Placement

**Decision:** Margin calculator is NOT PORTED to greenfield.

**Analysis:**
- Archive has `MarginAdapter` with `calculate()` method
- Margin calculation is critical for pre-trade risk checks
- No greenfield equivalent exists
- **Recommendation:** Port `MarginAdapter` to greenfield as `DhanMargin` implementing `MarginPort`

### 4.4 Holding Entity Field Set

**Decision:** Greenfield `Holding` entity includes `isin` and `t1_quantity` but not `ltp`, `pnl`, `available_quantity`.

**Analysis:**
- Archive reads `ltp`, computes `pnl`, reads `availableQty`
- Greenfield reads `isin`, `t1Qty` (not in archive)
- Different field sets serve different purposes:
  - Archive: PnL tracking and settlement availability
  - Greenfield: Security identification and delivery tracking
- **Recommendation:** Extend `Holding` entity to include both sets

### 4.5 Balance Entity Field Set

**Decision:** Greenfield `Balance` entity includes `available_cash`, `utilized_margin`, `total_margin`.

**Analysis:**
- Archive reads 5 fields: `availabelBalance`, `sodLimit`, `collateralAmount`, `utilizedAmount`, `withdrawableBalance`
- Greenfield reads 3 fields: `availabelBalance`, `utilizedMargin`, `totalMargin`
- Missing: `sod_limit`, `collateral_amount`, `withdrawable_balance`
- **Recommendation:** Extend `Balance` entity to include all 5 fields

### 4.6 Return Type: Domain Entities

**Decision:** Greenfield returns frozen dataclasses (`Position`, `Holding`, `Balance`, `Trade`).

**Rationale:**
- Decouples adapter layer from external dependencies
- Frozen dataclasses provide immutability and type safety
- Thread-safe by construction

**Trade-off:**
- Loss of mutability (cannot update fields in-place)
- **Recommendation:** Provide utility functions for common transformations (e.g., `positions_to_dataframe`)

---

## 5. Design Principles Applied

### 5.1 Ports and Adapters (Hexagonal Architecture)

- `PortfolioPort` defines inbound interface
- `DhanPortfolio` implements outbound adapter interface
- Domain entities (`Position`, `Holding`, `Balance`, `Trade`) are independent of both

### 5.2 Interface Segregation Principle (ISP)

- `PortfolioPort` is narrow: only `positions`, `holdings`, `funds`, `trades`
- Each port method is focused and minimal
- No margin calculation in portfolio port (separate concern)

### 5.3 Dependency Inversion

- Service layer depends on `PortfolioPort` (abstraction), not `DhanPortfolio` (concrete)
- Enables paper broker or test fake substitution

### 5.4 Single Responsibility

- Adapter handles HTTP orchestration
- Mapper handles DTO → entity conversion
- Service handles aggregation
- Domain entities handle data representation

### 5.5 Frozen Value Objects

- All domain entities are `frozen=True` dataclasses
- Thread-safe by construction
- No accidental mutation

---

## 6. Recommended Architecture for Greenfield Portfolio

### 6.1 Immediate Fixes (Pre-Production)

```
1. Port margin calculator adapter
   - Create DhanMargin class implementing MarginPort
   - Port calculate() method with request validation
   - Port _validate_request() logic
   - Port assert_dhan_payload invariant check

2. Extend Holding entity
   - Add ltp: Decimal = Decimal("0")
   - Add pnl: Decimal = Decimal("0")
   - Add available_quantity: int = 0

3. Extend Balance entity
   - Add sod_limit: Decimal = Decimal("0")
   - Add collateral_amount: Decimal = Decimal("0")
   - Add withdrawable_balance: Decimal = Decimal("0")

4. Fix balance error handling
   - Raise DataError when balance API returns unexpected format
   - Match archive's warning log behavior
```

### 6.2 Short-Term Enhancements

```
5. Add post-fetch logging
   - Log position count, holding count, balance after fetch
   - Match archive's structured logging

6. Add portfolio caching
   - Extend PortfolioService with TTL cache (5-10s)
   - Cache positions, holdings, funds separately
   - Add invalidation API

7. Fix product type parsing
   - Log warning on unknown product type
   - Do not silently default to INTRADAY

8. Add @runtime_checkable to PortfolioPort
   - Match HistoricalPort and MarketDataPort
```

### 6.3 Medium-Term Additions

```
9.  Add request timeout
    - Add timeout parameter to PortfolioPort methods
    - Propagate to HTTP client

10. Add retry at adapter level
    - Wire infrastructure retry into portfolio adapters
    - Idempotent retry for reads (positions, holdings, funds)

11. Add portfolio metrics
    - Observe fetch latency, error rates
    - Integrate with observability infrastructure

12. Add circuit breaker at adapter level
    - Block repeated failures
    - Prevent resource exhaustion
```

### 6.4 Target Architecture Diagram

```
                    ┌──────────────────┐
                    │  Strategy Code   │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼──────┐ ┌────▼─────┐ ┌──────▼────────┐
    │ PortfolioPort   │ │MarginPort│ │PortfolioService│
    │                 │ │          │ │  (cache+agg)   │
    └─────────┬──────┘ └────┬─────┘ └──────┬────────┘
              │              │              │
    ┌─────────▼──────┐ ┌────▼──────────────▼─────┐
    │DhanPortfolio    │ │    DhanMargin           │
    │ • positions     │ │ • calculate             │
    │ • holdings      │ │ • validate_request      │
    │ • funds         │ │ • assert_payload        │
    │ • trades        │ │                         │
    └─────────┬──────┘ └────┬─────────────────────┘
              │              │
    ┌─────────▼──────────────▼─────────────┐
    │         DhanHttpClient               │
    │  (rate limiting, circuit breaker)    │
    └──────────────────────────────────────┘
```

---

## 7. Summary

The greenfield portfolio implementation is a **structurally superior** but **behaviorally incomplete** port of the archive.

**Strengths:**
- Clean layered architecture with port abstractions
- Domain entities (frozen dataclasses) with zero external dependencies
- Service-layer aggregation (PnL, exposure)
- Trade retrieval added
- ISIN and T1 quantity on holdings
- Dedicated mapper module

**Weaknesses:**
- Margin calculator not ported (CRITICAL)
- Holding entity missing ltp, pnl, available_quantity (HIGH)
- Balance entity missing sod_limit, collateral_amount, withdrawable_balance (MEDIUM)
- No post-fetch observability
- No portfolio caching

**Overall parity:** ~60% of archive behavior preserved, ~20% improved, ~20% missing or degraded.

---

*End of greenfield_design.md*
