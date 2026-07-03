# Brokers Codebase — Deep Architectural Audit

**Date:** 2026-07-03  
**Scope:** `/Users/apple/Downloads/INC_Trade/brokers` (modern greenfield tree)  
**Refactors applied this session:** REF-1 (instrument key), REF-2 (typed idempotency), test naming fixes

---

## PHASE 1 — Codebase Mapping

### 1.1 Top-level packages and responsibilities

| Package | Responsibility |
|---------|----------------|
| `brokers/adapters/` | Broker-specific I/O: HTTP, WS, mapping, gateway composition |
| `brokers/adapters/base_streaming.py` | Shared WebSocket lifecycle for all brokers |
| `brokers/adapters/dhan/` | Dhan broker port implementations + depth feeds |
| `brokers/adapters/upstox/` | Upstox broker port implementations + protobuf WS |
| `brokers/config/` | Cross-broker constants: endpoints, indices, env |
| `brokers/core/` | Shared runtime utilities (idempotency, etc.) |
| `brokers/domain/` | Frozen entities, enums, exceptions (broker-agnostic) |
| `brokers/infrastructure/` | Cross-cutting runtime: credentials, JWT, lifecycle, WS pool |
| `brokers/ports/` | Protocol interfaces (`StreamingPort`, `InstrumentInfo`, …) |
| `brokers/resilience/` | Shared HTTP resilience: rate limit, circuit breaker, retry |
| `brokers/utils/` | Price/format helpers |
| `brokers/scripts/` | Operational tooling (parity compare, test inventory) |
| `brokers/tests/` | Unit + integration tests |

**Intentionally removed (not retroduced):** `brokers/infrastructure/resilience/` — consolidated into `brokers/resilience/`.

### 1.2 Dependency graph (import direction)

```
domain/          ← (nothing in brokers imports outward)
    ↑
ports/           ← domain
    ↑
config/          ← (standalone URLs, indices)
    ↑
resilience/      ← domain.exceptions
core/            ← stdlib + domain (typed_idempotency)
infrastructure/  ← domain, stdlib
    ↑
adapters/{dhan,upstox}/  ← all above + broker-local modules
    ↑
tests/           ← adapters (allowed)
```

**Gateway composition pattern (both brokers):**

```
UpstoxGateway / DhanGateway
  → auth, http, instruments, orders, market_data, portfolio, streaming, …
  → wires token_refresh_fn into http
  → wires instruments into market_data, orders, streaming (Upstox)
```

### 1.3 Shared vocabulary inventory

| Symbol / concept | Canonical location | Duplicate / drift locations |
|------------------|-------------------|---------------------------|
| Index symbols (NIFTY, SENSEX) | `brokers/config/indices.py` | Was duplicated in 5 Upstox `_instrument_key` helpers — **fixed → `instrument_key.py`** |
| Upstox REST URLs (typed) | `brokers/config/endpoints.py` → `Upstox` | `adapters/upstox/config.py` → `ENDPOINTS` dict (parallel) |
| Dhan REST URLs | `adapters/dhan/config.py` → `ENDPOINTS` | `brokers/config/endpoints.py` (partial) |
| Exchange→segment (Upstox) | `adapters/upstox/config.py` → `EXCHANGE_TO_SEGMENT` | Used only via `instrument_key.py` + mapper now |
| Order enums | `brokers/domain/enums.py` | Mapped in each `mapper.py` |
| Price decimals | `brokers/utils/price.py` | Some WS ticks still use `Decimal(str(...))` inline |
| Idempotency (order result cache) | **`brokers/core/typed_idempotency.py`** (new) | Was `upstox/idempotency.py` + `dhan/idempotency.py` — **merged** |
| Idempotency (filesystem gate) | `brokers/core/idempotency.py` | Different semantics (check_and_set bool) — **not merged** |
| HTTP resilience | `brokers/resilience/http_client.py` | Both brokers extend `BaseResilientHttpClient` ✓ |
| WS subscribe encoding | `adapters/upstox/streaming.py` | Binary opcode + empty guid (protocol-specific) |

---

## PHASE 2 — Shotgun Surgery Detection

Findings ordered by **blast radius** (highest first).

---

### [SMELL-1] Duplicated logic — instrument key resolution (Upstox)

