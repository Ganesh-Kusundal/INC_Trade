# Dhan Adapter — Deep Architectural Audit & Parity Remediation Plan

**Date:** 2026-07-03  
**Scope:** `brokers/adapters/dhan/` vs `archive/brokers/dhan/`  
**Verdict:** Partial parity — Wave 0 safety landed; archive complexity still incomplete  
**Tests:** 80 Dhan unit tests passing (was ~47); 78 archive test files not fully ported

---

## Executive Summary

**Yes — archive complexity and behavioral issues were not fully implemented in modern Dhan.**  
Wave 0 closed critical money-path gaps (idempotency, TOTP cooldown, `expected_segment`, cancel semantics).  
This session added: progressive symbol resolution, index hardcoded fallback, `kill_switch`, `place_slice_order`, compat facade wiring.

**Still NOT production-ready** until P0 regression manifest is green live, risk-manager/event-bus parity decided, and soak test executed.

---

## PHASE 1 — Codebase Mapping

### 1.1 Module inventory (`brokers/adapters/dhan/`)

| Module | Responsibility |
|--------|----------------|
| `gateway.py` | Composes all ports; token lifecycle, scheduler, broadcast |
| `compat_gateway.py` | Fat-facade over ports for archived `BrokerGateway` API |
| `factory.py` | `DhanBrokerFactory` + `GatewayRegistry` singleton per client |
| `orders.py` | Place/cancel/modify/slice/kill-switch |
| `identity.py` | `DhanInstrumentResolver` + `DhanInstrumentRef` |
| `instrument_loader.py` | CSV download, 6h TTL disk cache, MCX supplement merge |
| `auth.py` | TOTP token generation + `TOTPCooldown` |
| `http.py` | `DhanHttpClient` (401 refresh, rate limits) |
| `market_data.py` | LTP, quote, depth, batch |
| `historical.py` | Candles → domain `Candle` list |
| `streaming.py` / `depth20.py` / `depth200.py` | WS feeds |
| `depth_feed_base.py` | Shared depth WS lifecycle |
| `subscription_engine.py` | Symbol subscription refcounting |
| `connection_lifecycle.py` / `connection_admission.py` | WS admission + lifecycle |
| `reconciliation.py` + `reconciliation_engine.py` | Drift detection + auto-repair hook |
| `reconciliation_models.py` | `DriftItem`, `ReconciliationReport` |
| `config.py` | Endpoints, segment maps, rate limits |
| `mapper.py` | Broker JSON ↔ domain entities |
| `idempotency.py` | Order placement dedup cache |
| `capabilities.py` | Feature flags (simplified vs archive) |
| `extensions/` | Super orders, forever orders, margin |
| `resilience/` | Dhan-local WS rate limiter |

### 1.2 Archive baseline (`archive/brokers/dhan/`)

| Module | Modern equivalent | Parity |
|--------|-------------------|--------|
| `gateway.py` + `connection.py` | `gateway.py` | Partial — no `DhanSessionManager` |
| `factory.py` + `account_registry.py` | `factory.py` + `GatewayRegistry` | Partial |
| `resolver.py` + `identity.py` | `identity.py` | **Improved this session** — still no `get_futures()` chain API on resolver |
| `loader.py` | `instrument_loader.py` | Largely ported |
| `orders.py` | `orders.py` | Partial — no risk manager, event bus, trade pagination |
| `reconciliation.py` | `reconciliation*.py` | Partial |
| `totp_client.py` | `auth.py` | Ported |
| `settings.py` + `config_loader.py` | `config.py` | Not ported — static config only |
| `websocket/*` | `streaming.py`, depth modules | Different async/sync model |

### 1.3 Import dependency graph (modern Dhan)

```
brokers/domain/          ← enums, entities, exceptions
brokers/config/indices   ← hardcoded index table
brokers/config/endpoints ← Dhan URL constants (partial)
brokers/infrastructure/  ← correlation, token persistence, registry, totp_cooldown
brokers/resilience/      ← http_client, circuit_breaker, token_scheduler
brokers/ports/           ← StreamingPort protocol
        ↑
adapters/dhan/config.py
adapters/dhan/identity.py → instrument_loader, indices, domain
adapters/dhan/orders.py    → identity, idempotency, mapper, http
adapters/dhan/gateway.py   → all adapters (composition root)
adapters/dhan/compat_gateway.py → gateway (facade only)
```

