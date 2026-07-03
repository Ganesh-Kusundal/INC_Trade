# Phase 4 — Convergence Gate: Market Data
## Greenfield Broker Replication Protocol — Dhan Broker

**Protocol:** Greenfield Broker Replication Protocol  
**Phase:** 4 — Market Data (WebSocket, Depth Feeds, Subscriptions, REST API)  
**Status:** CONVERGED ✓  
**Date:** 2026-07-03  

---

## Exit Criteria Validation

| # | Criterion | Requirement | Actual | Status |
|---|-----------|-------------|--------|--------|
| 1 | Source files inspected | 100% of files in scope | 16 archive + 5 greenfield files read | ✅ PASS |
| 2 | Public APIs documented | Every public API has behavioral contract | 60+ APIs in `public_contract.md` (1,440 lines) | ✅ PASS |
| 3 | Externally observable behavior evidenced | Every behavior has evidence | 44 behaviors in `evidence_matrix.md` | ✅ PASS |
| 4 | State transitions documented | Every state machine complete | 10 state machines in `state_machine.md` (715 lines) | ✅ PASS |
| 5 | Exception paths documented | Every exception path traced | 6 race conditions, 5 recovery paths in `failure_analysis.md` | ✅ PASS |
| 6 | Retry policies documented | Every retry policy complete | Reconnection backoff, polling retry in `runtime_sequence.md` | ✅ PASS |
| 7 | Configuration options documented | Every config option listed | WebSocket URLs, timeouts, limits in `source_audit.md` | ✅ PASS |
| 8 | Dependencies mapped | Every dependency traced | 10 critical missing dependencies in `dependency_graph.md` | ✅ PASS |
| 9 | Open questions resolved/recorded | All OQs addressed | OQs recorded in `evidence_matrix.md` | ✅ PASS |
| 10 | No undocumented behavior | All behaviors captured | 14 gaps in `greenfield_design.md` | ✅ PASS |
| 11 | Mandatory verification confirmed | All 7 items checked | See checklist below | ✅ PASS |
| 12 | Archived tests analyzed | Test coverage mapped | `test_connection_manager.py` analyzed | ✅ PASS |

**Overall Status:** ✅ **CONVERGED** — All 12 exit criteria satisfied

---

## Deliverables Summary

| # | Deliverable | File | Lines | Status |
|---|-------------|------|-------|--------|
| 1 | Source Audit | `source_audit.md` | 685 | ✅ Complete |
| 2 | Runtime Sequence | `runtime_sequence.md` | 1,101 | ✅ Complete |
| 3 | Dependency Graph | `dependency_graph.md` | 863 | ✅ Complete |
| 4 | State Machine | `state_machine.md` | 715 | ✅ Complete |
| 5 | Public Contract | `public_contract.md` | 1,440 | ✅ Complete |
| 6 | Failure Analysis | `failure_analysis.md` | 1,060 | ✅ Complete |
| 7 | Evidence Matrix | `evidence_matrix.md` | 207 | ✅ Complete |
| 8 | Greenfield Design | `greenfield_design.md` | 471 | ✅ Complete |
| 9 | Implementation Tasks | `implementation_tasks.md` | 656 | ✅ Complete |
| 10 | Convergence Gate | `convergence_gate.md` | this file | ✅ Complete |

**Total documentation:** ~7,200 lines across 10 deliverables

---

## Scope Summary

**Archive:** 16 source files, ~5,834 lines
- WebSocket: `depth_feed_base.py`, `market_feed.py`, `connection.py`, `connection_manager.py`, `order_stream.py`, `polling_feed.py`, `_helpers.py`
- Subscription: `subscription_engine.py`
- Depth feeds: `depth_20.py`, `depth_200.py`
- Connection management: `connection_lifecycle.py`, `connection_admission.py`, `reconnecting_service.py`
- Instrument resolution: `resolver.py`, `resolver_refresher.py`
- REST API: `market_data.py`

**Greenfield:** 5 source files, ~523 lines
- `market_data.py`, `streaming.py`, `depth20.py`, `depth200.py`, `order_stream.py`

**Coverage gap:** ~84% of archive market data functionality not yet ported to greenfield

---

## Key Findings

### Critical Gaps (8)

1. **No binary depth parsing** — Archive parses binary WebSocket packets for 20-level and 200-level depth; greenfield has placeholder only
2. **No event bus integration** — Archive dispatches depth updates via event bus; greenfield has no pub/sub
3. **No connection admission control** — Archive uses `fcntl` file locks + 429 cooldown to prevent connection storms; greenfield has none
4. **No depth cache** — Archive maintains in-memory depth cache per instrument; greenfield has none
5. **No subscription engine** — Archive manages subscribe/unsubscribe with pending/active/stale states; greenfield has none
6. **No reconnection with backfill** — Archive reconnects with staleness detection + backfill after gap; greenfield has basic reconnect only
7. **No polling feed fallback** — Archive falls back to REST polling when WebSocket unavailable; greenfield has none
8. **No resolver refresh** — Archive periodically refreshes instrument resolver (24h TTL); greenfield loads once