**Pattern:** B  
**Files (before fix):**
- `brokers/adapters/upstox/market_data.py`
- `brokers/adapters/upstox/orders.py`
- `brokers/adapters/upstox/historical.py`
- `brokers/adapters/upstox/streaming.py`
- `brokers/adapters/upstox/options.py`
- `brokers/adapters/upstox/instruments.py`

**Symbol:** `index_upstox_key` + `EXCHANGE_TO_SEGMENT` + `f"{segment}|{symbol}"`  
**Blast radius:** 6 files per key-resolution rule change  
**Impact:** HIGH  
**Status:** ✅ **REMEDIATED** → `brokers/adapters/upstox/instrument_key.py`

---

### [SMELL-2] Duplicated logic — typed order idempotency caches

**Pattern:** B  
**Files (before fix):**
- `brokers/adapters/upstox/idempotency.py`
- `brokers/adapters/dhan/idempotency.py`

**Symbol:** `InMemoryIdempotencyCache` / `DhanIdempotencyCache` (near-identical Generic caches)  
**Blast radius:** 2 brokers + tests  
**Impact:** HIGH  
**Status:** ✅ **REMEDIATED** → `brokers/core/typed_idempotency.py` (aliases kept)

---

### [SMELL-3] Scattered constants — dual Upstox URL sources

**Pattern:** A  
**Files:**
- `brokers/config/endpoints.py` (`Upstox.production()`, method per endpoint)
- `brokers/adapters/upstox/config.py` (`ENDPOINTS` dict, `V2_BASE`, `HFT_BASE`)

**Symbol:** e.g. LTP URL, trades URL, place order URL  
**Blast radius:** 8+ adapter files if Upstox changes host routing  
**Impact:** HIGH  
**Evidence:** `portfolio.py` uses `ENDPOINTS["trades"]`; `extended.py`/`gtt.py` use `Upstox` class; `news.py` uses `ENDPOINTS`.

---

### [SMELL-4] Fragmented feature ownership — Upstox auth

**Pattern:** E  
**Files:** `brokers/adapters/upstox/auth/*` (12 modules, ~2.4k LOC)  
**Symbol:** Token lifecycle (TOTP, OAuth, PKCE, holders, scheduler, redirect)  
**Blast radius:** 12 files for any auth policy change  
**Impact:** HIGH  
**Note:** Retroduced from archive; overlaps `brokers/resilience/token_manager.py` + `token_scheduler.py`.

---

### [SMELL-5] Parallel inheritance — broker gateway + compat shim asymmetry

**Pattern:** F  
**Files:**
- `brokers/adapters/dhan/compat_gateway.py` (archive flat API shim)
- `brokers/adapters/upstox/gateway.py` (ports only, no compat)

**Symbol:** `get_orderbook` / `trades` / flat method names  
**Blast radius:** 2 gateway surfaces; legacy callers break on Upstox  
**Impact:** HIGH for migration

---

### [SMELL-6] Inconsistent abstraction levels — tick shape

**Pattern:** G  
**Files:**
- `brokers/adapters/upstox/streaming.py` → `on_tick(dict)`
- `brokers/adapters/base_streaming.py` → `subscribe_quotes` builds `Quote`
- Archive had `TickTranslatorAdapter` → canonical `Quote`

**Symbol:** `ltp` in dict vs `Quote.ltp`  
**Blast radius:** All WS consumers  
**Impact:** MEDIUM

---

### [SMELL-7] Cross-module state mutation — private `_loaded` access

**Pattern:** C  
**Files:** `market_data.py`, `orders.py` (was `instruments._loaded`)  
**Symbol:** `_loaded` private field read from outside  
**Blast radius:** 3 files  
**Impact:** MEDIUM  
**Status:** ✅ **REMEDIATED** → `UpstoxInstruments.is_loaded` property

---

### [SMELL-8] Duplicated logic — WebSocket reconnect boilerplate

**Pattern:** B  
**Files:**
- `brokers/adapters/base_streaming.py`
- `brokers/adapters/dhan/reconnecting_service.py`
- `brokers/adapters/dhan/depth_feed_base.py`
- `brokers/adapters/upstox/portfolio_stream.py` (inline `_run` loop)

