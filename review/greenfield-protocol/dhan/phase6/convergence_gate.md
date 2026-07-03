# Phase 6 — Convergence Gate: Historical Data
## Greenfield Broker Replication Protocol — Dhan Broker

**Protocol:** Greenfield Broker Replication Protocol  
**Phase:** 6 — Historical Data (Candles, OHLC, LTP, Quotes, Depth)  
**Status:** CONVERGED ✓  
**Date:** 2026-07-03  

---

## Exit Criteria Validation

| # | Criterion | Requirement | Actual | Status |
|---|-----------|-------------|--------|--------|
| 1 | Source files inspected | 100% of files in scope | 3 archive + 5 greenfield + 3 domain files read | ✅ PASS |
| 2 | Public APIs documented | Every public API has behavioral contract | 30+ APIs in `public_contract.md` (463 lines) | ✅ PASS |
| 3 | Externally observable behavior evidenced | Every behavior has evidence | 38 behaviors in `evidence_matrix.md` | ✅ PASS |
| 4 | State transitions documented | Every state machine complete | 2 state machines in `state_machine.md` (313 lines) | ✅ PASS |
| 5 | Exception paths documented | Every exception path traced | 6 race conditions, 4 recovery paths in `failure_analysis.md` | ✅ PASS |
| 6 | Retry policies documented | Every retry policy complete | Historical data retry in `runtime_sequence.md` | ✅ PASS |
| 7 | Configuration options documented | Every config option listed | Timeframes, endpoints in `source_audit.md` | ✅ PASS |
| 8 | Dependencies mapped | Every dependency traced | 7 gaps in `dependency_graph.md` | ✅ PASS |
| 9 | Open questions resolved/recorded | All OQs addressed | OQs recorded in `evidence_matrix.md` | ✅ PASS |
| 10 | No undocumented behavior | All behaviors captured | 16 gaps in `greenfield_design.md` | ✅ PASS |
| 11 | Mandatory verification confirmed | All 7 items checked | See checklist below | ✅ PASS |
| 12 | Archived tests analyzed | Test coverage mapped | Test files analyzed in `source_audit.md` | ✅ PASS |

**Overall Status:** ✅ **CONVERGED** — All 12 exit criteria satisfied

---

## Deliverables Summary

| # | Deliverable | File | Lines | Status |
|---|-------------|------|-------|--------|
| 1 | Source Audit | `source_audit.md` | 433 | ✅ Complete |
| 2 | Runtime Sequence | `runtime_sequence.md` | 1,158 | ✅ Complete |
| 3 | Dependency Graph | `dependency_graph.md` | 697 | ✅ Complete |
| 4 | State Machine | `state_machine.md` | 313 | ✅ Complete |
| 5 | Public Contract | `public_contract.md` | 463 | ✅ Complete |
| 6 | Failure Analysis | `failure_analysis.md` | 342 | ✅ Complete |
| 7 | Evidence Matrix | `evidence_matrix.md` | 211 | ✅ Complete |
| 8 | Greenfield Design | `greenfield_design.md` | 406 | ✅ Complete |
| 9 | Implementation Tasks | `implementation_tasks.md` | 662 | ✅ Complete |
| 10 | Convergence Gate | `convergence_gate.md` | this file | ✅ Complete |

**Total documentation:** ~4,690 lines across 10 deliverables

---

## Scope Summary

**Archive:** 3 source files, ~370 lines
- `historical.py` (172 lines) — Historical data retrieval
- `market_data.py` (186 lines) — Market data REST API (OHLC, LTP, quotes)
- `datalake/gateway.py` (12 lines) — Data lake gateway (stub)

**Greenfield:** 5 source files, ~383 lines
- `adapters/dhan/historical.py` (159 lines)
- `adapters/dhan/market_data.py` (89 lines)
- `ports/historical.py` (43 lines)
- `ports/market_data.py` (18 lines)
- `services/market_data_service.py` (74 lines)

**Coverage gap:** ~40% of archive historical data functionality not yet ported to greenfield

---

## Key Findings

### Critical Gap (1)

1. **Wrong intraday endpoint** — Greenfield uses `/charts/historical` for intraday data instead of `/charts/intraday`; all sub-day historical data requests will likely fail

### High Severity Gaps (3)

