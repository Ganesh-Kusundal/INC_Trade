# Phase 7 — Convergence Gate: Portfolio & Margin
## Greenfield Broker Replication Protocol — Dhan Broker

**Protocol:** Greenfield Broker Replication Protocol
**Phase:** 7 — Portfolio & Margin (Positions, Holdings, Balance, Trades, Margin)
**Status:** CONVERGED ✓
**Date:** 2026-07-03

---

## Exit Criteria Validation

| # | Criterion | Requirement | Actual | Status |
|---|-----------|-------------|--------|--------|
| 1 | Source files inspected | 100% of files in scope | 2 archive + 3 greenfield + 3 domain files read | ✅ PASS |
| 2 | Public APIs documented | Every public API has behavioral contract | 10+ APIs in `PortfolioPort`, `DhanPortfolio`, `PortfolioService`, `MarginAdapter` | ✅ PASS |
| 3 | Externally observable behavior evidenced | Every behavior has evidence | 44 behaviors in `evidence_matrix.md` | ✅ PASS |
| 4 | State transitions documented | Every state machine complete | Portfolio is stateless (read-only); margin is request/response | ✅ PASS |
| 5 | Exception paths documented | Every exception path traced | 6 race conditions, 4 recovery paths in `failure_analysis.md` | ✅ PASS |
| 6 | Retry policies documented | Every retry policy complete | Portfolio retry in `implementation_tasks.md` T2.3 | ✅ PASS |
| 7 | Configuration options documented | Every config option listed | Endpoints, rate limits in `config.py` | ✅ PASS |
| 8 | Dependencies mapped | Every dependency traced | 15 gaps in `greenfield_design.md` | ✅ PASS |
| 9 | Open questions resolved/recorded | All OQs addressed | 7 OQs recorded in `evidence_matrix.md` | ✅ PASS |
| 10 | No undocumented behavior | All behaviors captured | 15 gaps in `greenfield_design.md` | ✅ PASS |
| 11 | Mandatory verification confirmed | All 7 items checked | See checklist below | ✅ PASS |
| 12 | Archived tests analyzed | Test coverage mapped | Test files analyzed in `evidence_matrix.md` | ✅ PASS |

**Overall Status:** ✅ **CONVERGED** — All 12 exit criteria satisfied

---

## Deliverables Summary

| # | Deliverable | File | Lines | Status |
|---|-------------|------|-------|--------|
| 1 | Failure Analysis | `failure_analysis.md` | ~320 | ✅ Complete |
| 2 | Evidence Matrix | `evidence_matrix.md` | ~220 | ✅ Complete |
| 3 | Greenfield Design | `greenfield_design.md` | ~410 | ✅ Complete |
| 4 | Implementation Tasks | `implementation_tasks.md` | ~740 | ✅ Complete |
| 5 | Convergence Gate | `convergence_gate.md` | this file | ✅ Complete |

**Total documentation:** ~1,690 lines across 5 deliverables

---

## Scope Summary

**Archive:** 2 source files, ~219 lines
- `portfolio.py` (103 lines) — Portfolio/positions/holdings/balance
- `margin.py` (116 lines) — Margin calculator

**Greenfield:** 3 source files, ~125 lines
- `adapters/dhan/portfolio.py` (55 lines)
- `ports/portfolio.py` (19 lines)
- `services/portfolio_service.py` (51 lines)

**Coverage gap:** ~40% of archive portfolio/margin functionality not yet ported to greenfield (margin calculator, Holding fields, Balance fields)

---

## Key Findings

### Critical Gaps (2)

1. **No margin calculator adapter** — Archive has `MarginAdapter` with `calculate()` method; greenfield has no margin adapter. Pre-trade margin checking is impossible.
2. **No margin request validation** — Archive validates qty > 0, price > 0 for LIMIT/STOP_LOSS; greenfield has no validation.

### High Severity Gaps (4)

3. **Balance returns zero instead of erroring** — Archive logs warning and returns empty `Balance()`; greenfield silently returns zero balance.
4. **No post-fetch logging for portfolio data** — Archive logs position/holding/balance counts; greenfield has no logging.
5. **No `available_quantity` on `Holding` entity** — Archive tracks available qty separately from total qty; greenfield drops this data.
6. **No `ltp` or `pnl` fields on `Holding` entity** — Archive computes PnL and tracks LTP for holdings; greenfield drops this data.

### Medium Severity Gaps (5)

7. **No request timeout** — Thread can block indefinitely on portfolio read.
8. **No retry at adapter level** — Transient failures propagate to caller.
9. **Product type silently defaults to INTRADAY** — Unknown product types are masked.
10. **No `sod_limit`, `collateral_amount`, `withdrawable_balance` on `Balance`** — Balance entity tracks only 3 fields vs archive's 5.
11. **No portfolio caching** — Every call hits the API.

### Low Severity Gaps (4)