**Symbol:** reconnect delay, `run_forever`, thread spawn  
**Blast radius:** 4 implementations  
**Impact:** MEDIUM

---

### [SMELL-9] Implicit coupling via naming — pytest module basename clash

**Pattern:** D  
**Files:**
- `tests/unit/adapters/dhan/test_orders_safety.py` vs `test_upstox_orders_safety.py`
- `tests/unit/adapters/dhan/test_instrument_loader.py` vs `test_upstox_instrument_loader.py`

**Symbol:** `test_orders_safety`, `test_instrument_loader` module names  
**Blast radius:** Full `brokers/tests/` collection  
**Impact:** MEDIUM  
**Status:** ✅ **REMEDIATED** (Upstox tests prefixed)

---

### [SMELL-10] Missing abstraction layer — feed response parsing

**Pattern:** H  
**Files:**
- `brokers/adapters/upstox/market_data.py` → `_find_symbol_data`
- `brokers/adapters/upstox/mapper.py`

**Symbol:** `instrument_key` vs `:` vs `instrument_token` response keys  
**Blast radius:** 2 files + batch endpoints  
**Impact:** MEDIUM

---

### [SMELL-11] Scattered constants — rate limits

**Pattern:** A  
**Files:**
- `brokers/adapters/upstox/config.py` → `RATE_LIMITS`
- `brokers/adapters/dhan/config.py` → rate limit tables
- `brokers/resilience/http_client.py` → consumes per-broker dict

**Blast radius:** 2 configs + http clients  
**Impact:** LOW

---

### [SMELL-12] Fragmented feature ownership — Dhan depth feeds

**Pattern:** E  
**Files:** `depth20.py`, `depth200.py`, `depth_feed_base.py`, `subscription_engine.py`, `connection_admission.py`, `connection_lifecycle.py`  
**Blast radius:** 6 files for one depth subscription  
**Impact:** MEDIUM (Dhan-specific, not Upstox)

---

### [SMELL-13] Three idempotency semantics (conceptual split)

**Pattern:** B + G  
**Files:**
- `brokers/core/idempotency.py` (bool gate + filesystem)
- `brokers/core/typed_idempotency.py` (correlation → OrderResponse)
- Broker order adapters

**Impact:** MEDIUM — developers must pick correct cache  
**Note:** Intentionally different use cases; needs naming clarity in docs.

---

## PHASE 3 — Root Cause Classification

| Root cause | Smells |
|------------|--------|
| **1. Missing shared vocabulary** | SMELL-1, SMELL-3, SMELL-11 |
| **2. Missing service/use-case layer** | SMELL-4, SMELL-12 (auth/depth logic in I/O modules) |
| **3. Missing domain model** | SMELL-6 (raw dict ticks) |
| **4. Boundary violations** | SMELL-7 (was `_loaded`), SMELL-4 (auth not using shared resilience token layer) |
| **5. Premature file splitting** | SMELL-4 (upstox auth), SMELL-12 (dhan depth), thin `news.py`/`metrics.py` |
| **6. Inconsistent standards** | SMELL-3 (dual URL sources), SMELL-5 (compat asymmetry), SMELL-9 (test naming) |

---

## PHASE 4 — Refactoring Plan

### REF-1 — Centralize Upstox instrument key resolution ✅ DONE

| Field | Value |
|-------|-------|
| **Root cause** | 1, 5 |
| **Action** | Extract |
| **From** | 5 duplicate `_instrument_key` implementations |
| **To** | `brokers/adapters/upstox/instrument_key.py` |
| **Touches** | `instruments.py`, `market_data.py`, `orders.py`, `historical.py`, `streaming.py`, `options.py`, `gateway.py` |
| **Test strategy** | `pytest brokers/tests/unit/adapters/upstox/` + live quotes |
| **Sequencing** | None (foundational) |

---

### REF-2 — Unify typed order idempotency caches ✅ DONE

| Field | Value |
|-------|-------|
| **Root cause** | 1, 6 |
| **Action** | Merge |
| **From** | `upstox/idempotency.py`, `dhan/idempotency.py` |
| **To** | `brokers/core/typed_idempotency.py` |
| **Touches** | Both idempotency shims, order adapters, unit tests |
| **Test strategy** | `test_upstox_orders_safety`, `test_orders_safety` (dhan) |
| **Sequencing** | After REF-1 optional |