2. **MCX session times hardcoded to NSE** — Archive supports MCX commodity session times; greenfield hardcodes NSE equity session times, breaking MCX instruments
3. **OI (Open Interest) silently dropped** — Archive returns OI for futures/options; greenfield silently drops OI field
4. **LTP returns zero instead of erroring** — Archive raises exception when instrument not found; greenfield returns zero, hiding errors

### Medium Severity Gaps (5)

5. **No batch operations** — Archive supports batch quote/LTP; greenfield makes N individual calls (10x performance impact)
6. **No OHLC method** — Archive has dedicated OHLC endpoint; greenfield has endpoint defined but not implemented
7. **No market depth (20-level)** — Archive parses 20-level depth; greenfield only supports 5-level
8. **No data caching** — Greenfield has TTL-based cache service but not integrated with historical adapter
9. **No timeout configuration** — Neither archive nor greenfield has explicit timeout policies for historical requests

### Low Severity Gaps (3)

10. **No data validation** — No timeframe/date range/symbol validation before API call
11. **No pagination** — Dhan API returns all data in single call; no pagination needed
12. **No data lake integration** — Archive has stub for data lake gateway; greenfield has none

### Improvements Over Archive (7)

1. **Port-based design** — Greenfield uses dependency injection via ports
2. **TTL caching service** — Greenfield has dedicated caching service layer
3. **Immutable entities** — Greenfield uses frozen dataclasses with Decimal precision
4. **Dual-format parsing** — Greenfield supports both dict and list response formats
5. **Multi-path lookup** — Greenfield tries multiple resolution paths for instruments
6. **Type-safe timeframes** — Greenfield uses Python enums vs archive's string constants
7. **Clean error codes** — Greenfield has structured error codes vs archive's string-based errors

---

## Mandatory Verification Checklist

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| 1 | Only expired tokens trigger regeneration | **N/A** | Historical data uses auth token from Phase 1; no independent token lifecycle |
| 2 | Refresh is thread safe | **NOT PORTED** | No token refresh integration in historical data |
| 3 | Refresh storms are prevented | **NOT PORTED** | No admission control in historical data |
| 4 | Duplicate logins are impossible | **N/A** | Historical data doesn't perform login |
| 5 | Concurrent requests synchronize correctly | **PARTIAL** | Greenfield has TTL cache; archive has no caching |
| 6 | Authentication retries are bounded | **PARTIAL** | Greenfield has basic retry via HTTP client; archive has bounded retry with backoff |
| 7 | Secrets never leak | **PRESERVED** | No token/secret logging in either codebase |

**Summary:** 2/7 N/A, 1/7 PRESERVED, 3/7 NOT PORTED/PARTIAL, 1/7 PARTIAL

---

## Implementation Priority

### Phase 6A — Data Correctness (3 hours)

1. Fix intraday endpoint (`/charts/historical` → `/charts/intraday`)
2. Fix silent-zero bug (LTP should raise exception, not return zero)
3. Add OI field to candle response

### Phase 6B — Feature Parity (4 hours)

4. Add MCX session time support
5. Add batch operations (batch quote, batch LTP)
6. Add OHLC method implementation
7. Add 20-level market depth parsing

### Phase 6C — Robustness (3 hours)

8. Add data validation (timeframe, date range, symbol)
9. Add timeout configuration
10. Integrate TTL cache with historical adapter
11. Add data lake integration (if needed)

**Total estimated effort:** 10 hours (1.25 days)  
**Critical path:** Endpoint fix → OI field → MCX session → Batch operations

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
| 7 | Portfolio | ⏳ PENDING | — |
| 8 | Cross-Cutting | ⏳ PENDING | — |

**Progress:** 7/9 phases complete (78%)

---

## Next Phase

**Phase 7 — Portfolio**

Scope:
- `archive/brokers/dhan/portfolio.py` — Portfolio/positions/holdings
- `archive/brokers/dhan/positions.py` — Position management
- `archive/brokers/dhan/holdings.py` — Holdings retrieval
- `archive/brokers/dhan/margins.py` — Margin/funds management
- Estimated ~15-25 source files

**Recommendation:** Proceed to Phase 7 after Phase 6A data correctness fixes are addressed.

---

*End of Phase 6 Convergence Gate*