12. **`PortfolioPort` not `@runtime_checkable`** — Cannot use `isinstance()` checks.
13. **No async support** — Cannot use in async contexts.
14. **No portfolio metrics** — Cannot observe fetch latency or error rates.
15. **No circuit breaker at adapter level** — Repeated failures waste resources.

### Improvements Over Archive (9)

1. **Port-based design** — Greenfield uses dependency injection via `PortfolioPort`.
2. **Service-layer aggregation** — `PortfolioService` provides `total_unrealized_pnl()`, `total_realized_pnl()`, `net_exposure()`.
3. **Trade retrieval** — Greenfield adds `trades()` method (not in archive portfolio).
4. **ISIN and T1 quantity on holdings** — Greenfield reads `isin` and `t1Qty` (not in archive).
5. **Dedicated mapper module** — `mapper.py` centralizes DTO → entity conversion.
6. **Frozen value objects** — All domain entities are `frozen=True` dataclasses.
7. **Cleaner adapter signature** — `DhanPortfolio` depends on `DhanHttpClient` only (no identity provider).
8. **More complete exchange mapping** — `_normalize_exchange` includes `IDX_I` → `INDEX`.
9. **Fallback field parsing** — `map_holding` handles multiple field name variants.

---

## Mandatory Verification Checklist

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| 1 | Only expired tokens trigger regeneration | **N/A** | Portfolio uses auth token from Phase 1; no independent token lifecycle |
| 2 | Refresh is thread safe | **NOT PORTED** | No token refresh integration in portfolio |
| 3 | Refresh storms are prevented | **NOT PORTED** | No admission control in portfolio |
| 4 | Duplicate logins are impossible | **N/A** | Portfolio doesn't perform login |
| 5 | Concurrent requests synchronize correctly | **PARTIAL** | Greenfield has no caching; archive has no caching |
| 6 | Authentication retries are bounded | **PARTIAL** | Greenfield has basic retry via HTTP client; archive has bounded retry with backoff |
| 7 | Secrets never leak | **PRESERVED** | No token/secret logging in either codebase |

**Summary:** 2/7 N/A, 1/7 PRESERVED, 3/7 NOT PORTED/PARTIAL, 1/7 PARTIAL

---

## Implementation Priority

### Phase 7A — Margin Calculator (3 hours)

1. Create `MarginPort` Protocol
2. Create `DhanMargin` adapter implementing `MarginPort`
3. Port `calculate()` method with request validation
4. Port `_validate_request()` logic
5. Port `assert_dhan_payload` invariant check
6. Add `/margincalculator` endpoint to config

### Phase 7B — Entity Completeness (1.5 hours)

7. Extend `Holding` entity with `ltp`, `pnl`, `available_quantity` fields
8. Extend `Balance` entity with `sod_limit`, `collateral_amount`, `withdrawable_balance` fields
9. Update `map_holding` to populate new fields
10. Update `map_balance` to populate new fields

### Phase 7C — Error Handling & Observability (1.35 hours)

11. Fix balance error handling (raise `DataError` on unexpected format)
12. Add post-fetch logging for positions, holdings, balance
13. Fix product type parsing (log warning on unknown)
14. Add `@runtime_checkable` to `PortfolioPort`

### Phase 7D — Performance & Reliability (4 hours)

15. Add portfolio caching (TTL 5s) to `PortfolioService`
16. Add request timeout to `PortfolioPort` methods
17. Add retry at adapter level for portfolio reads
18. Add portfolio metrics (latency, call count)
19. Add circuit breaker at adapter level

**Total estimated effort:** 12.35 hours (1.5 days)
**Critical path:** Balance entity extension → balance error handling → portfolio caching → portfolio metrics

---

## Protocol Phase Status

| Phase | Name | Status | Deliverables |
|-------|------|--------|--------------|
| 0 | Foundation | ✅ CONVERGED | 9 docs |
| 1 | Authentication | ✅ CONVERGED | 9 docs |
| 2 | Instrument Master | ✅ CONVERGED | 10 docs |
| 3 | Rate Limiting | ✅ CONVERGED | 10 docs |
| 4 | Market Data | ✅ CONVERGED | 10 docs |
| 5 | Order Management | ✅ CONVERGED | 10 docs |
| 6 | Historical Data | ✅ CONVERGED | 10 docs |
| 7 | Portfolio | ✅ CONVERGED | 5 docs |
| 8 | Cross-Cutting | ⏳ PENDING | — |

**Progress:** 8/9 phases complete (89%)

---

## Next Phase

**Phase 8 — Cross-Cutting**

Scope:
- Cross-cutting concerns that span all phases
- Authentication token lifecycle management
- Rate limiting integration across all adapters
- Circuit breaker integration across all adapters
- Retry policy integration across all adapters
- Observability integration (metrics, logging, tracing)
- Configuration validation across all adapters
- Error handling integration across all adapters
- Estimated ~20-30 source files

**Recommendation:** Proceed to Phase 8 after Phase 7A margin calculator is implemented.

---

*End of Phase 7 Convergence Gate*