---

### REF-3 — Single Upstox URL source

| Field | Value |
|-------|-------|
| **Root cause** | 1, 6 |
| **Action** | Enforce boundary — deprecate `ENDPOINTS` dict |
| **From** | `adapters/upstox/config.py` → `ENDPOINTS` |
| **To** | `brokers/config/endpoints.py` → `Upstox` methods only; config keeps maps/rate limits |
| **Touches** | `portfolio.py`, `market_data.py`, `orders.py`, `news.py`, `http.py` |
| **Test strategy** | Contract tests comparing URL strings; mocked HTTP integration |
| **Sequencing** | After REF-1 |

---

### REF-4 — Collapse Upstox auth onto shared token infrastructure

| Field | Value |
|-------|-------|
| **Root cause** | 2, 4, 5 |
| **Action** | Merge + introduce abstraction |
| **From** | `adapters/upstox/auth/*` (holders, scheduler duplicate) |
| **To** | `brokers/resilience/token_manager.py` + thin `UpstoxAuth` facade |
| **Touches** | 12 auth files, `gateway.py`, TOTP tests |
| **Test strategy** | Existing auth unit suite + live TOTP bootstrap |
| **Sequencing** | After REF-3; highest risk — do incrementally |

---

### REF-5 — Upstox compat gateway (parity with Dhan)

| Field | Value |
|-------|-------|
| **Root cause** | 5, 6 |
| **Action** | Introduce abstraction |
| **From** | N/A |
| **To** | `brokers/adapters/upstox/compat_gateway.py` mirroring Dhan pattern |
| **Touches** | New file, `__init__.py`, legacy integration tests |
| **Test strategy** | Side-by-side with archive gateway method signatures |
| **Sequencing** | After REF-1, REF-3 |

---

### REF-6 — Tick → domain Quote at streaming boundary

| Field | Value |
|-------|-------|
| **Root cause** | 3, 6 |
| **Action** | Introduce abstraction |
| **From** | `streaming._parse_tick` dict |
| **To** | `brokers/adapters/upstox/tick_mapper.py` → `Quote` |
| **Touches** | `streaming.py`, WS parity tests |
| **Test strategy** | `test_ws_parity.py` + unit decoder tests |
| **Sequencing** | After REF-1 |

---

### REF-7 — Consolidate WS reconnect into base or shared mixin

| Field | Value |
|-------|-------|
| **Root cause** | 2, 5 |
| **Action** | Extract |
| **From** | `portfolio_stream._run`, dhan reconnecting_service |
| **To** | Extend `base_streaming.py` or `infrastructure/websocket_runner.py` |
| **Touches** | `portfolio_stream.py`, dhan depth feeds |
| **Test strategy** | WS integration tests, mock WebSocketApp |
| **Sequencing** | After REF-6 |

---

### REF-8 — Rename idempotency modules for clarity

| Field | Value |
|-------|-------|
| **Root cause** | 6 |
| **Action** | Rename |
| **From** | `core/idempotency.py` (bool gate), `core/typed_idempotency.py` |
| **To** | `correlation_gate.py` + `order_result_cache.py` |
| **Touches** | Imports across brokers |
| **Test strategy** | `tests/unit/test_idempotency.py` |
| **Sequencing** | Independent, low risk |

---

## PHASE 5 — Structural Recommendations

### 5.1 Proposed directory structure (target)

```
brokers/
  domain/              # Entities, enums, exceptions — no I/O
  ports/               # Protocols only
  config/
    endpoints.py       # ALL broker URL builders (single source)
    indices.py         # Index symbol vocabulary
  core/
    order_result_cache.py   # TypedIdempotencyCache (rename from REF-8)
    correlation_gate.py     # Filesystem idempotency gate
  resilience/          # HTTP client, CB, RL, shared token scheduler
  infrastructure/      # Credentials, lifecycle, jwt, ws pool
  adapters/
    base_streaming.py
    dhan/
      gateway.py       # Composer
      compat_gateway.py
      ...ports...
    upstox/
      gateway.py
      compat_gateway.py   # REF-5
      instrument_key.py   # ✅ exists
      tick_mapper.py      # REF-6
      auth/               # Thin facade only after REF-4
      ...ports...
  utils/
  tests/
```