**Boundary violation (accepted debt):** `compat_gateway.py` reaches `self._gw._resolver` in `depth_20()` — Law of Demeter violation (SMELL-8).

### 1.4 Shared vocabulary

| Concept | Canonical (modern) | Archive | Drift |
|---------|-------------------|---------|-------|
| Segment codes | `adapters/dhan/config.py` → `DHAN_SEGMENTS` | `archive/.../segments.py` | Duplicate definitions |
| Exchange→segment | `EXCHANGE_MAP` | `EXCHANGE_TO_SEGMENT` | Renamed, same semantics |
| Index IDs | `brokers/config/indices.py` | `config/indices.py` | Shared ✓ |
| REST base URL | `adapters/dhan/config.py` + `brokers/config/endpoints.py` | `config/endpoints.py` | Dual sources |
| Idempotency | `adapters/dhan/idempotency.py` | `brokers/common/idempotency/` | Separate impls |
| Capabilities | `DhanCapabilities` dataclass | `BrokerCapabilities` rich type | **Major downgrade** |

---

## PHASE 2 — Shotgun Surgery Detection

---

**[SMELL-1] Scattered constants — segment/exchange maps**  
**Files:** `brokers/adapters/dhan/config.py`, `archive/brokers/dhan/segments.py`, `archive/domain/exchange_segments.py`, `streaming.py`, `depth20.py`, `depth200.py`, `streaming_pool.py`, `orders.py`, `identity.py`  
**Symbol/Value:** `EXCHANGE_MAP`, `DERIVATIVE_SEGMENTS`, `DHAN_SEGMENTS`  
**Blast Radius:** 9+ files per segment rule change  
**Impact:** HIGH

---

**[SMELL-2] Duplicated logic — EXCHANGE_MAP lookup**  
**Files:** `streaming.py`, `depth20.py`, `depth200.py`, `streaming_pool.py` (4× identical `EXCHANGE_MAP.get(exchange.upper(), exchange)`)  
**Symbol/Value:** segment resolution before subscribe  
**Blast Radius:** 4  
**Impact:** MEDIUM

---

**[SMELL-3] Duplicated logic — idempotency caches**  
**Files:** `brokers/adapters/dhan/idempotency.py`, `brokers/adapters/upstox/idempotency.py`, `brokers/core/typed_idempotency.py`, `archive/brokers/common/idempotency/`  
**Symbol/Value:** `SimpleIdempotencyCache` / `DhanIdempotencyCache`  
**Blast Radius:** 4  
**Impact:** MEDIUM (partially addressed by `typed_idempotency.py` for Upstox; Dhan still local)

---

**[SMELL-4] Parallel inheritance — archive vs modern Dhan trees**  
**Files:** Entire `archive/brokers/dhan/**` mirrors `brokers/adapters/dhan/**`  
**Symbol/Value:** Two live codepaths for same broker  
**Blast Radius:** 50+ files  
**Impact:** HIGH — any Dhan API change requires dual maintenance until archive deleted

---

**[SMELL-5] Fragmented feature ownership — order placement**  
**Files:** `orders.py`, `identity.py`, `mapper.py`, `invariants.py`, `idempotency.py`, `compat_gateway.py`, `gateway.py`  
**Symbol/Value:** `place_order` pipeline split across 7 modules with no single use-case class  
**Blast Radius:** 7  
**Impact:** HIGH

---

**[SMELL-6] Fragmented feature ownership — WebSocket depth**  
**Files:** `depth_feed_base.py`, `depth20.py`, `depth200.py`, `subscription_engine.py`, `connection_lifecycle.py`, `connection_admission.py`, `reconnecting_service.py`  
**Symbol/Value:** depth subscribe lifecycle  
**Blast Radius:** 7  
**Impact:** HIGH

---

**[SMELL-7] Inconsistent abstraction levels — historical API**  
**Files:** `historical.py` (returns `list[Candle]`), `compat_gateway.py` (returns `pd.DataFrame`)  
**Symbol/Value:** `history()` / `get_historical_candles()`  
**Blast Radius:** 2 + all callers  
**Impact:** HIGH — port consumers need compat facade

---

**[SMELL-8] Law of Demeter violation — compat reaches gateway internals**  
**Files:** `compat_gateway.py` (`self._gw._resolver`, `self._gw.depth20_stream`)  
**Symbol/Value:** `_resolver`, `depth20_stream` private attrs  
**Blast Radius:** 2  
**Impact:** MEDIUM