### High Severity Gaps (4)

9. **No order stream WebSocket** — Archive streams order updates via dedicated WebSocket; greenfield polls REST
10. **No connection pool (depth-200)** — Archive manages pool of 200-level depth connections (max 5); greenfield has none
11. **No strict-mode publishing** — Archive validates instrument exists before publishing depth; greenfield does not
12. **No trade detection** — Archive detects trades from depth changes (last trade price/quantity); greenfield does not

### Moderate Gaps (4)

13. **No correlation IDs** — Archive tags WebSocket messages with correlation IDs for tracing; greenfield does not
14. **No health check endpoints** — Archive exposes per-feed health status; greenfield has none
15. **No metrics collection** — Archive tracks message rates, latency, gap counts; greenfield has none
16. **No dead-reference cleanup** — Archive cleans up dead subscriber references; greenfield may leak memory

### Improvements Over Archive (4)

1. **Simplified dependencies** — Greenfield uses `websockets` library directly vs archive's Dhan SDK wrapper
2. **Unified base class** — Greenfield `StreamingBase` provides common interface for all streaming adapters
3. **Cleaner REST API** — Greenfield `market_data.py` has simpler method signatures
4. **Header-based auth** — Greenfield uses header-based authentication vs archive's query param approach

---

## Mandatory Verification Checklist

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| 1 | Only expired tokens trigger regeneration | **N/A** | Market data uses auth token from Phase 1; no independent token lifecycle |
| 2 | Refresh is thread safe | **NOT PORTED** | No token refresh integration in market data WebSocket |
| 3 | Refresh storms are prevented | **NOT PORTED** | No admission control in greenfield |
| 4 | Duplicate logins are impossible | **N/A** | Market data doesn't perform login |
| 5 | Concurrent requests synchronize correctly | **NOT PORTED** | No subscription synchronization in greenfield |
| 6 | Authentication retries are bounded | **PARTIAL** | Greenfield has basic reconnect; archive has bounded backoff + admission |
| 7 | Secrets never leak | **PRESERVED** | No token/secret logging in either codebase |

**Summary:** 2/7 N/A, 1/7 PRESERVED, 3/7 NOT PORTED, 1/7 PARTIAL

---

## Implementation Priority

### Phase 4A — Critical Foundation (2-3 days)

1. Binary depth parsing (20-level + 200-level)
2. Event bus integration for depth updates
3. Domain entities (DepthLevel, DepthSnapshot, Trade)
4. Depth cache per instrument

### Phase 4B — Reliability (2 days)

5. Connection admission control (fcntl lock + 429 cooldown)
6. Polling feed fallback when WebSocket unavailable
7. Resolver periodic refresh (24h TTL)
8. Subscription engine with pending/active/stale states

### Phase 4C — Robustness (2 days)

9. Strict-mode publishing (validate instrument exists)
10. Trade detection from depth changes
11. Reconnection with staleness detection + backfill
12. Connection pool for depth-200 (max 5 connections)

### Phase 4D — Observability (1 day)

13. Correlation IDs for WebSocket message tracing
14. Health check endpoints per feed
15. Metrics collection (message rates, latency, gap counts)
16. Dead-reference cleanup for subscribers

**Total estimated effort:** 7-8 days  
**Critical path:** Binary parsing → Event bus → Depth cache → Subscription engine

---

## Protocol Phase Status

| Phase | Name | Status | Deliverables |
|-------|------|--------|--------------|
| 0 | Foundation | ✅ CONVERGED | 9 docs |
| 1 | Authentication | ✅ CONVERGED | 9 docs |
| 2 | Instrument Master | ✅ CONVERGED | 10 docs |
| 3 | Rate Limiting | ✅ CONVERGED | 10 docs |
| 4 | Market Data | ✅ CONVERGED | 10 docs |
| 5 | Order Management | ⏳ PENDING | — |
| 6 | Historical Data | ⏳ PENDING | — |
| 7 | Portfolio | ⏳ PENDING | — |
| 8 | Cross-Cutting | ⏳ PENDING | — |

**Progress:** 5/9 phases complete (56%)

---

## Next Phase

**Phase 5 — Order Management**

Scope:
- `archive/brokers/dhan/orders.py` — Order placement, modification, cancellation
- `archive/brokers/dhan/super_orders.py` — Bracket/cover orders
- `archive/brokers/dhan/forever_orders.py` — GTT orders
- `archive/brokers/dhan/exit_all.py` — Exit all positions
- `archive/brokers/dhan/conditional_triggers.py` — GTT trigger management
- `archive/brokers/dhan/status_mapper.py` — Order status normalization
- `archive/brokers/dhan/invariants.py` — Payload identity assertions
- Estimated ~30-40 source files

**Recommendation:** Proceed to Phase 5 after Phase 4A critical gaps are addressed.

---

*End of Phase 4 Convergence Gate*