### 5.2 Boundary rules

1. **`domain/`** never imports from `adapters/`, `infrastructure/`, or `resilience/`.
2. **`ports/`** may import `domain/` only.
3. **`config/`** is broker-agnostic; no adapter imports into config.
4. **`adapters/{broker}/`** may import `domain`, `ports`, `config`, `resilience`, `core`, `infrastructure`, `utils` — never sibling broker packages.
5. **Instrument key resolution:** all Upstox callers use `resolve_upstox_instrument_key()` — no inline `f"{segment}|{symbol}"`.
6. **URLs:** adapters call `brokers.config.endpoints` — no hardcoded `https://api.upstox.com` in port modules.
7. **Ticks:** WS adapters emit `Quote` at boundary, not raw dicts (after REF-6).
8. **Tests:** broker-specific test modules must be prefixed (`test_upstox_*`, `test_dhan_*`) when basename would collide.

### 5.3 Coding standards (checkable)

1. All money/price fields use `Decimal` via `brokers.utils.price.to_decimal` / `to_wire_float` — never bare `float` in order payloads.
2. All Upstox `instrument_key` values go through `instrument_key.resolve_upstox_instrument_key`.
3. WS subscribe/unsubscribe payloads are **binary UTF-8 JSON** (`OPCODE_BINARY`), `guid: ""`.
4. Authorized Upstox WS URLs must not add redundant `Authorization` headers.
5. HTTP 401/403 handlers call `try_refresh_on_401()` — never unconditional `force_refresh()`.
6. Private adapter state (`_loaded`) exposed only via `@property` — no cross-module `_field` access.
7. Order idempotency for placement uses `TypedIdempotencyCache` — not `IdempotencyCache` bool gate.
8. New broker endpoints added only to `brokers/config/endpoints.py`, then referenced from adapters.

### 5.4 Guardrails

| Guardrail | Purpose |
|-----------|---------|
| **pytest** `importlib` mode or prefixed test basenames | Prevent SMELL-9 collection clashes |
| **import-linter** contract: `adapters.upstox` ⊄ `adapters.dhan` | Broker isolation |
| **`__all__`** on `instrument_key.py`, `typed_idempotency.py` | Explicit public API |
| **ADR template** in `review/adr/` for new broker features | Prevent SMELL-12 depth-style sprawl |
| **CI gate:** `PRE_PROD_GATE=1` WS parity on market days | Catch protocol regressions |
| **Ruff rule** ban `api.upstox.com` string outside `config/` | Enforce REF-3 |

---

## Applied This Session

| Task | Result |
|------|--------|
| REF-1 instrument key | ✅ `instrument_key.py` |
| REF-2 idempotency | ✅ `core/order_result_cache.py` |
| REF-3 URL unification | ✅ `config/endpoints.py` + `urls.py`; removed `ENDPOINTS` dict |
| REF-4 auth resilience | ✅ `AuthPort.try_refresh_on_401` + `resilience_bridge.py` |
| REF-5 compat gateway | ✅ `compat_gateway.py` |
| REF-6 tick → Quote | ✅ `tick_mapper.py`; WS emits `Quote` |
| REF-7 WS reconnect | ✅ `infrastructure/websocket_runner.py`; portfolio stream uses it |
| REF-8 idempotency rename | ✅ `order_result_cache.py` + `correlation_gate.py` with shims |
| SMELL-7 `is_loaded` | ✅ public property |
| SMELL-9 test clashes | ✅ prefixed Upstox test modules |
| Tests | ✅ 771 passed full suite; 11 failures pre-existing (Dhan auth/MCX) |

---

## Verdict

The modern `brokers/` tree **does not** retroduce archive multiplexer/registry complexity. The highest remaining shotgun-surgery risks are:

1. **Dual Upstox URL sources** (REF-3)  
2. **Auth module sprawl** (REF-4)  
3. **Dhan-only depth feed fragmentation** (out of Upstox scope)

Foundational extractions (REF-1, REF-2) are complete and tested. Next highest ROI: **REF-3** (URL unification), then **REF-4** (auth collapse onto `brokers/resilience`).