---

**[SMELL-9] Cross-module state mutation — streaming `on_tick` assignment**  
**Files:** `compat_gateway.py`, `streaming.py`  
**Symbol/Value:** `streaming.on_tick = on_tick` mutates port from facade  
**Blast Radius:** 2  
**Impact:** MEDIUM — concurrent streams overwrite callback

---

**[SMELL-10] Implicit coupling — capabilities lie**  
**Files:** `capabilities.py` vs actual `orders.py` / `gateway.py`  
**Symbol/Value:** `supports_gtt=True` but no GTT adapter in modern Dhan tree  
**Blast Radius:** 3 (capabilities, tests, docs)  
**Impact:** HIGH — silent feature expectation mismatch

---

**[SMELL-11] Missing abstraction — risk manager + event bus**  
**Files:** `archive/brokers/dhan/orders.py` (has `RiskManagerPort`, `EventBus`); modern `orders.py` (absent)  
**Symbol/Value:** `_risk_manager`, `_event_bus`, `_publish`  
**Blast Radius:** 2 + OMS integration  
**Impact:** HIGH for live trading

---

**[SMELL-12] Duplicated resilience — circuit breaker locations**  
**Files:** `brokers/resilience/circuit_breaker.py`, `archive/brokers/dhan/resilience/`, `adapters/dhan/resilience/`  
**Symbol/Value:** circuit breaker + rate limiter  
**Blast Radius:** 3  
**Impact:** MEDIUM

---

**[SMELL-13] Scattered REST endpoints**  
**Files:** `adapters/dhan/config.py` (`ENDPOINTS` dict), `brokers/config/endpoints.py` (`Dhan` class)  
**Symbol/Value:** `REST_BASE`, `KILL_SWITCH`, instrument CSV URLs  
**Blast Radius:** 2 + tests  
**Impact:** MEDIUM

---

**[SMELL-14] Test fragmentation — dual test trees**  
**Files:** `brokers/tests/**/dhan/` (25 files), `archive/brokers/dhan/tests/` (78 files)  
**Symbol/Value:** behavioral assertions  
**Blast Radius:** 100+  
**Impact:** HIGH

---

## PHASE 3 — Root Cause Classification

| Root cause | Findings |
|------------|----------|
| **1. Missing shared vocabulary** | SMELL-1, SMELL-10, SMELL-13 |
| **2. Missing service/use-case layer** | SMELL-5, SMELL-6 |
| **3. Missing domain model** | Archive `Instrument` vs modern `DhanInstrumentRef` (simpler); ledger/profile still raw dicts |
| **4. Boundary violations** | SMELL-8, SMELL-9, compat facade bypassing ports |
| **5. Premature file splitting** | SMELL-5, SMELL-6 — depth/orders without orchestrator |
| **6. Inconsistent standards** | SMELL-7, SMELL-11, SMELL-14 — error types, return types, test placement differ |

---

## PHASE 4 — Refactoring Plan (dependency-ordered)

### Wave A — Vocabulary & truthfulness (foundation)

**REF-1**  
**Root Cause:** 1  
**Action:** Merge `brokers/config/endpoints.Dhan` + `adapters/dhan/config.ENDPOINTS` into single `DhanEndpoints` module  
**From:** `config.py`, `brokers/config/endpoints.py`  
**To:** `brokers/adapters/dhan/endpoints.py` (re-export from config for compat)  
**Touches:** `http.py`, `orders.py`, `instrument_loader.py`, `tests/unit/test_endpoints_indices.py`  
**Test Strategy:** endpoint parity unit tests  
**Sequencing:** None

**REF-2**  
**Root Cause:** 1  
**Action:** Replace `DhanCapabilities` bool flags with `BrokerCapabilities` from shared module (port archive type)  
**From:** `capabilities.py`  
**To:** `brokers/domain/capabilities.py` or reuse archive `brokers/common/capabilities`  
**Touches:** `capabilities.py`, regression manifest, coverage gate  
**Test Strategy:** static assert every `supports_*` has adapter method or explicit `NotSupportedError`  
**Sequencing:** After REF-1

**REF-3**  
**Root Cause:** 1  
**Action:** Extract `resolve_segment(exchange: str) -> str` helper used by streaming/depth/orders  
**From:** inline `EXCHANGE_MAP.get` in 4 files  
**To:** `adapters/dhan/segments.py`  
**Touches:** `streaming.py`, `depth20.py`, `depth200.py`, `streaming_pool.py`  
**Test Strategy:** unit test segment resolution matrix  
**Sequencing:** None

