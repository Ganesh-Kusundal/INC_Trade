# Phase 8 — State Machines: Cross-Cutting Concerns

> **Greenfield Broker Replication Protocol — Dhan Adapter**
> Phase 8 documents every state machine governing cross-cutting lifecycle,
> identity, session, options, futures, reconciliation, and alert flows.

---

## Table of Contents

1. [Gateway Lifecycle State Machine](#1-gateway-lifecycle-state-machine)
2. [Factory Bootstrap State Machine](#2-factory-bootstrap-state-machine)
3. [Identity / Auth State Machine](#3-identity--auth-state-machine)
4. [Session State Machine](#4-session-state-machine)
5. [Token Broadcast State Machine](#5-token-broadcast-state-machine)
6. [Options Trading State Machine](#6-options-trading-state-machine)
7. [Futures Trading State Machine](#7-futures-trading-state-machine)
8. [Reconciliation State Machine](#8-reconciliation-state-machine)
9. [Alert State Machine](#9-alert-state-machine)
10. [Instrument Loader State Machine](#10-instrument-loader-state-machine)
11. [Configuration Loader State Machine](#11-configuration-loader-state-machine)
12. [Order Lifecycle State Machine (Domain)](#12-order-lifecycle-state-machine-domain)
13. [Greenfield vs Archive Comparison Summary](#13-greenfield-vs-archive-comparison-summary)

---

## 1. Gateway Lifecycle State Machine

### Archive (`BrokerGateway`)

The archive gateway has no explicit state enum; its lifecycle is implicit in
the `DhanConnection` object graph and the `close()` method.

```
                     ┌──────────────────────────────────────────────┐
                     │                                              │
  __init__           v                                              │
  ─────────► [INIT] ──── load_instruments() ──► [READY]            │
                │                                │                  │
                │ close()                        │ stream() /       │
                │ (noop if no WS)                │ place_order()    │
                v                                v                  │
             [CLOSED] ◄──── close() ────── [ACTIVE]                │
                                               │                    │
                                               │ close()            │
                                               v                    │
                                           [CLOSED] ────────────────┘
```

| State          | Entry Condition                                  | Allowed Transitions          |
|----------------|--------------------------------------------------|------------------------------|
| `INIT`         | `BrokerGateway(connection)` constructed           | → READY (load_instruments)   |
|                |                                                  | → CLOSED (close before load) |
| `READY`        | Instruments loaded, adapters wired                | → ACTIVE (first API call)    |
|                |                                                  | → CLOSED (close)             |
| `ACTIVE`       | At least one market-data or order call made       | → CLOSED (close)             |
| `CLOSED`       | `close()` invoked; HTTP pool + WS stopped         | *(terminal)*                 |

**Failure paths:**
- `load_instruments()` raises → stays in `INIT`, exception propagated.
- `close()` during `INIT` → transitions to `CLOSED` (safe no-op).
- Any API call after `CLOSED` → raises `ConnectionError` (archive does not guard this explicitly).

### Greenfield (`DhanGateway`)

The greenfield gateway adds explicit token-lifecycle tracking and scheduler management.

```
  __init__
  ─────────► [INIT]
                │
                │ auth.get_token() succeeds
                │ + adapters constructed
                │ + scheduler started (optional)
                │ + broadcast receivers registered
                v
             [READY] ──── first API/stream call ──► [ACTIVE]
                │                                      │
                │ close()                              │ close()
                v                                      v
             [CLOSED] ◄─────────────────────────────── [CLOSED]
```

| State      | Entry Condition                                     | Allowed Transitions       |
|------------|-----------------------------------------------------|---------------------------|
| `INIT`     | `DhanGateway(...)` entered                          | → READY (init completes)  |
| `READY`    | All adapters constructed, scheduler running          | → ACTIVE (first call)     |
|            |                                                     | → CLOSED (close)          |
| `ACTIVE`   | HTTP call or stream subscription made                | → CLOSED (close)          |
| `CLOSED`   | Scheduler stopped, streams stopped, HTTP closed      | *(terminal)*              |

**Greenfield additions:**
- `health()` method exposes `auth_valid`, `scheduler.health()`, `broadcast.token_refresh_metrics`.
- `close()` is idempotent: stops scheduler, all 4 stream types, then HTTP client.

**Failure paths:**
- `DhanAuth` init fails (no credentials) → `AuthenticationError` during `INIT`, no transition.
- Scheduler start fails → logged as warning, gateway still transitions to `READY`.

---

## 2. Factory Bootstrap State Machine

### Archive (`BrokerFactory`)

```
  create()
  ─────────► [START]
                │
                │ DhanSettingsLoader.from_env()
                v
             [SETTINGS_LOADED]
                │
                │ AccountConnectionRegistry.get_or_create()
                │   ├─ cache HIT  → return existing gateway
                │   └─ cache MISS → _build_gateway()
                v
             [BUILDING]
                │
                ├─ _create_auth() ──────────► token acquired
                ├─ _create_http_client() ───► resilience wired
                ├─ _create_connection_and_gateway() → DhanConnection + BrokerGateway
                ├─ _wire_websocket_services() → market_feed + order_stream created
                ├─ _setup_token_refresh_scheduler() → scheduler registered
                └─ register_broker_health_check()
                v
             [BUILT] ──── return gateway ──► [DONE]
```

| State              | Description                                    | Failure Transition           |
|--------------------|------------------------------------------------|------------------------------|
| `START`            | `create()` called                              | → FAILED (settings error)    |
| `SETTINGS_LOADED`  | `DhanConnectionSettings` frozen dataclass      | → FAILED (auth error)        |
| `BUILDING`         | Wiring auth → HTTP → connection → WS → scheduler | → FAILED (any step error)  |
| `BUILT`            | Gateway fully wired, returned to caller        | *(terminal success)*         |
| `FAILED`           | Any bootstrap step raised                      | *(terminal failure)*         |

**Key failure paths:**
- Missing `DHAN_CLIENT_ID` → `ValueError` at `SETTINGS_LOADED`.
- TOTP generation fails + no cached token → `ConfigurationError` at `BUILDING`.
- `AccountConnectionRegistry` ensures only one gateway per `(broker_id, account_id)`.

### Greenfield

The greenfield has no separate factory class. `DhanGateway.__init__()` performs
all bootstrap inline. The state machine is collapsed into the gateway lifecycle
(Section 1). Token persistence, broadcast registration, and scheduler setup all
happen within `__init__`.

**Key difference:** Archive uses a multi-step factory with registry-based
singleton enforcement. Greenfield inlines everything into the gateway constructor,
relying on the caller to manage singleton semantics.

---

## 3. Identity / Auth State Machine

### Archive (`AuthManager` + `DhanTotpClient`)

```
                     ┌──────────────────────────────────────────────────────┐
                     │                                                      │
  AuthManager()      v                                                      │
  ─────────► [UNAUTHENTICATED] ──── acquire() ──► [AUTHENTICATED]          │
                     │                                   │                  │
                     │ acquire() fails                   │ token expires    │
                     v                                   v                  │
                  [FAILED] ◄─────────────────── [TOKEN_EXPIRED]            │
                                                    │                       │
                                                    │ force_refresh()       │
                                                    v                       │
                                                [REFRESHING] ──────────────┘
                                                    │
                                                    │ refresh succeeds
                                                    v
                                               [AUTHENTICATED]
```

| State              | Description                                  | Transitions                          |
|--------------------|----------------------------------------------|--------------------------------------|
| `UNAUTHENTICATED`  | No token acquired yet                        | → AUTHENTICATED (acquire success)    |
|                    |                                              | → FAILED (acquire failure)           |
| `AUTHENTICATED`    | Valid `TokenState` with non-expired token    | → TOKEN_EXPIRED (expiry detected)    |
| `TOKEN_EXPIRED`    | `TokenState.is_valid()` returns False        | → REFRESHING (refresh triggered)     |
| `REFRESHING`       | `force_refresh()` in progress                | → AUTHENTICATED (success)            |
|                    |                                              | → FAILED (refresh failure)           |
| `FAILED`           | TOTP rate-limited or credentials invalid     | *(requires manual intervention)*     |

**Race condition:** The archive uses a `refresh_lock` (threading.Lock) shared
between the HTTP 401 handler and the background scheduler. The lock has a
5-second timeout to prevent indefinite blocking.

### Greenfield (`DhanAuth`)

```
  DhanAuth()
  ─────────► [INIT]
                │
                ├─ access_token provided → [AUTHENTICATED] (STATIC source)
                ├─ token_store has valid → [AUTHENTICATED] (from store)
                ├─ pin+totp_secret → generate_token() → [AUTHENTICATED] or [FAILED]
                └─ no credentials → [UNAUTHENTICATED]
```

| Method           | State Transition                                  |
|------------------|---------------------------------------------------|
| `get_token()`    | Returns current token; no state change            |
| `is_valid()`     | Checks `TokenState.is_valid()`; no state change   |
| `generate_token()` | → AUTHENTICATED (success) / FAILED (exception)  |
| `refresh_token()`  | Calls `generate_token()`; catches rate-limit    |
| `acquire()`        | Calls `generate_token()`; returns TokenState    |
| `force_refresh()`  | Delegates to `acquire()`                        |

**Greenfield differences:**
- No separate `AuthManager` wrapper; `DhanAuth` owns state directly.
- Uses `TokenState` from `brokers.infrastructure.token_persistence`.
- `refresh_token()` catches `TokenRateLimitError` and `AuthenticationError`
  gracefully, logging warnings instead of propagating.

---

## 4. Session State Machine

### Archive (`DhanSessionManager`)

```
  ┌────────────────┐
  │  AUTH_REQUIRED │ ◄── token_valid() == False
  └───────┬────────┘
          │ token acquired
          v
  ┌────────────────┐
  │ DISCONNECTED   │ ◄── no WS connections active
  └───────┬────────┘
          │ some WS connected
          v
  ┌────────────────┐
  │   DEGRADED     │ ◄── partial WS connectivity
  └───────┬────────┘
          │ all WS connected
          v
  ┌────────────────┐
  │    HEALTHY      │ ◄── token valid + all WS up
  └────────────────┘
```

| State            | Condition                                   | `is_ready_for_trading()` |
|------------------|---------------------------------------------|--------------------------|
| `AUTH_REQUIRED`  | `token_valid()` returns False               | False                    |
| `DISCONNECTED`   | Token valid, no WS connections              | False                    |
| `DEGRADED`       | Token valid, some (not all) WS connected    | False                    |
| `HEALTHY`        | Token valid, all WS connected               | True                     |

**Transition triggers:**
- Token refresh → may move from `AUTH_REQUIRED` to `DISCONNECTED`.
- WS reconnect success → `DEGRADED` → `HEALTHY` or `DISCONNECTED` → `DEGRADED`.
- WS disconnect → `HEALTHY` → `DEGRADED` or `DEGRADED` → `DISCONNECTED`.

### Greenfield

No explicit session manager. The `DhanGateway.health()` method provides
equivalent data points (`auth_valid`, scheduler health, broadcast metrics)
but does not compute a coarse lifecycle state string.

**Gap:** Greenfield lacks the `DEGRADED` vs `DISCONNECTED` distinction.

---

## 5. Token Broadcast State Machine

### Greenfield (`TokenBroadcast`)

```
  [IDLE] ──── register_receiver() ──► [HAS_RECEIVERS]
     ^                                    │
     │                                    │ broadcast(new_token)
     │                                    v
     │                                [BROADCASTING]
     │                                    │
     │  all receivers notified            │ per-receiver exceptions isolated
     v                                    v
  [IDLE] ◄────────────────────────── [BROADCASTING]
```

| State           | Description                                  | Transitions                   |
|-----------------|----------------------------------------------|-------------------------------|
| `IDLE`          | No receivers registered                      | → HAS_RECEIVERS (register)    |
| `HAS_RECEIVERS` | 1+ receivers registered                      | → BROADCASTING (broadcast)    |
| `BROADCASTING`  | Iterating receivers, delivering token        | → IDLE (complete)             |

**Key behaviors:**
- Weak references: receivers are held via `WeakMethod` for bound methods.
- Dead reference cleanup: collected receivers are pruned during `broadcast()`.
- Idempotent registration: same receiver won't be added twice.
- Per-receiver error isolation: one failure doesn't stop others.

### Archive

No equivalent `TokenBroadcast` class. Token refresh is handled by
`_on_token_refresh` callback in the factory, which directly calls
`gateway._conn.broadcast_token()`.

---

## 6. Options Trading State Machine

### Archive (`OptionsAdapter`)

```
  get_option_chain()
  ─────────► [RESOLVING]
                │
                │ identity.resolve_ref()
                ├─ success → segment determined
                └─ failure → InstrumentNotFoundError
                v
             [VALIDATING]
                │
                │ assert_dhan_identity(scrip_id, segment)
                ├─ pass → continue
                └─ fail → ValueError (invariant breach)
                v
             [FETCHING]
                │
                │ client.post("/optionchain", ...)
                ├─ success → parse strikes + greeks
                └─ failure → DhanError / MarketDataError
                v
             [COMPLETE]
```

### Greenfield (`DhanOptions`)

Same flow but without the `assert_dhan_identity` invariant assertion.
The greenfield uses `_resolve_underlying()` which has a broader search
strategy (direct resolve → INDEX fallback → substring search → commodity futures).

**Key difference:** Archive enforces defence-in-depth invariant checks via
`assert_dhan_identity()`. Greenfield relies on the resolver's correctness
without explicit payload assertion before the HTTP call.

---

## 7. Futures Trading State Machine

### Archive (`FuturesAdapter`)

```
  get_contracts()
  ─────────► [RESOLVING_EXCHANGE]
                │
                │ _resolve_derivatives_exchange()
                │ maps INDEX → NFO/BFO via _INDEX_FNO_MAP
                v
             [QUERYING_RESOLVER]
                │
                │ resolver.get_futures(underlying, exchange)
                ├─ found → format contracts
                └─ not found → empty list
                v
             [COMPLETE]
```

### Greenfield (`DhanFutures`)

```
  get_contract()
  ─────────► [SEARCHING]
                │
                │ resolver.search(query, limit=500)
                v
             [FILTERING]
                │
                │ filter by instrument_type ∈ FUTURES_INSTRUMENT_TYPES
                │ filter by symbol prefix match
                │ parse expiry from symbol
                │ exclude expired contracts
                v
             [SORTING]
                │
                │ sort by expiry ascending
                │ select by expiry_type (CURRENT=0, NEXT=1, FAR=2)
                v
             [RESOLVED] ──► DhanInstrumentRef or None
```

**Key difference:** Greenfield has richer contract resolution with expiry
parsing from symbol strings and relative expiry selection (CURRENT/NEXT/FAR).
Archive delegates to `resolver.get_futures()` which is a simpler lookup.

---

## 8. Reconciliation State Machine

### Archive (`DhanReconciliationService`)

```
  reconcile()
  ─────────► [IDLE]
                │
                │ fetch broker orders + positions
                ├─ success → broker state captured
                └─ failure → DriftItem(kind="fetch_error", severity="HIGH")
                v
             [FETCHED]
                │
                │ ReconciliationEngine.compare_orders()
                │ ReconciliationEngine.compare_positions()
                v
             [COMPARED]
                │
                │ auto_repair enabled?
                ├─ yes → _repair_local_oms()
                │         ├─ upsert missing orders
                │         └─ upsert missing positions
                └─ no → skip
                v
             [COMPLETE] ──► ReconciliationReport
```

| State       | Description                             | Failure Handling                     |
|-------------|-----------------------------------------|--------------------------------------|
| `IDLE`      | Before reconciliation starts            | N/A                                  |
| `FETCHED`   | Broker state fetched (may have errors)  | Fetch errors become DriftItems       |
| `COMPARED`  | Local vs broker comparison complete     | Comparison errors logged, not raised |
| `COMPLETE`  | Report ready, repairs applied if needed | Repair failures logged as warnings   |

### Greenfield (`DhanReconciliation`)

Simpler model: only position reconciliation, no order reconciliation.

```
  reconcile_positions()
  ─────────► [FETCHING] ──► [COMPARING] ──► [RESULT]
                │               │              │
                │ remote fetch  │ match/mismatch│ dict with:
                │ fails         │ detection     │ matched, missing_local,
                │ → error dict  │               │ missing_remote, mismatched_qty
```

**Gap:** Greenfield lacks order reconciliation, auto-repair, severity
classification, and the `ReconciliationEngine` delegation.

---

## 9. Alert State Machine

### Archive (`AlertsAdapter`)

```
  place(request)
  ─────────► [VALIDATING]
                │
                │ _validate_request()
                │ - trigger_price > 0
                │ - condition ∈ {LTP_CROSSES_ABOVE, LTP_CROSSES_BELOW}
                ├─ errors → ValueError
                └─ valid → continue
                v
             [RESOLVING]
                │
                │ identity.resolve_ref(symbol, exchange)
                │ assert_dhan_payload(payload)
                v
             [PLACING]
                │
                │ client.post("/alerts", ...)
                ├─ success → Alert(active=True)
                └─ failure → DhanError
                v
             [PLACED]

  list_all() ──► [FETCHING] ──► [LISTED]
  get(id)    ──► [FETCHING] ──► [FETCHED]
  delete(id) ──► [DELETING] ──► [DELETED]
```

### Greenfield (`DhanAlerts`)

Simpler model: no identity resolution, no invariant assertion, no request
validation. Directly posts raw payload to `/alerts`.

```
  create_alert() ──► [POSTING] ──► [CREATED]
  get_alerts()   ──► [FETCHING] ──► [LISTED]
  delete_alert() ──► [DELETING] ──► [DELETED]
  update_alert() ──► [UPDATING] ──► [UPDATED]
```

**Gap:** Greenfield lacks request validation (price > 0, condition enum),
identity resolution via `DhanInstrumentResolver`, and the invariant assertion
`assert_dhan_payload()`.

---

## 10. Instrument Loader State Machine

### Archive (`InstrumentLoader`)

```
  load_cached()
  ─────────► [CHECKING_CACHE]
                │
                │ cache exists + age < 6h?
                ├─ yes → [LOADING_FROM_CACHE]
                └─ no  → [DOWNLOADING]
                            │
                            │ pd.read_csv(Dhan CSV URL)
                            ├─ success → [CACHING] → write to disk
                            └─ failure → [FALLBACK_TO_STALE_CACHE]
                                           │
                                           │ stale cache exists?
                                           ├─ yes → load stale
                                           └─ no → raise
                v
             [MERGING_MCX]
                │
                │ _fetch_mcx_detailed()
                ├─ success → merge MCX rows
                └─ failure → mcx_required?
                              ├─ yes → raise
                              └─ no → skip (warning logged)
                v
             [COMPLETE] ──► list[dict]
```

### Greenfield (`DhanInstrumentResolver`)

```
  load()
  ─────────► [CHECKING_LOADED]
                │
                │ self._loaded flag
                ├─ True → return immediately
                └─ False → [DOWNLOADING]
                              │
                              │ requests.get(CSV_URL, timeout=30)
                              ├─ success → parse rows → [LOADED]
                              └─ failure → raise (no fallback)
                              v
                           [LOADED] ──► self._loaded = True
```

**Gap:** Greenfield has no caching, no MCX supplement, no stale-cache fallback.

---

## 11. Configuration Loader State Machine

### Archive (`DhanConfigLoader`)

```
  load()
  ─────────► [DEFAULTS]
                │
                │ parse .env file (if exists)
                v
             [ENV_FILE_LOADED]
                │
                │ parse DHAN_RESILIENCE_* env vars
                v
             [ENV_VARS_MERGED]
                │
                │ DhanResilienceConfig.from_dict(merged)
                v
             [CONFIG_READY]
```

Priority: defaults < .env file < environment variables.

### Greenfield (`config.py`)

Static module-level constants. No loading state machine. All values are
imported directly:

```python
REST_BASE = "https://api.dhan.co/v2"
ENDPOINTS = { ... }
RATE_LIMITS = { ... }
EXCHANGE_MAP = { ... }
```

**Gap:** Greenfield has no runtime-configurable resilience parameters.
All values are hardcoded at module level.

---

## 12. Order Lifecycle State Machine (Domain)

Both archive and greenfield share the same domain-level order lifecycle
defined in `brokers/domain/order_lifecycle.py`:

```
  PENDING ────► OPEN ────► PARTIALLY_FILLED ────► FILLED
     │           │               │
     │           │               ├────► CANCELLED
     │           │               └────► PARTIALLY_CANCELLED ──► CANCELLED
     │           │
     │           ├────► FILLED
     │           ├────► CANCELLED
     │           ├────► PARTIALLY_CANCELLED
     │           ├────► EXPIRED
     │           └────► REJECTED
     │
     ├────► OPEN
     ├────► REJECTED
     ├────► CANCELLED
     └────► EXPIRED

  Terminal states: FILLED, CANCELLED, PARTIALLY_CANCELLED, EXPIRED, REJECTED
```

This is the canonical transition table shared by both implementations.

---

## 13. Greenfield vs Archive Comparison Summary

| Concern              | Archive State Depth | Greenfield State Depth | Gap Severity |
|----------------------|---------------------|------------------------|--------------|
| Gateway lifecycle    | Implicit (3 states) | Inline in __init__     | Low          |
| Factory bootstrap    | 5 explicit states   | Collapsed into gateway | Medium       |
| Auth/Identity        | 5 states + lock     | 3 states + lock        | Low          |
| Session manager      | 4 states            | Not implemented        | **High**     |
| Token broadcast      | N/A (inline)        | 3 states + weakref     | N/A (new)    |
| Options trading      | 4 states + invariants | 3 states, no invariants | Medium    |
| Futures trading      | 3 states            | 4 states (richer)      | N/A (improved) |
| Reconciliation       | 4 states + repair   | 3 states, positions only | **High**   |
| Alerts               | 4 states + validation | 2 states, no validation | Medium    |
| Instrument loader    | 5 states + cache    | 2 states, no cache     | **High**     |
| Config loader        | 3 states + merge    | Static constants       | Medium       |
| Order lifecycle      | Shared domain model | Shared domain model    | None         |

---

*End of Phase 8 — State Machines*