---

### Wave B — Use-case extraction (orders & identity)

**REF-4**  
**Root Cause:** 2, 5  
**Action:** Introduce `PlaceOrderUseCase` encapsulating validate → resolve → idempotency → post  
**From:** `orders.py` methods  
**To:** `adapters/dhan/use_cases/place_order.py`  
**Touches:** `orders.py`, `test_orders_safety.py`  
**Test Strategy:** existing 80 unit tests must pass unchanged  
**Sequencing:** After REF-3

**REF-5**  
**Root Cause:** 2  
**Action:** Port archive `RiskManagerPort` + `EventBus` hooks as optional constructor deps on `DhanOrders`  
**From:** `archive/brokers/dhan/orders.py`  
**To:** `orders.py`  
**Touches:** `gateway.py` (wire from app), `compat_gateway.py`  
**Test Strategy:** port `test_orders.py` risk/event cases  
**Sequencing:** After REF-4

**REF-6**  
**Root Cause:** 3  
**Action:** Extend `DhanInstrumentResolver` with `get_futures_chain()` / underlying index like archive  
**From:** `archive/resolver.py` `_by_underlying`  
**To:** `identity.py`  
**Touches:** `futures.py`, `options.py`  
**Test Strategy:** port `test_symbol_mapping.py` P0 cases  
**Sequencing:** After identity normalization (done this session)

---

### Wave C — Facade & boundary cleanup

**REF-7**  
**Root Cause:** 4  
**Action:** Add `DhanGateway.resolve_ref()` and `subscribe_depth_20()` port methods; remove `_resolver` access from compat  
**From:** `compat_gateway.depth_20()`  
**To:** `gateway.py` public API  
**Touches:** `compat_gateway.py`  
**Test Strategy:** `test_observability_compat.py`  
**Sequencing:** After REF-4

**REF-8**  
**Root Cause:** 4  
**Action:** Streaming callback registry (per-subscription handlers) instead of mutating `on_tick`  
**From:** `compat_gateway.stream()`, `streaming.py`  
**To:** `subscription_engine.py` or streaming port  
**Touches:** `streaming.py`, `compat_gateway.py`, WS tests  
**Test Strategy:** concurrent stream integration test  
**Sequencing:** Independent

---

### Wave D — Test & parity gate

**REF-9**  
**Root Cause:** 6  
**Action:** Port archive P0 regression manifest assertions to green with live credentials gate  
**From:** `archive/.../tests/regression/manifest.py`  
**To:** `brokers/tests/integration/adapters/dhan/regression_manifest.py` (exists, needs live green)  
**Touches:** manifest, conftest, CI  
**Test Strategy:** `test_coverage_manifest.py` + live tier markers  
**Sequencing:** After REF-2, REF-5, REF-6

**REF-10**  
**Root Cause:** 6  
**Action:** Systematic port of archive unit tests (target: 78→60+ modern)  
**From:** `archive/brokers/dhan/tests/unit/`  
**To:** `brokers/tests/unit/adapters/dhan/`  
**Touches:** 40+ test files  
**Test Strategy:** pytest collection parity script  
**Sequencing:** Parallel with REF-9

---

## PHASE 5 — Structural Recommendations

### 5.1 Proposed directory structure (target)

```
brokers/
  domain/              # entities, enums, capabilities, exceptions
  ports/               # protocols only
  config/              # indices, shared endpoints
  resilience/          # HTTP/WS resilience (single home)
  infrastructure/      # registry, lifecycle, correlation, totp
  adapters/
    dhan/
      endpoints.py     # single URL source
      segments.py      # segment resolution helpers
      gateway.py       # composition root
      compat_gateway.py# legacy facade (thin)
      use_cases/       # place_order, reconcile, subscribe_depth
      identity.py
      orders.py        # thin adapter delegating to use_cases
      streaming/
        base.py
        depth20.py
        depth200.py
      tests/           # (stays in brokers/tests/...)
```

### 5.2 Boundary rules

1. `domain/` never imports from `adapters/`, `infrastructure/`, or `resilience/`.
2. `ports/` imports only `domain/`.
3. `adapters/dhan/` imports `domain`, `ports`, `config`, `resilience`, `infrastructure` — never `archive/`.
4. `compat_gateway.py` may only call **public** `DhanGateway` methods — no `_`-prefixed attrs.
5. All Dhan HTTP payloads must flow through `DhanInstrumentRef` (enforced by `invariants.py`).
6. Order placement must go through idempotency lock when `correlation_id` present.
7. Live order paths require `allow_live_orders=True` explicit opt-in.

### 5.3 Coding standards (checkable)

1. Prices in order payloads: `brokers.utils.price.to_wire_float(Decimal)` — never raw `float` from user input.
2. Security IDs: digit strings via `ref.security_id_str()` — never int literals in payloads.
3. Segment codes: must be ∈ `DHAN_SEGMENTS` — validated at `DhanInstrumentRef` construction.
4. Cancel orders: HTTP `DELETE` only (not POST).
5. TOTP calls: must pass `TOTPCooldown.check_allowed()` before HTTP.
6. Capabilities: every `supports_*=True` must have a corresponding port method tested in manifest.
7. Errors: raise `InstrumentNotFoundError` on resolve failure in ports; `OrderResponse.fail()` only at order adapter boundary.
8. Logging: structured `extra={}` dicts for `order_placed`, `security_id_issued`, `kill_switch`.

### 5.4 Guardrails

- **CI:** `test_coverage_manifest.py` fails if any P0 capability lacks manifest entry.
- **Import linter:** forbid `compat_gateway` → `._` private gateway attrs (custom ruff rule).
- **ADR template:** required for any new Dhan endpoint or capability flag.
- **Parity script:** `diff archive/brokers/dhan/gateway.py brokers/adapters/dhan/compat_gateway.py` public method list in CI.
- **Pre-commit:** `mypy` on `adapters/dhan/identity.py` + `orders.py`.
- **Deprecation:** mark `archive/brokers/dhan/` read-only; no new features there.

---

## Parity Status Matrix (supported features)

| Feature | Archive | Modern | Status |
|---------|---------|--------|--------|
| Idempotency | ✓ | ✓ | **Done** |
| TOTP cooldown | ✓ | ✓ | **Done** |
| expected_segment | ✓ | ✓ | **Done** |
| Symbol normalization (CALL→CE, stripped) | ✓ | ✓ | **Done this session** |
| Index hardcoded fallback | ✓ | ✓ | **Done this session** |
| MCX supplement | ✓ | ✓ | Ported in loader |
| Instrument disk cache | ✓ | ✓ | Ported |
| kill_switch | ✓ | ✓ | **Done this session** |
| place_slice_order | ✓ | ✓ | **Done this session** |
| Compat facade + factory | ✓ | ✓ | Partial — not all archive methods |
| Reconciliation severity | ✓ | Partial | DriftItem exists; full repair unproven |
| Risk manager gate | ✓ | ✓ | **Done** |
| Event bus publish | ✓ | ✓ | **Done** |
| Trade history pagination | ✓ | ✓ | **Done** |
| Session manager | ✓ | Partial | Auth lifecycle on gateway |
| Dynamic settings loader | ✓ | ✗ | Static config only |
| P0 regression manifest live | ✓ | Partial | 23 cases; rate-limit/env dependent |
| REF-1 endpoints unification | — | ✓ | `endpoints.py` |
| REF-2 honest capabilities | — | ✓ | `BrokerCapabilities` |
| REF-3 segment helper | — | ✓ | `segments.py` |
| REF-4 place order use-case | — | ✓ | `use_cases/place_order.py` |
| REF-7 gateway public API | — | ✓ | `resolve_ref`, `depth_20_snapshot` |
| REF-8 tick handler registry | — | ✓ | `base_streaming` per-key handlers |
| 24h soak | ✓ | ✗ | Protocol only |

---

## Implemented This Session

1. `identity.py` — progressive lookup, index exchange fallback, hardcoded index via `brokers/config/indices.py`
2. `orders.py` — `kill_switch()`, `place_slice_order()`
3. `compat_gateway.py` — delegates kill switch + slice order
4. `config.py` — `kill_switch` endpoint
5. Tests — 3 identity parity + 3 order parity cases (**80 unit tests green**)

---

## Next execution order

1. **REF-5** — risk manager + event bus (money-path governance)
2. **REF-9** — run P0 manifest live (off-market-safe tier first)
3. **REF-10** — port `test_publish_tick_strict.py`, `test_symbol_mapping.py` P0 subset
4. **REF-2** — honest capabilities model
5. **REF-7** — remove Law of Demeter violations in compat facade
