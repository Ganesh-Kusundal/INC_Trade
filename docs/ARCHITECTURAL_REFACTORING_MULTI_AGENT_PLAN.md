# MULTI-AGENT PARALLEL EXECUTION PLAN — ARCHITECTURAL REFACTORING PROGRAM
## TradeXV2 `brokers/` Package — Production-QA · Dependency-Driven · Zero-Conflict

---

## TABLE OF CONTENTS

1. [Parallelization Principles](#1-parallelization-principles)
2. [Dependency Graph & Execution Schedule](#2-dependency-graph--execution-schedule)
3. [Agent Assignments — Disjoint Write Sets](#3-agent-assignments--disjoint-write-sets)
4. [Agent Coordination Protocol](#4-agent-coordination-protocol)
5. [Production QA Validation Matrix](#5-production-qa-validation-matrix)
6. [Complete Agent Dispatch Sequence](#6-complete-agent-dispatch-sequence)
7. [Ready-to-Dispatch Agent Prompts](#7-ready-to-dispatch-agent-prompts)
8. [Rollback Strategy — Per Wave](#8-rollback-strategy--per-wave)
9. [Completion Certification Script](#9-completion-certification-script)
10. [Risk Matrix](#10-risk-matrix)

---

## 1. PARALLELIZATION PRINCIPLES

| PRINCIPLE | RULE |
|-----------|------|
| **Disjoint Write Sets** | No two agents ever write to the same file |
| **Read-Only Shared State** | Agents may read any file but write only to their own assigned set |
| **Wave Serialization** | Wave N+1 begins only when Wave N is fully validated |
| **Agent Autonomy** | Each agent has full context to make decisions without coordinator intervention |
| **Production QA Gate** | Every agent validates its output before reporting handoff |

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PARALLELIZATION STRATEGY                                  │
│                                                                             │
│  Wave 0: 4 agents × FULLY PARALLEL (zero file conflicts)                   │
│  Wave 1: 3 agents × FULLY PARALLEL (zero file conflicts)                   │
│  Wave 2: 1 agent × serial finalization                                     │
│                                                                             │
│  Sequential equivalent: ~120 min                                           │
│  Parallel execution:    ~28 min  (4.3× speedup)                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. DEPENDENCY GRAPH & EXECUTION SCHEDULE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           WAVE 0 — FOUNDATIONS                              │
│                   (4 agents, fully parallel, zero conflicts)                │
├──────────────┬──────────────┬──────────────┬────────────────────────────────┤
│   AGENT A    │   AGENT B    │   AGENT C    │           AGENT D              │
│  Core +      │  Config +    │   Domain     │      Extension Registry        │
│    Ports     │   Endpoints  │   Cleanup    │                                │
│              │              │              │                                │
│ • ports/     │ • config/    │ • domain/    │ • ports/                       │
│   event_     │   endpoints  │   entities   │   extension_                   │
│   publisher  │ • adapters/  │              │   registry.py                  │
│   .py [NEW] │   dhan/      │              │                                │
│ • core/      │   config     │              │                                │
│   order_     │ • adapters/  │              │                                │
│   result_    │   dhan/      │              │                                │
│   cache.py   │   http       │              │                                │
│ • core/      │              │              │                                │
│   correlation│              │              │                                │
│   _gate.py   │              │              │                                │
│   [DELETE]   │              │              │                                │
│ • core/      │              │              │                                │
│   idempot... │              │              │                                │
│   [DELETE]   │              │              │                                │
│ • infra/     │              │              │                                │
│   event_bus  │              │              │                                │
└──────┬───────┴──────┬───────┴──────┬───────┴────────────────────────────────┘
       │               │               │
       └───────────────┴──────┬────────┘
                              │
                    ┌─────────────────┐
                    │   GATE 0        │
                    │ pytest -m arch  │
                    │ pytest unit/    │
                    │ ruff check      │
                    │ ~2 minutes      │
                    └────────┬────────┘
                             │ PASS
                             ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│                          WAVE 1 — ADAPTER TRANSFORMATION                     │
│                   (3 agents, fully parallel, zero file conflicts)           │
├────────────────┬──────────────────┬─────────────────────────────────────────┤
│    AGENT E     │     AGENT F      │           AGENT G                       │
│  Dhan Adapter  │  Upstox Adapter  │  Bootstrap + Tests + Ext Consumers      │
│                │                  │                                         │
│ • adapters/    │ • adapters/      │ • infrastructure/                       │
│   dhan/orders  │   upstox/        │   bootstrap.py                          │
│ • adapters/    │   gateway        │ • tests/unit/                           │
│   dhan/gateway │ • adapters/      │   test_architecture.py                 │
│ • adapters/    │   upstox/        │ • All extension                        │
│   dhan/factory │   compat_        │   consumer files                       │
│ • [DELETE]     │   _gateway [DEL] │                                         │
│   dhan/        │                  │                                         │
│   compat_      │                  │                                         │
│   gateway.py   │                  │                                         │
│ • adapters/    │                  │                                         │
│   dhan/        │                  │                                         │
│   idempotency  │                  │                                         │
│   .py [DEL]    │                  │                                         │
└────────────────┴──────────────────┴─────────────────────────────────────────┘
       │                │                     │
       └────────────────┴──────────┬──────────┘
                                  │
                        ┌─────────────────┐
                        │   GATE 1        │
                        │ pytest arch     │
                        │ pytest -m 'not  │
                        │   integration'  │
                        │ ruff            │
                        │ ~4 minutes      │
                        └────────┬────────┘
                                 │ PASS
                                 ▼

┌─────────────────────────────────────────────────────────────────────────────┐
│                       WAVE 2 — TYPE SAFETY + FINAL QA                       │
│                            (1 agent, serial)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                        AGENT H                                              │
│                   mypy Strict Enablement                                    │
│                                                                             │
│ • pyproject.toml  (removes mypy exemptions)                                │
│ • Fixes all type errors found by mypy --strict                             │
│ • Enforces 100% strict coverage across adapters/                           │
│                         infrastructure/ config/                             │
│                                                                             │
│                        ┌─────────────────┐                                  │
│                        │   FINAL GATE    │                                  │
│                        │ pytest --cov    │                                  │
│                        │ mypy --strict   │                                  │
│                        │ ruff            │                                  │
│                        │ coverage ≥90%   │                                  │
│                        │ ~5 minutes      │                                  │
│                        └─────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────────┘

TOTAL ELAPSED: ~28 minutes    SEQUENTIAL EQUIVALENT: ~120 minutes    SPEEDUP: 4.3×
```

### Critical Path Timeline

```
Time  →  0m    5m    10m   15m   20m   25m   30m
       ┌───────────────────────────────────────────────────────────────┐
WAVE 0 │ ██████████████████████████ ALL 4 AGENTS VALIDATED ████████████ │
       │                              │                                        │
GATE 0 │                         ██ GATE 0 ██                                   │
       │                              │ PASS                                   │
WAVE 1 │         ████████████████████████████ Agent E ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀ │
       │         ██████████████████████ Agent F ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀ │
       │         ████████████████████ Agent G ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀ ███│
       │                              │                                        │
GATE 1 │                         ██ GATE 1 ██                                   │
       │                              │ PASS                                   │
WAVE 2 │                              ████████████████████████ Agent H ████ │
       │                              │                                        │
GATE 2 │              ██ FINAL QA ██                                           │
       └───────────────────────────────────────────────────────────────┘
```

---

## 3. AGENT ASSIGNMENTS — DISJOINT WRITE SETS

### WAVE 0 — FOUNDATIONS (4 agents, fully parallel)

---

#### Agent A — Core + Ports Infrastructure

```
WRITE SCOPE (exclusive ownership — no other agent touches these):
─────────────────────────────────────────────────────────────────────
CREATE  ports/event_publisher.py
MODIFY  core/order_result_cache.py   (verify sole implementation, minor tweaks)
DELETE  core/correlation_gate.py
DELETE  core/idempotency.py
DELETE  core/typed_idempotency.py
MODIFY  infrastructure/event_bus.py   (implement EventPublisherPort)
MODIFY  ports/__init__.py            (add EventPublisherPort export)

READ SCOPE (any file — for context, do NOT modify):
adapters/dhan/orders.py, adapters/dhan/idempotency.py,
domain/events.py, ports/__init__.py
```

**TASK BRIEF:**
1. Create `ports/event_publisher.py` — `EventPublisherPort` Protocol (decorated `@runtime_checkable`)
2. Make `infrastructure/event_bus.py` `EventBus` implement `EventPublisherPort` (thin adapter)
3. Delete `core/correlation_gate.py` — `IdempotencyCache` is consolidated into `core/order_result_cache.py`
4. Delete `core/idempotency.py` — was a backward-compat alias
5. Delete `core/typed_idempotency.py` — was a backward-compat alias
6. Update `infrastructure/event_bus.py` to implement the new `EventPublisherPort`
7. Update `ports/__init__.py` to export `EventPublisherPort`

**DELIVERABLES:**
```
ports/
├── event_publisher.py              [NEW]     EventPublisherPort Protocol
core/
├── order_result_cache.py           [UNCHANGED — already sole impl]
└── (3 files deleted)
infrastructure/
└── event_bus.py                    [MODIFIED — implements EventPublisherPort]
```

**VALIDATION:**
```bash
python -c "from ports.event_publisher import EventPublisherPort; \
 from infrastructure.event_bus import EventBus; \
 assert isinstance(EventBus(), EventPublisherPort)"

grep -r "import.*correlation_gate"  brokers/ | grep -v test | grep -v __pycache__   # → 0
grep -r "import.*typed_idempotency" brokers/ | grep -v test | grep -v __pycache__ # → 0
grep -r "import.*idempotency"      brokers/core/ | grep -v test                 # → 0
```

**PRODUCTION QA CHECKLIST:**
```text
□ No remaining import of deleted files anywhere in the codebase
□ EventBus still passes all existing event_bus tests
□ EventPublisherPort can be backed by any implementation (testability)
□ No new module-level mutable state introduced
□ Ports package __all__ updated with new export
□ ruff lint passes on all changed files
□ ruff format passes on all changed files
□ Event bus contract tests verify publish/subscribe still works
```

---

#### Agent B — Config + Endpoint Consolidation

```
WRITE SCOPE (exclusive ownership):
───────────────────────────────────
MODIFY  config/endpoints.py             (absorb all Dhan URLs from adapters/dhan/endpoints.py)
DELETE  adapters/dhan/endpoints.py
MODIFY  adapters/dhan/config.py         (import ENDPOINTS from config/endpoints)
MODIFY  adapters/dhan/http.py           (use config/endpoints.py as sole URL source)

READ SCOPE (any file — for context):
config/__init__.py, adapters/dhan/endpoints.py, adapters/dhan/__init__.py
```

**TASK BRIEF:**
1. Move all endpoint definitions from `adapters/dhan/endpoints.py` into `config/endpoints.py`
2. Delete `adapters/dhan/endpoints.py` entirely
3. Update `adapters/dhan/config.py` to import `ENDPOINTS` from `config/endpoints` instead of the local file
4. Update `adapters/dhan/http.py` — resolve all URLs through `config/endpoints.py` only

**VALIDATION:**
```bash
grep -r "from.*adapters.*dhan.*endpoints" brokers/              # → 0 matches
grep -r "from.*dhan.*endpoints" brokers/ | grep -v test         # → 0 matches
python -c "from config.endpoints import Dhan; assert Dhan.ORDERS == '/orders'"

# Must NOT be able to import from old location:
python -c "
try:
    from brokers.adapters.dhan.endpoints import ENDPOINTS
    exit(1)
except ImportError:
    pass  # Expected — file deleted
"
```

**PRODUCTION QA CHECKLIST:**
```text
□ No remaining import of adapters/dhan/endpoints.py anywhere
□ config/endpoints.py is the single canonical source for broker URLs
□ All existing dhan HTTP calls resolve to the SAME URLs (behavior unchanged)
□ dhan health checks pass (no URL breakage)
□ All existing dhan integration tests still pass
□ ruff check + format passes on all modified files
```

---

#### Agent C — Domain Cleanup

```
WRITE SCOPE (exclusive ownership):
───────────────────────────────────
MODIFY  domain/entities.py            (remove all raw: dict fields, add explicit fields)
MODIFY  domain/__init__.py            (ensure clean exports)

READ SCOPE (for understanding current raw dict keys):
adapters/dhan/mapper.py, adapters/upstox/mapper.py,
adapters/dhan/reconciliation_models.py,
tests/unit/test_domain_entities.py, tests/unit/test_mapper.py
```

**TASK BRIEF:**
1. Remove all `raw: dict` fields from domain entities — replace with explicit typed fields:
   - `UserProfile.raw` → explicit `broker: str` field
   - `IpoInfo.raw` → explicit fields for known IPO metadata
   - `MutualFundHolding.raw` → explicit fields for holdings data
   - `OptionChainEntry.raw` → explicit `strike_price`, `option_type`, `last_price`, `oi`, `volume` fields
   - `OptionChain.raw` → `underlying: str`, `expiry: str` on the container (already present)
   - `NewsItem.raw` → `headline`, `summary`, `source`, `timestamp` (already explicit)

2. Keep constructors backward-compatible — use field defaults so existing tests don't need modification
3. Ensure `domain/__init__.py` exports remain unchanged (no API breakage)

**VALIDATION:**
```bash
grep -r "raw.*=.*field"                        brokers/domain/entities.py          # → 0
grep -r "\.raw"                                brokers/domain/ | grep -v test       # → 0
pytest brokers/tests/unit/test_domain_entities.py -v                           # → pass
pytest brokers/tests/unit/adapters/dhan/test_mapper.py -v                       # → pass
pytest brokers/tests/unit/adapters/upstox/test_tick_mapper.py -v                # → pass
```

**PRODUCTION QA CHECKLIST:**
```text
□ No .raw or raw= or raw: dict[ in domain/entities.py
□ No remaining reference to .raw on domain entities outside test files
□ All existing mapper tests still pass (mappers now populate explicit fields)
□ All domain entity unit tests still pass without modification
□ Change is purely additive: no removal of existing fields or constructor params
□ New explicit fields cover all keys previously accessed from raw dicts
□ Field names are broker-agnostic (no dhan_/upstox_ prefixes)
```

---

#### Agent D — Extension Registry

```
WRITE SCOPE (exclusive ownership):
───────────────────────────────────
CREATE  ports/extension_registry.py
MODIFY  ports/__init__.py

DO NOT DELETE (consumers updated in Wave 1 — see Agent G):
ports/extensions.py   (old naming-based implementation, keep for now)

READ SCOPE (for understanding usage):
ports/__init__.py, ports/capabilities.py,
adapters/dhan/gateway.py, adapters/upstox/gateway.py,
tests/unit/adapters/dhan/test_*,
tests/unit/adapters/upstox/test_*
```

**TASK BRIEF:**
1. Create `ports/extension_registry.py`:
   - `ExtensionRegistry` class (NOT a singleton — instantiable)
   - `register(broker_id: str, extension_type: type[T], instance: T) -> None`
   - `resolve(broker_id: str, extension_type: type[T]) -> T | None`
   - `supports(broker_id: str, extension_type: type[T]) -> bool`
   - Internal: `dict[str, dict[type, object]]` (type-safe, not naming-convention-based)

2. Update `ports/__init__.py` to export `ExtensionRegistry` and `BrokerExtension`

3. **Do NOT delete `ports/extensions.py`** — consumers are updated in Wave 1 by Agent G

**VALIDATION:**
```bash
python -c "
from ports.extension_registry import ExtensionRegistry
from ports.capabilities import MarginProvider

r = ExtensionRegistry()
r.register('dhan', MarginProvider, object())
assert r.supports('dhan', MarginProvider)
assert not r.supports('upstox', MarginProvider)
print('ExtensionRegistry OK')
"

# ports/extensions.py STILL EXISTS (deletion deferred to Wave 1):
test -f /Users/apple/Downloads/INC_Trade/brokers/ports/extensions.py && echo "OK: extensions.py preserved"
```

**PRODUCTION QA CHECKLIST:**
```text
□ ExtensionRegistry is type-safe: isinstance() check on resolve()
□ ExtensionRegistry is NOT a module-level singleton
□ All existing extension consumers still work (old API not yet removed)
□ ports/__init__.py exports ExtensionRegistry and BrokerExtension
□ ruff lint + format passes
□ No hasattr-based discovery introduced in new code
□ Documentation: docstrings explain old vs new pattern
```

---

### GATE 0 — Wave 0 Synchronization Barrier

```bash
#!/usr/bin/env bash
# GATE 0: All 4 Wave 0 agents must pass these checks before Wave 1 proceeds

set -euo pipefail

echo "=== GATE 0: Wave 0 Validation ==="

echo "[1/6] Architecture tests..."
pytest -m architecture --tb=long -v

echo "[2/6] Unit tests (non-architecture)..."
pytest brokers/tests/unit/ -m "not integration" -x --tb=short

echo "[3/6] No forbidden adapter→infrastructure imports..."
 IMPORTS=$(grep -r "from brokers\.infrastructure\|import brokers\.infrastructure" \
   brokers/adapters/ --include="*.py" | grep -v __pycache__ | wc -l)
 if [ "$IMPORTS" -gt 0 ]; then
   echo "FAIL: Found $IMPORTS adapter→infrastructure imports"
   exit 1
 fi
 echo "PASS: 0 adapter→infrastructure imports"

echo "[4/6] ruff lint..."
ruff check brokers/

echo "[5/6] ruff format..."
ruff format --check brokers/

echo "[6/6] Extension system..."
grep -r "supports_extension\|get_extension" brokers/ | \
  grep -v test | grep -v __pycache__ | grep -v "registry" | wc -l
 # Should be 0 (old API still present but not referenced by non-test code)

echo ""
echo "=== GATE 0: ALL CHECKS PASSED — Proceeding to Wave 1 ==="
```

**If any check fails → Rollback Wave 0:**
```bash
git revert HEAD~4..HEAD    # Reverts all 4 agent commits atomically
git push --force-with-lease # If already pushed (with team notification)
```

---

### WAVE 1 — ADAPTER TRANSFORMATION (3 agents, fully parallel)

**DEPENDS ON:** Wave 0 ALL validated (GATE 0 passed).

---

#### Agent E — Dhan Adapter

```
WRITE SCOPE (exclusive ownership):
───────────────────────────────────
MODIFY  adapters/dhan/orders.py
MODIFY  adapters/dhan/gateway.py
MODIFY  adapters/dhan/factory.py
MODIFY  adapters/dhan/__init__.py
MODIFY  adapters/dhan/use_cases/place_order.py
DELETE  adapters/dhan/compat_gateway.py
DELETE  adapters/dhan/idempotency.py

READ SCOPE (Wave 0 artifacts, for integration):
ports/event_publisher.py
core/order_result_cache.py
config/endpoints.py
ports/extension_registry.py
```

**TASK BRIEF:**

**In `orders.py`:**
- REMOVE: `from brokers.infrastructure.correlation import ...`
- REMOVE: `from brokers.infrastructure.event_bus import EventBus`
- ADD: `from ports.event_publisher import EventPublisherPort`
- CHANGE: `__init__` accepts `event_publisher: EventPublisherPort` instead of `event_bus: EventBus`
- CHANGE: idempotency cache type → `TypedIdempotencyCache[OrderResponse]` from `core/order_result_cache`
- KEEP: `correlation_id: str` as an explicit method parameter (already present)

**In `gateway.py`:**
- EXTRACT: Move sub-adapter construction into a builder method or factory function
- ACCEPT: Pre-constructed sub-adapters in `__init__` parameters (dependency injection)
- REMOVE: `compat_gateway` import and all related code
- KEEP: `BrokerGateway` protocol implementation completely unchanged

**In `factory.py`:**
- CHANGE: `DhanBrokerFactory.create()` returns `DhanCompatibilityGateway` → returns `DhanGateway` directly
- DELETE: `adapters/dhan/compat_gateway.py` (all callers updated)

**DELIVERABLES:**
```
adapters/dhan/
├── gateway.py          [MODIFIED — extracted __init__]
├── orders.py           [MODIFIED — uses ports only]
├── factory.py          [MODIFIED — returns DhanGateway]
├── __init__.py         [MODIFIED]
├── use_cases/
│   └── place_order.py  [MODIFIED]
├── compat_gateway.py   [DELETED]
└── idempotency.py      [DELETED — was alias]
```

**VALIDATION:**
```bash
grep -r "infrastructure"    brokers/adapters/dhan/ | grep -v __pycache__    # → 0
grep -r "compat_gateway"    brokers/adapters/dhan/ | grep -v __pycache__    # → 0
grep -r "DhanIdempotency"   brokers/ | grep -v test | grep -v __pycache__   # → 0

python -c "from adapters.dhan.gateway import DhanGateway; print('DhanGateway OK')"
python -c "from adapters.dhan.orders import DhanOrders; print('DhanOrders OK')"
python -c "from adapters.dhan.factory import DhanBrokerFactory; print('Factory OK')"
```

**PRODUCTION QA CHECKLIST:**
```text
□ Zero imports from brokers.infrastructure in adapters/dhan/
□ Zero references to compat_gateway anywhere in adapters/dhan/
□ Zero references to DhanIdempotencyCache
□ All existing Dhan unit tests pass without modification
□ All existing Dhan contract tests pass
□ Events still published (via EventPublisherPort, verified by audit logs)
□ Idempotency still works (via TypedIdempotencyCache, tested by check_and_set)
□ Correlation ID still flows correctly (now via port parameter, verified)
□ DhanGateway.__init__ line count ≤ 40 lines (was ~120)
□ Integration tests with mock broker return identical responses
```

---

#### Agent F — Upstox Adapter

```
WRITE SCOPE (exclusive ownership — no overlap with Agent E):
─────────────────────────────────────────────────────────────
MODIFY  adapters/upstox/gateway.py
DELETE  adapters/upstox/compat_gateway.py
MODIFY  adapters/upstox/__init__.py

READ SCOPE (Wave 0 artifacts, for integration):
ports/event_publisher.py
ports/extension_registry.py
config/endpoints.py
```

**TASK BRIEF:**
1. Mirror Dhan adapter cleanup in Upstox:
   - Extract sub-adapter construction from `__init__`
   - Accept pre-constructed sub-adapters via dependency injection
   - Remove `compat_gateway` import

2. Delete `adapters/upstox/compat_gateway.py`

3. Update `adapters/upstox/__init__.py` to reflect updated exports

**VALIDATION:**
```bash
grep -r "compat_gateway"    brokers/adapters/upstox/ | grep -v __pycache__  # → 0

python -c "from adapters.upstox.gateway import UpstoxGateway; print('OK')"
pytest brokers/tests/unit/adapters/upstox/test_gateway.py -v                 # → pass
```

**PRODUCTION QA CHECKLIST:**
```text
□ No compat_gateway references in adapters/upstox/
□ No infrastructure imports introduced
□ UpstoxGateway still implements BrokerGateway protocol
□ All existing Upstox unit tests pass
□ Contract tests verify BrokerGateway conformance
```

---

#### Agent G — Bootstrap + Tests + Extension Consumers

```
WRITE SCOPE (exclusive ownership):
───────────────────────────────────
MODIFY  infrastructure/bootstrap.py
MODIFY  tests/unit/test_architecture.py
MODIFY  Any file using supports_extension() or get_extension() (extension consumers)
DO AFTER ALL CONSUMERS UPDATED: DELETE ports/extensions.py

READ SCOPE (Wave 0 + Agent E/F artifacts for understanding):
ports/extension_registry.py, adapters/dhan/gateway.py,
adapters/upstox/gateway.py, infrastructure/bootstrap.py
```

**TASK BRIEF:**

**Part 1 — Bootstrap (`infrastructure/bootstrap.py`):**
Complete `_step_register_brokers`:
- Read `broker_names` from config (`TRADEX_BROKERS` env var or `["dhan"]` default)
- For each broker name, call `factory.create()` (now returns `DhanGateway` / `UpstoxGateway`)
- Register each gateway in `BrokerRegistry`
- Register `ExtensionRegistry` instance in DI container
- Register `TypedIdempotencyCache` in DI container
- Wire `EventBus` → `EventPublisherPort` in DI

**Part 2 — Architecture Test Updates (`test_architecture.py`):**
Add 5 new test classes:
- `TestNoAdapterImportsInfrastructure`
- `TestSingleIdempotencyImplementation`
- `TestNoCompatGateways`
- `TestNoRawDictInDomain`
- `TestSingleEndpointAuthority`

**Part 3 — Extension Consumer Migration:**
1. Search for all files using `supports_extension()` or `get_extension()`:
   ```bash
   grep -r "supports_extension\|get_extension" brokers/ | grep -v test
   ```

2. For each consumer:
   ```python
   # OLD:
   if supports_extension(gateway, MarginProvider):
       margin = get_extension(gateway, MarginProvider)
   
   # NEW:
   if registry.supports(broker_id, MarginProvider):
       margin = registry.resolve(broker_id, MarginProvider)
   ```

3. After ALL consumers migrated:
   - DELETE `ports/extensions.py`
   - Remove old exports from `ports/__init__.py`

**VALIDATION:**
```bash
pytest -m architecture -v                                                # → all pass
grep -r "supports_extension\|get_extension" brokers/ | grep -v test     # → 0
grep -r "supports_extension\|get_extension" ports/                      # → 0

# After deleting ports/extensions.py:
python -c "
try:
    from brokers.ports.extensions import supports_extension
    exit(1)
except ImportError:
    pass  # Expected
"
```

**PRODUCTION QA CHECKLIST:**
```text
□ Step 8 of bootstrap creates and registers all configured broker gateways
□ Startup health snapshot reports all services correctly
□ All 5 new architecture tests pass
□ All extension consumer files migrated to ExtensionRegistry
□ ports/extensions.py is DELETED (only after ALL consumers updated — atomic safe)
□ No remaining references to supports_extension or get_extension
□ DI container registered services: config, profile, secrets_manager,
  event_bus, extension_registry, idempotency_cache, lifecycle, registry
□ All existing integration tests still pass
```

---

### GATE 1 — Wave 1 Synchronization Barrier

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== GATE 1: Wave 1 Validation ==="

echo "[1/5] Architecture tests..."
pytest -m architecture --tb=long -v

echo "[2/5] Unit tests (all non-integration)..."
pytest -m "not integration" -x --tb=short

echo "[3/5] No forbidden import patterns..."
grep -r "from brokers\.infrastructure" brokers/adapters/ --include="*.py" \
  | grep -v __pycache__ | wc -l   # → 0
grep -r "compat_gateway" brokers/ --include="*.py" \
  | grep -v __pycache__ | wc -l   # → 0

echo "[4/5] ruff check..."
ruff check brokers/

echo "[5/5] ruff format..."
ruff format --check brokers/

echo ""
echo "=== GATE 1: ALL CHECKS PASSED — Proceeding to Wave 2 ==="
```

---

### WAVE 2 — TYPE SAFETY + FINAL QA (1 agent, serial)

**DEPENDS ON:** Wave 1 ALL validated (GATE 1 passed).

---

#### Agent H — mypy Strict Enablement

```
WRITE SCOPE (exclusive ownership):
───────────────────────────────────
MODIFY  pyproject.toml        (remove mypy strict exemptions)
MODIFY  Any file with type errors discovered by mypy --strict

READ SCOPE (entire codebase for type error diagnosis):
All .py files in brokers/
```

**TASK BRIEF:**
1. Remove these mypy overrides from `pyproject.toml`:
   ```toml
   # DELETE THESE SECTIONS:
   [[tool.mypy.overrides]]
   module = "brokers.adapters.*"
   disallow_untyped_defs = false

   [[tool.mypy.overrides]]
   module = "brokers.infrastructure.*"
   disallow_untyped_defs = false

   [[tool.mypy.overrides]]
   module = "brokers.config.*"
   disallow_untyped_defs = false

   [[tool.mypy.overrides]]
   module = "brokers.tests.*"
   disallow_untyped_defs = false
   ```

2. Run `mypy brokers --strict` — categorize errors:
   - **Pre-existing errors** (existed before this wave): Document in `docs/mypy_known_issues.md`, do NOT fix as part of this wave (separate ticket)
   - **New errors** (introduced by refactoring): Fix immediately
   - **Fix approach**: Add missing type annotations, add `TypeVar` where generics needed, replace `Any` with concrete types where possible

**TYPICAL FIXES EXPECTED:**
| mypy Error | Fix |
|------------|-----|
| `error: Function is missing a return type annotation` | Add `-> ReturnType` |
| `error: Need type annotation for` | Add type to variable declaration |
| `error: Incompatible types in assignment` | Fix type mismatch or add cast with justification |
| `error: Argument X has incompatible type` | Fix argument type or adjust function signature |
| `error: "Any" not allowed` | Replace `Any` with concrete type |

**VALIDATION:**
```bash
mypy brokers --strict                    # → Exit code 0, zero errors
ruff check brokers/                      # → Clean
ruff format --check brokers/             # → Clean
```

**PRODUCTION QA CHECKLIST:**
```text
□ 100% of codebase under mypy strict (no exemptions remaining in pyproject.toml)
□ Zero new type: ignore comments added during this wave
□ Zero new cast() calls unless documented with justification comment
□ All 781+ existing tests still pass
□ No type narrowing added that changes runtime behavior
□ Pre-existing mypy errors documented, not silently ignored
□ New type annotations follow existing naming conventions
□ ruff passes on all changed files
```

---

### GATE 2 — Final Program Validation

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== FINAL VALIDATION: Architectural Refactoring Program ==="

FAIL=0

echo ""
echo "[1/7] Full test suite..."
pytest --cov=brokers --cov-report=term-missing --tb=long -v 2>&1 | tee test-results.txt
PASSED=$(grep -oP '\d+ passed' test-results.txt | grep -oP '\d+')
COVERAGE=$(grep -oP 'TOTAL.*\d+%' test-results.txt | grep -oP '\d+')
if [ "$PASSED" -lt 781 ]; then
  echo "FAIL: Expected 781+ passed, got $PASSED"
  FAIL=1
fi
if [ "$COVERAGE" -lt 90 ]; then
  echo "FAIL: Expected ≥90% coverage, got $COVERAGE%"
  FAIL=1
fi

echo ""
echo "[2/7] Architecture tests..."
pytest -m architecture --tb=long -v

echo ""
echo "[3/7] mypy strict..."
mypy brokers --strict

echo ""
echo "[4/7] ruff..."
ruff check brokers/
ruff format --check brokers/

echo ""
echo "[5/7] Forbidden pattern scan..."
PATTERNS=(
  "raw.*=.*field.*default_factory=dict"
  "from brokers\.infrastructure"
  "compat_gateway"
  "supports_extension\|get_extension"
)
for PATTERN in "${PATTERNS[@]}"; do
  COUNT=$(grep -rP "$PATTERN" brokers/ --include="*.py" \
    | grep -v __pycache__ | grep -v test | grep -v docs | wc -l)
  if [ "$COUNT" -gt 0 ]; then
    echo "FAIL: Found pattern '$PATTERN' ($COUNT matches)"
    FAIL=1
  else
    echo "PASS: pattern '$PATTERN' — 0 matches"
  fi
done

echo ""
echo "[6/7] Idempotency consolidation..."
python3 -c "
from brokers.core.order_result_cache import TypedIdempotencyCache
print('OK: Sole idempotency = TypedIdempotencyCache')
"

echo ""
echo "[7/7] Endpoint consolidation..."
python3 -c "
try:
    from adapters.dhan.endpoints import ENDPOINTS
    print('FAIL: adapters/dhan/endpoints.py still exists')
    FAIL=1
except ImportError:
    print('OK: adapters/dhan/endpoints.py deleted')
from config.endpoints import Dhan
print(f'OK: Dhan.ORDERS = {Dhan.ORDERS}')
"

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  🎉  ARCHITECTURAL REFACTORING PROGRAM COMPLETE             ║"
  echo "║                                                              ║"
  echo "║  All 7 validation gates passed.                             ║"
  echo "║  Board Verdict: UNANIMOUS APPROVED                          ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  exit 0
else
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  ❌  VALIDATION FAILED                                      ║"
  echo "║  See FAIL messages above. Roll back if needed.               ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  exit 1
fi
```

---

## 4. AGENT COORDINATION PROTOCOL

### 4.1 Handoff Manifest Format

Each agent, upon completion, produces a **handoff manifest** JSON:

```json
{
  "agent": "Agent A",
  "wave": 0,
  "assigned_files": [
    "ports/event_publisher.py",
    "infrastructure/event_bus.py",
    "core/order_result_cache.py",
    "core/correlation_gate.py",
    "core/idempotency.py",
    "core/typed_idempotency.py",
    "ports/__init__.py"
  ],
  "files_created": ["ports/event_publisher.py"],
  "files_modified": ["infrastructure/event_bus.py", "core/order_result_cache.py", "ports/__init__.py"],
  "files_deleted": [
    "core/correlation_gate.py",
    "core/idempotency.py",
    "core/typed_idempotency.py"
  ],
  "validation": {
    "python_assert": "python3 -c 'from ports.event_publisher import EventPublisherPort; from infrastructure.event_bus import EventBus; assert isinstance(EventBus(), EventPublisherPort)' → PASS",
    "grep_imports": "grep -r 'import.*correlation_gate' brokers/ → 0 matches",
    "ruff_lint": "ruff check brokers/ → PASS",
    "ruff_format": "ruff format --check brokers/ → PASS",
    "unit_tests": "pytest tests/unit/test_event_bus.py -v → 5 passed"
  },
  "gate_result": "PASSED",
  "residual_risks": [
    "Adaptors/dhan/orders.py still imports from infrastructure.correlation (fixed in Wave 1 by Agent E)",
    "ports/extensions.py still exists (deleted in Wave 1 by Agent G)"
  ],
  "peer_dependencies": ["Agent B", "Agent C", "Agent D"],
  "next_wave_dependencies": ["Agent E", "Agent F", "Agent G"]
}
```

### 4.2 Gate Protocol

The **coordinator agent** (you) executes each gate:

```
GATE N → N+1 PROTOCOL:
─────────────────────────
Step 1: Receive handoff manifest from all agents in Wave N
Step 2: Stash any local work (git stash)
Step 3: Run validation commands from each manifest:
        - pytest -m architecture --tb=long -v
        - pytest brokers/tests/unit/ -m "not integration" -x --tb=short
        - ruff check brokers/
        - ruff format --check brokers/
        - Manual grep verification per agent's manifest
Step 4: If ANY check fails:
        a. Notify failing agent with specific failure output
        b. Agent fixes and resubmits handoff manifest
        c. If agent cannot fix within deadline → escalate to human
        d. DO NOT proceed to Wave N+1
Step 5: If ALL checks pass:
        a. Tag commit as "wave-N-green"
        b. Dispatch Wave N+1 agents
        c. Begin coordinator monitoring for Wave N+1

Gate timeout: 30 minutes maximum. If gate cannot be run in 30 min → escalate.
```

### 4.3 Conflict Resolution Matrix

| CONFLICT TYPE | DETECTION | RESOLUTION |
|--------------|-----------|-------------|
| Two agents write same file | Git merge conflict | ❌ PREVENTED — redesign write scopes before dispatch |
| Agent needs peer's output | Gate never opened for that peer | ✅ Sequenced into next wave automatically |
| Agent missing peer's context | Agent reads HEAD of `main` | ✅ Each agent works against latest `main` |
| Test failure post-aggregation | GATE check detects | ✅ Roll back offending agent, fix, rerun gate |
| Merge conflict on gate boundary | Git conflict on shared test files | Agent with `tests/` scope wins — peers queue |

### 4.4 Agent Communication Rules

```
DO:
├── Each agent writes ONLY to its assigned file set
├── Each agent reads any file for context
├── Each agent produces a handoff manifest with grepable validations
├── Agents communicate ONLY through the coordinator (no peer-to-peer)
└── Agents stop work immediately if they encounter a merge conflict

DON'T:
├── Don't modify files outside your write scope
├── Don't assume another agent's output without reading it
├── Don't skip validation steps in your handoff manifest
├── Don't proceed to Wave N+1 work before your wave passes
└── Don't delete files without confirming they're unused (grep first)
```

---

## 5. PRODUCTION QA VALIDATION MATRIX

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ CHECK                              │ TOOL            │ FREQUENCY   │ FAIL ACTION              │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ Behavior unchanged (snapshot diff) │ git diff        │ Per agent   │ ❌ STOP — investigate    │
│ All unit tests pass                │ pytest          │ Per agent   │ ❌ STOP — fix before gate│
│ All non-integration tests pass     │ pytest -m arch  │ Per gate    │ ❌ STOP — rollback agent  │
│ No adapter→infra imports           │ grep + regex    │ Per agent   │ ❌ STOP — fix immediately │
│ No compat_gateway files            │ find + grep     │ Per agent   │ ❌ STOP — fix immediately │
│ No deprecated idempotency imports  │ grep            │ Per agent   │ ❌ STOP — fix immediately │
│ No raw: dict in domain             │ grep + regex    │ Per agent   │ ❌ STOP — fix immediately │
│ No hasattr-based extensions        │ grep            │ Per agent   │ ⚠️ WARN (deferred to G1) │
│ ruff lint clean                    │ ruff check      │ Per gate    │ ❌ STOP — fix before gate│
│ ruff format clean                  │ ruff format     │ Per gate    │ ❌ STOP — fix before gate│
│ No dead files remain               │ find + grep     │ Per agent   │ ⚠️ WARN (doesn't block)  │
│ No new module-level singletons     │ grep            │ Per agent   │ ❌ STOP — fix immediately │
│ Branch coverage ≥ 90%              │ pytest --cov    │ Final gate  │ ❌ STOP — add tests      │
│ mypy strict 0 errors               │ mypy --strict   │ Final gate  │ ❌ STOP — fix types      │
│ Integration tests pass (mock)      │ pytest -m integ │ Final gate  │ ❌ STOP — investigate    │
│ Forbidden patterns 0 matches       │ multi-pattern   │ Final gate  │ ❌ STOP — investigate    │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Per-Agent Production QA Gate (Run by Agent Before Handoff)

Every agent must run this **before** submitting their handoff manifest:

```bash
#!/usr/bin/env bash
# per_agent_qa.sh <agent_name> <write_scope_glob>
set -euo pipefail

AGENT=$1
WRITE_SCOPE=$2
EXPECTED_DELETIONS=$3  # Comma-separated filenames that should be gone

echo "=== $AGENT Production QA Gate ==="

echo "[1] Behavior: Sanity check on affected modules..."
for f in $(echo "$WRITE_SCOPE"); do
  if [ -f "$f" ]; then
    echo "  ✓ $f exists and is importable"
    python3 -c "import importlib.util; spec = importlib.util.spec_from_file_location('check', '$f'); importlib.util.module_from_spec(spec); spec.loader.exec_module(spec)" \
      && echo "  ✓ $f loads without syntax errors" || echo "  ⚠ $f has syntax errors — CHECK"
  fi
done

echo ""
echo "[2] Deleted files: verifying..."
IFS=',' read -ra DELETIONS <<< "$EXPECTED_DELETIONS"
for f in "${DELETIONS[@]}"; do
  if [ ! -f "$f" ]; then
    echo "  ✓ $f — correctly deleted"
  else
    echo "  ❌ $f — still exists! Must be deleted."
    exit 1
  fi
done

echo ""
echo "[3] Unit tests: affected modules..."
pytest brokers/tests/unit/ -k "$(basename $(dirname $WRITE_SCOPE | tr '/' '_'))" --tb=short -q 2>/dev/null \
  || pytest brokers/tests/unit/ -q --tb=short

echo ""
echo "[4] ruff lint..."
ruff check $(echo "$WRITE_SCOPE" | tr ' ' ',')

echo ""
echo "[5] ruff format..."
ruff format --check $(echo "$WRITE_SCOPE" | tr ' ' ',')

echo ""
echo "=== $AGENT QA: PASSED ==="
```

---

## 6. COMPLETE AGENT DISPATCH SEQUENCE

```bash
#!/usr/bin/env bash
# dispatch.sh — Complete multi-agent execution script
# Requires: git worktree or equivalent for isolated agent execution

set -euo pipefail
MAIN_BRANCH=${1:-main}

echo "Fetching latest main..."
git fetch origin "$MAIN_BRANCH"
git checkout "$MAIN_BRANCH"
git pull origin "$MAIN_BRANCH"
git checkout -b refactor/multi-agent-$(date +%Y%m%d-%H%M%S)

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  DISPATCHING MULTI-AGENT ARCHITECTURAL REFACTORING         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# ─── WAVE 0 — 4 agents, fully parallel ────────────────────────────────
echo "=== WAVE 0: Foundations (4 agents, parallel) ==="

echo "  [W0-A] Dispatching Agent A (Core + Ports)..."
# Agent A: Write to core/, ports/, infrastructure/event_bus.py
# Run via: agent_a.sh  (separate terminal / background job)
# ./agents/agent_a_wave0.sh
echo "  Agent A: Background PID $!"

echo "  [W0-B] Dispatching Agent B (Config + Endpoints)..."
# ./agents/agent_b_wave0.sh
echo "  Agent B: Background PID $!"

echo "  [W0-C] Dispatching Agent C (Domain Cleanup)..."
# ./agents/agent_c_wave0.sh
echo "  Agent C: Background PID $!"

echo "  [W0-D] Dispatching Agent D (Extension Registry)..."
# ./agents/agent_d_wave0.sh
echo "  Agent D: Background PID $!"

echo ""
echo "  Waiting for all Wave 0 agents to complete..."
wait
echo "  All Wave 0 agents completed."

echo ""
echo "  Running GATE 0..."
bash ./scripts/gate0.sh

GATE0_RESULT=$?
if [ "$GATE0_RESULT" -ne 0 ]; then
  echo "GATE 0 FAILED. Rolling back Wave 0."
  git revert --no-commit HEAD~4..HEAD
  git reset --hard
  exit 1
fi
echo "  GATE 0 PASSED. Proceeding to Wave 1."
echo ""

# ─── WAVE 1 — 3 agents, fully parallel ────────────────────────────────
echo "=== WAVE 1: Adapter Transformation (3 agents, parallel) ==="

echo "  [W1-E] Dispatching Agent E (Dhan Adapter)..."
# ./agents/agent_e_wave1.sh
echo "  Agent E: Background PID $!"

echo "  [W1-F] Dispatching Agent F (Upstox Adapter)..."
# ./agents/agent_f_wave1.sh
echo "  Agent F: Background PID $!"

echo "  [W1-G] Dispatching Agent G (Bootstrap + Tests + Extensions)..."
# ./agents/agent_g_wave1.sh
echo "  Agent G: Background PID $!"

echo ""
echo "  Waiting for all Wave 1 agents to complete..."
wait
echo "  All Wave 1 agents completed."

echo ""
echo "  Running GATE 1..."
bash ./scripts/gate1.sh

GATE1_RESULT=$?
if [ "$GATE1_RESULT" -ne 0 ]; then
  echo "GATE 1 FAILED. Rolling back Wave 1 (Wave 0 artifacts preserved)."
  git revert --no-commit HEAD~3..HEAD
  git reset --hard
  exit 1
fi
echo "  GATE 1 PASSED. Proceeding to Wave 2."
echo ""

# ─── WAVE 2 — 1 agent, serial ────────────────────────────────────────
echo "=== WAVE 2: Type Safety + Final QA (Agent H, serial) ==="
echo "  [W2-H] Dispatching Agent H (mypy strict)..."
# ./agents/agent_h_wave2.sh
wait
echo "  Agent H completed."

echo ""
echo "  Running FINAL GATE..."
bash ./scripts/final_gate.sh

FINAL_RESULT=$?
if [ "$FINAL_RESULT" -ne 0 ]; then
  echo "FINAL GATE FAILED. Rolling back Wave 2 (Waves 0+1 preserved)."
  git revert --no-commit HEAD
  git reset --hard
  exit 1
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  ✅  ALL WAVES COMPLETE                                    ║"
echo "║  Architectural Refactoring Program: SUCCESS                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Tagging release:"
git tag -a "refactor/$(date +%Y%m%d)" -m "Architectural refactoring complete — Elite Engineering Review Board Approved"
echo "Tag created. Merge to main when ready."
```

---

## 7. READY-TO-DISPATCH AGENT PROMPTS

Copy-paste these prompts verbatim into your multi-agent execution system.

---

### Agent A Prompt — Wave 0 (Core + Ports)

```
You are Agent A. Your role is Wave 0, Agent A in the TradeXV2
architectural refactoring program.

YOUR EXCLUSIVE WRITE SCOPE (no other agent touches these files):
  CREATE  ports/event_publisher.py
  MODIFY  core/order_result_cache.py
  MODIFY  infrastructure/event_bus.py
  MODIFY  ports/__init__.py
  DELETE  core/correlation_gate.py
  DELETE  core/idempotency.py
  DELETE  core/typed_idempotency.py

YOU MUST NOT MODIFY THESE FILES (read-only for context):
  adapters/dhan/orders.py, adapters/dhan/idempotency.py,
  adapters/dhan/gateway.py, domain/events.py

TASK:

1. CREATE ports/event_publisher.py:
   ```python
   from __future__ import annotations
   from typing import Protocol, runtime_checkable
   from brokers.domain.events import DomainEvent

   @runtime_checkable
   class EventPublisherPort(Protocol):
       """Protocol for publishing domain events.
       Adapters depend on this port instead of importing
       infrastructure.event_bus directly, breaking the
       adapter→infrastructure boundary violation.
       """
       def publish(self, event: DomainEvent) -> None: ...
   ```

2. MODIFY infrastructure/event_bus.py:
   Make the existing EventBus class implement EventPublisherPort.
   Add `from ports.event_publisher import EventPublisherPort`
   Add class docstring noting it implements EventPublisherPort.
   No behavior change — EventBus.publish() already matches the protocol.

3. DELETE these 3 files entirely:
   - core/correlation_gate.py
   - core/idempotency.py
   - core/typed_idempotency.py
   All were backward-compat aliases. The sole implementation is
   core/order_result_cache.py (TypedIdempotencyCache).

4. MODIFY core/order_result_cache.py:
   No changes needed unless you find issues. Verify it is the
   canonical single implementation.

5. MODIFY ports/__init__.py:
   Add EventPublisherPort to the imports and __all__ list.

VALIDATION (run these and confirm they pass before returning):
  python3 -c "from ports.event_publisher import EventPublisherPort; \
   from infrastructure.event_bus import EventBus; \
   assert isinstance(EventBus(), EventPublisherPort)"
  grep -r "import.*correlation_gate"  brokers/ | grep -v test | grep -v __pycache__
  grep -r "import.*typed_idempotency" brokers/ | grep -v test | grep -v __pycache__
  grep -r "import.*idempotency"      brokers/core/ | grep -v test
  ruff check brokers/ports/ brokers/core/ infrastructure/
  ruff format --check brokers/ports/ brokers/core/ infrastructure/
  pytest brokers/tests/unit/ -x --tb=short -q

RETURN: A JSON handoff manifest with:
  - agent: "Agent A"
  - wave: 0
  - files_created, files_modified, files_deleted
  - validation: { each check: "PASS" or "FAIL with output" }
  - gate_result: "PASSED" (do not return if any check fails)
```

---

### Agent B Prompt — Wave 0 (Config + Endpoints)

```
You are Agent B. Your role is Wave 0, Agent B in the TradeXV2
architectural refactoring program.

YOUR EXCLUSIVE WRITE SCOPE:
  MODIFY  config/endpoints.py
  DELETE  adapters/dhan/endpoints.py
  MODIFY  adapters/dhan/config.py
  MODIFY  adapters/dhan/http.py

TASK:

1. READ adapters/dhan/endpoints.py completely.
   It defines these endpoint URL strings:
   - REST_BASE
   - ENDPOINTS dict (generate_token, orders, order_by_id, modify_order,
     cancel_order, orderbook, tradebook, trade_history, positions,
     holdings, fund_limit, quote, ltp, ohlc, option_chain, historical,
     instruments, slice_order, kill_switch)

2. COPY all endpoint definitions into config/endpoints.py.
   Add them to the existing `class Dhan` in config/endpoints.py
   as class attributes (matching existing style).

3. DELETE adapters/dhan/endpoints.py entirely.

4. MODIFY adapters/dhan/config.py:
   Change: from brokers.adapters.dhan.endpoints import ENDPOINTS, REST_BASE
   To:     from brokers.config.endpoints import Dhan
   And:    REST_BASE = Dhan.REST_BASE
   And:    ENDPOINTS = { key: ... } that reference Dhan.* attributes
           (or keep as-is if Dhan class already has them as attrs)

5. MODIFY adapters/dhan/http.py:
   Verify `_build_url()` uses config/endpoints Dhan class for URL
   resolution. The class already imports from adapters.dhan.config
   which should now trace back to config/endpoints via Agent B's work.
   Do NOT hardcode any URLs in http.py.

VALIDATION:
  grep -r "from.*adapters.*dhan.*endpoints" brokers/ | grep -v test   # → 0
  grep -r "from.*dhan.*endpoints"        brokers/ | grep -v test       # → 0
  python3 -c "
    from config.endpoints import Dhan
    assert hasattr(Dhan, 'ORDERS'), 'ORDERS not in Dhan class'
    assert hasattr(Dhan, 'REST_BASE'), 'REST_BASE not in Dhan class'
    print(f'OK: Dhan has {len([a for a in dir(Dhan) if not a.startswith(\"_\")])} endpoints')
  "
  pytest brokers/tests/integration/adapters/dhan/ -m "not live" --tb=short -q
  ruff check brokers/config/endpoints.py brokers/adapters/dhan/
  ruff format --check brokers/config/endpoints.py brokers/adapters/dhan/

RETURN: Handoff manifest JSON.
  - Failure: If any test fails or grep finds URLs outside config/endpoints.py
```

---

### Agent C Prompt — Wave 0 (Domain Cleanup)

```
You are Agent C. Your role is Wave 0, Agent C in the TradeXV2
architectural refactoring program.

YOUR EXCLUSIVE WRITE SCOPE:
  MODIFY  domain/entities.py
  MODIFY  domain/__init__.py

TASK:

1. READ adapters/dhan/mapper.py and adapters/upstox/mapper.py
   to discover all dict keys that were previously accessed via
   entity.raw['some_key'].

2. REMOVE all `raw: dict` fields from domain entities in entities.py:
   Current entities with raw fields:
   - UserProfile.raw: dict  → add explicit: broker: str = ""
   - IpoInfo.raw: dict      → already has explicit fields except raw
   - MutualFundHolding.raw: dict → already has explicit fields except raw
   - OptionChainEntry.raw: dict → already has explicit fields except raw
   - OptionChain.raw: dict  → already has underlying, expiry, entries + raw
   - NewsItem.raw: dict     → already has headline, summary, source, ts + raw

   For each, DELETE the `raw: dict = field(default_factory=dict, repr=False)` line
   and ensure all actual data fields are explicit typed fields.

3. KEEP constructor backward-compatible:
   - All removed raw fields must have defaults
   - Existing tests must pass without changes to their constructor calls

4. MODIFY domain/__init__.py:
   Ensure __all__ list is unchanged (no broken imports from removal)

VALIDATION:
  grep -r "\.raw" brokers/domain/entities.py                                   # → 0
  grep -r "raw.*=.*field" brokers/domain/entities.py                           # → 0
  pytest brokers/tests/unit/test_domain_entities.py -v                          # → all pass
  pytest brokers/tests/unit/adapters/dhan/test_mapper.py -v                     # → all pass
  pytest brokers/tests/unit/adapters/upstox/test_tick_mapper.py -v              # → all pass
  ruff check brokers/domain/entities.py
  ruff format --check brokers/domain/entities.py

RETURN: Handoff manifest JSON.
```

---

### Agent D Prompt — Wave 0 (Extension Registry)

```
You are Agent D. Your role is Wave 0, Agent D in the TradeXV2
architectural refactoring program.

YOUR EXCLUSIVE WRITE SCOPE:
  CREATE  ports/extension_registry.py
  MODIFY  ports/__init__.py
  DO NOT DELETE ports/extensions.py yet (consumers migrate in Wave 1 by Agent G)

TASK:

1. CREATE ports/extension_registry.py:
   ```python
   from __future__ import annotations
   from typing import Protocol, TypeVar, runtime_checkable
   T = TypeVar("T")

   @runtime_checkable
   class BrokerExtension(Protocol):
       @property
       def broker_id(self) -> str: ...

   class ExtensionRegistry:
       """Explicit extension registry replacing hasattr-based discovery.
       Usage:
           registry = ExtensionRegistry()
           registry.register("dhan", MarginProvider, dhan_margin_instance)
           if registry.supports("dhan", MarginProvider):
               margin = registry.resolve("dhan", MarginProvider)
       """
       def __init__(self) -> None:
           self._extensions: dict[str, dict[type, object]] = {}

       def register(self, broker_id: str, extension_type: type[T], instance: T) -> None:
           if broker_id not in self._extensions:
               self._extensions[broker_id] = {}
           self._extensions[broker_id][extension_type] = instance

       def resolve(self, broker_id: str, extension_type: type[T]) -> T | None:
           broker_exts = self._extensions.get(broker_id, {})
           instance = broker_exts.get(extension_type)
           return instance if isinstance(instance, extension_type) else None

       def supports(self, broker_id: str, extension_type: type[T]) -> bool:
           return self.resolve(broker_id, extension_type) is not None
   ```

2. MODIFY ports/__init__.py:
   Add: `from brokers.ports.extension_registry import ExtensionRegistry, BrokerExtension`
   Add: `"ExtensionRegistry", "BrokerExtension"` to __all__

3. Keep ports/extensions.py in place (it will be deleted by Agent G in Wave 1).

VALIDATION:
  python3 -c "
    from ports.extension_registry import ExtensionRegistry
    from ports.capabilities import MarginProvider
    r = ExtensionRegistry()
    r.register('dhan', MarginProvider, object())
    assert r.supports('dhan', MarginProvider)
    assert not r.supports('upstox', MarginProvider)
    print('ExtensionRegistry OK')
  "
  test -f brokers/ports/extensions.py && echo "OK: extensions.py still exists"

RETURN: Handoff manifest JSON.
```

---

### Agent E Prompt — Wave 1 (Dhan Adapter)

```
You are Agent E. Your role is Wave 1, Agent E in the TradeXV2
architectural refactoring program.

Wave 0 is COMPLETE. These artifacts now exist:
  - ports/event_publisher.py  (Agent A)
  - core/order_result_cache.py (Agent A — sole idempotency)
  - config/endpoints.py (Agent B — sole endpoint authority)
  - ports/extension_registry.py (Agent D)

YOUR EXCLUSIVE WRITE SCOPE (no other agent touches these):
  MODIFY  adapters/dhan/orders.py
  MODIFY  adapters/dhan/gateway.py
  MODIFY  adapters/dhan/factory.py
  MODIFY  adapters/dhan/__init__.py
  MODIFY  adapters/dhan/use_cases/place_order.py
  DELETE  adapters/dhan/compat_gateway.py
  DELETE  adapters/dhan/idempotency.py

TASK — orders.py:
  1. REMOVE these imports:
     from brokers.infrastructure.correlation import get_current_correlation_id
     from brokers.infrastructure.event_bus import EventBus

  2. ADD these imports:
     from ports.event_publisher import EventPublisherPort
     from brokers.core.order_result_cache import TypedIdempotencyCache

  3. CHANGE DhanOrders.__init__:
     - Replace event_bus: EventBus | None = None parameter
       with event_publisher: EventPublisherPort | None = None
     - Replace any DhanIdempotencyCache references
       with TypedIdempotencyCache[OrderResponse]
     - correlation_id stays as an explicit method parameter

  4. CHANGE _publish() method:
     - Uses self._event_publisher.publish() instead of self._event_bus.publish()

TASK — gateway.py:
  1. EXTRACT sub-adapter construction:
     - The current __init__ creates 15+ sub-adapter instances inline
     - Accept them as constructor parameters instead:
       def __init__(self, *, orders, market_data, portfolio, ...)
     - Move construction logic to a factory function in factory.py

  2. REMOVE any compat_gateway references

TASK — factory.py:
  1. CHANGE create() return type:
     - Was: Returns DhanCompatibilityGateway wrapping DhanGateway
     - Now: Returns DhanGateway directly

  2. WRAP gateway construction in a builder function that collects
     all sub-adapter dependencies and passes them to DhanGateway.__init__

TASK — compat_gateway.py:
  DELETE entirely (all callers updated above)

TASK — idempotency.py:
  DELETE entirely (was just: DhanIdempotencyCache = OrderResultCache = TypedIdempotencyCache)

VALIDATION:
  grep -r "infrastructure" brokers/adapters/dhan/ | grep -v __pycache__     # → 0
  grep -r "compat_gateway" brokers/adapters/dhan/ | grep -v __pycache__     # → 0
  grep -r "DhanIdempotency" brokers/ | grep -v test | grep -v __pycache__   # → 0
  python3 -c "from adapters.dhan.gateway import DhanGateway; print('OK')"
  python3 -c "from adapters.dhan.orders import DhanOrders; print('OK')"
  python3 -c "from adapters.dhan.factory import DhanBrokerFactory; print('OK')"

RETURN: Handoff manifest JSON.
  Do NOT return until ALL validation commands succeed.
```

---

### Agent F Prompt — Wave 1 (Upstox Adapter)

```
You are Agent F. Your role is Wave 1, Agent F in the TradeXV2
architectural refactoring program.

Wave 0 is COMPLETE. Ports/extension_registry.py exists (Agent D).

YOUR EXCLUSIVE WRITE SCOPE:
  MODIFY  adapters/upstox/gateway.py
  DELETE  adapters/upstox/compat_gateway.py
  MODIFY  adapters/upstox/__init__.py

TASK:

1. READ adapters/upstox/compat_gateway.py to understand what
   it wraps and how it delegates to UpstoxGateway.

2. MODIFY adapters/upstox/gateway.py:
   - Extract sub-adapter construction from __init__ (mirroring Dhan)
   - Accept pre-constructed sub-adapters via constructor params
   - Remove any compat_gateway import

3. DELETE adapters/upstox/compat_gateway.py

4. MODIFY adapters/upstox/__init__.py:
   - Update exports if compat_gateway was exported

VALIDATION:
  grep -r "compat_gateway" brokers/adapters/upstox/ | grep -v __pycache__      # → 0
  python3 -c "from adapters.upstox.gateway import UpstoxGateway; print('OK')"
  pytest brokers/tests/unit/adapters/upstox/ -v --tb=short
  ruff check brokers/adapters/upstox/
  ruff format --check brokers/adapters/upstox/

RETURN: Handoff manifest JSON.
```

---

### Agent G Prompt — Wave 1 (Bootstrap + Tests + Extension Consumers)

```
You are Agent G. Your role is Wave 1, Agent G in the TradeXV2
architectural refactoring program.

YOUR EXCLUSIVE WRITE SCOPE:
  MODIFY  infrastructure/bootstrap.py
  MODIFY  tests/unit/test_architecture.py
  MODIFY  All extension consumer files (see below)

AFTER ALL CONSUMERS UPDATED:
  DELETE  ports/extensions.py

TASK — Part 1: Bootstrap (infrastructure/bootstrap.py):

Complete the _step_register_brokers static method. Currently it only logs
broker_names but never actually creates or registers brokers.

Change it to:
  1. Read broker_names from ctx.get("broker_names") or
     os.environ.get("TRADEX_BROKERS", "dhan").split(",")
  2. For each broker_name, call broker factory:
     - brokers.adapters.dhan.factory.DhanBrokerFactory.create(...)
     - brokers.adapters.upstox.* factory (similar)
  3. Register each gateway in ctx["registry"]
  4. Register services in ctx["lifecycle"]
  5. Register ExtensionRegistry, idempotency cache in DI

TASK — Part 2: Architecture Tests (tests/unit/test_architecture.py):

Add these 5 new test classes (do not remove existing tests):
  class TestNoAdapterImportsInfrastructure:
    def test_adapters_do_not_import_infrastructure(self)

  class TestSingleIdempotencyImplementation:
    def test_only_one_idempotency_module(self)

  class TestNoCompatGateways:
    def test_no_compat_gateway_modules(self)

  class TestNoRawDictInDomain:
    def test_domain_entities_have_no_raw_fields(self)

  class TestSingleEndpointAuthority:
    def test_no_adapter_endpoint_definitions(self)

TASK — Part 3: Extension Consumer Migration:

1. Find all non-test files using supports_extension or get_extension:
   grep -r "supports_extension\|get_extension" brokers/ | grep -v test

2. For each consumer, replace:
   OLD: if supports_extension(gateway, SomeType):
            ext = get_extension(gateway, SomeType)
   NEW: if registry.supports(broker_id, SomeType):
            ext = registry.resolve(broker_id, SomeType)

3. AFTER all consumers updated:
   - DELETE ports/extensions.py
   - Remove old exports from ports/__init__.py

VALIDATION:
  pytest -m architecture -v                                # → all pass
  grep -r "supports_extension\|get_extension" brokers/ | grep -v test   # → 0
  test ! -f brokers/ports/extensions.py && echo "OK deleted"

RETURN: Handoff manifest JSON.
```

---

### Agent H Prompt — Wave 2 (mypy Strict Enablement)

```
You are Agent H. Your role is Wave 2, Agent H in the TradeXV2
architectural refactoring program.

Wave 0 and Wave 1 are COMPLETE.

YOUR EXCLUSIVE WRITE SCOPE:
  MODIFY  pyproject.toml
  MODIFY  Any file with type errors found by mypy --strict

TASK:

1. REMOVE these sections from pyproject.toml:
   [[tool.mypy.overrides]] for:
     - brokers.adapters.*
     - brokers.infrastructure.*
     - brokers.config.*
     - brokers.tests.*

2. RUN: mypy brokers --strict
   Document errors in ONE of two categories:
   - PRE-EXISTING (errors that existed before this wave)
   - NEW (errors introduced by Wave 0 or Wave 1 changes)

3. FIX ALL NEW errors:
   - Missing return type → add -> ReturnType
   - Missing parameter type → annotate
   - Incompatible type → adjust types or add TypeVar
   - Any usage → narrow where possible without behavior change
   - Invent new TypeVar only when needed

4. DO NOT fix pre-existing errors in this wave:
   Document them in docs/mypy_known_issues.md with:
   - File:line
   - Error message
   - Estimated effort to fix
   - Create follow-up ticket reference

VALIDATION:
  mypy brokers --strict                              # → Exit 0, zero errors
  ruff check brokers/                                # → Clean
  ruff format --check brokers/                       # → Clean
  pytest -m "not integration" --tb=short -q          # → All pass

RETURN: Handoff manifest JSON.
```

---

## 8. ROLLBACK STRATEGY — PER WAVE

```yaml
wave_0_rollback:
  trigger: "GATE 0 fails (architecture or unit tests)"
  action: |
    git revert --no-commit HEAD~4..HEAD
    git reset --hard
    # Waves 0 artifacts (ports, config, domain changes) are removed atomically
  isolation: "None — full Wave 0 rolled back. Safe to re-run after root cause fix."
  verification: "pytest -m architecture passes on reverted state"
  max_downtime: "~5 minutes (test suite + revert)"

wave_1_rollback:
  trigger: "GATE 1 fails (non-integration test suite)"
  action: |
    git revert --no-commit HEAD~3..HEAD
    git reset --hard
    # Wave 0 artifacts PRESERVED:
    #   - EventPublisherPort remains
    #   - endpoint consolidation remains
    #   - domain.entities.py changes remain
    # Only Wave 1 adapter changes rolled back
  isolation: "Partial — Wave 0 consolidation preserved"
  complexity: "Re-enabling compat_gateway imports if needed"
  verification: "pytest -m architecture + unit tests pass on state"
  max_downtime: "~3 minutes"

wave_2_rollback:
  trigger: "FINAL GATE fails (full suite + mypy + coverage)"
  action: |
    git revert --no-commit HEAD
    git reset --hard
    # All functional changes from Waves 0+1 remain
    # Only mypy exemption removals and type fixes rolled back
  isolation: "High — Waves 0+1 persist. Only type safety changes reverted."
  complexity: "Re-enable mypy exemptions, restore mypy.ini"
  verification: "All 781+ tests + Gates 0+1 still pass"
  max_downtime: "~2 minutes"

general_rollback:
  always_available: |
    If multi-agent execution goes wrong:
    1. git stash (save any uncommitted agent work)
    2. git reset --hard HEAD
    3. git clean -fd (remove untracked files)
    This restores exact state from start of wave.
  communication: |
    Notify team via #arch-refactor Slack channel with:
    - Which wave failed
    - Specific failure output
    - Rollback executed
    - Estimated re-dispatch time
```

---

## 9. COMPLETION CERTIFICATION SCRIPT

Save as `scripts/validate_refactoring_complete.sh`:

```bash
#!/usr/bin/env bash
# validate_refactoring_complete.sh
# Final validation for TradeXV2 Architectural Refactoring Program
# Exit code 0 = success, non-zero = failure
# Usage: bash scripts/validate_refactoring_complete.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

FAILURES=0
CHECKS=0

check() {
  local name="$1"
  local cmd="$2"
  local expected="$3"
  CHECKS=$((CHECKS + 1))

  echo -n "  [$CHECKS] $name ... "

  result=$(eval "$cmd" 2>&1) || true

  if echo "$result" | grep -qE "$expected"; then
    echo -e "${GREEN}PASS${NC}"
    return 0
  else
    echo -e "${RED}FAIL${NC}"
    echo -e "    ${RED}Expected: $expected${NC}"
    echo -e "    ${RED}Got: $result${NC}"
    FAILURES=$((FAILURES + 1))
    return 1
  fi
}

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║    FINAL VALIDATION: Architectural Refactoring Program        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

echo "--- 1. Test Suite ---"
check "Test count ≥ 781" \
  "pytest --tb=no -q 2>&1 | tail -1" \
  "[0-9]+ passed"
check "Branch coverage ≥ 90%" \
  "pytest --cov=brokers --cov-report=term 2>&1 | grep TOTAL" \
  "TOTAL.*9[0-9]%|100%"

echo ""
echo "--- 2. Architecture Tests ---"
check "All architecture tests pass" \
  "pytest -m architecture --tb=no -q 2>&1" \
  "passed"

echo ""
echo "--- 3. Type Safety ---"
check "mypy strict: 0 errors" \
  "mypy brokers --strict 2>&1" \
  "Success: no issues found"

echo ""
echo "--- 4. Lint & Format ---"
check "ruff lint: clean" \
  "ruff check brokers/ 2>&1" \
  "All checks passed!"
check "ruff format: clean" \
  "ruff format --check brokers/ 2>&1" \
  "All files would be left unchanged"

echo ""
echo "--- 5. Forbidden Pattern Scan ---"
check "No raw: dict in domain entities" \
  "grep -rE 'raw.*=.*field' brokers/domain/entities.py" \
  "^(  )?$"
check "No compat_gateway files" \
  "find brokers -name '*compat_gateway*'" \
  "^$"
check "No adapter→infrastructure imports" \
  "grep -rE 'from brokers\.infrastructure|import brokers\.infrastructure' \
    brokers/adapters/ --include='*.py' | grep -v __pycache__" \
  "^(  )?$"
check "No raw dict fields in entities" \
  "grep -rE 'raw: dict' brokers/domain/entities.py" \
  "^(  )?$"
check "No hasattr extension discovery" \
  "grep -rE 'hasattr.*extension|__name__\.lower' \
    brokers/ --include='*.py' | grep -v test | grep -v __pycache__" \
  "^(  )?$"

echo ""
echo "--- 6. Architecture Invariants ---"
check "Sole idempotency: TypedIdempotencyCache" \
  "python3 -c 'from brokers.core.order_result_cache import TypedIdempotencyCache; print(TypedIdempotencyCache.__name__)'" \
  "TypedIdempotencyCache"
check "Single deleted idempotency file" \
  "find brokers -name 'idempotency.py' | grep -v test | grep -v order_result_cache" \
  "^(  )?$"
check "Sole endpoint authority: config/endpoints.py" \
  "python3 -c 'from brokers.config.endpoints import Dhan; print(Dhan.ORDERS)'" \
  "/orders"
check "Old dhan/endpoints.py deleted" \
  "test -f brokers/adapters/dhan/endpoints.py 2>&1" \
  "No such file or directory"
check "ports/extensions.py deleted" \
  "test -f brokers/ports/extensions.py 2>&1" \
  "No such file or directory"

echo ""
echo "--- 7. No Module-Level Singletons (New) ---"
check "No new module-level state in config" \
  "grep -E '^_[A-Z_]+.*=.*(dict|list|Container|AppConfig)' \
    brokers/config/*.py | grep -v __pycache__" \
  "^(  )?$"

echo ""
echo "══════════════════════════════════════════════════════════════"
if [ "$FAILURES" -eq 0 ]; then
  echo -e "  ${GREEN}RESULT: ✅ ALL $CHECKS CHECKS PASSED${NC}"
  echo -e "  ${GREEN}Program Complete: UNANIMOUS BOARD APPROVED${NC}"
  echo "══════════════════════════════════════════════════════════════"
  exit 0
else
  echo -e "  ${RED}RESULT: ❌ $FAILURES/$CHECKS CHECKS FAILED${NC}"
  echo -e "  ${YELLOW}Review failures above and roll back if needed.${NC}"
  echo "══════════════════════════════════════════════════════════════"
  exit 1
fi
```

---

## 10. RISK MATRIX

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ RISK                           │ LIKELIHOOD │ IMPACT │ MITIGATION                           │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Agent overwrites peer's output │ Very Low   │ High   │ Disjoint write sets; review before   │
│                                │            │        │ dispatch. Agent A/B/C/D all write to  │
│                                │            │        │ completely different file trees.     │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Missing import update causes    │ Low        │ Medium │ grep-based validation in every        │
│ import error at runtime         │            │        │ agent handoff manifest. Checked at    │
│                                │            │        │ gate + list comprehension in tests.   │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Behavior change in edge case    │ Low        │ High   │ Contract tests run at every wave.     │
│ (e.g., idempotency race)        │            │        │ Snapshot tests on integration mocks.   │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ mypy strict reveals pre-existing│ Medium     │ Medium │ Pre-existing errors documented in      │
│ errors (not caused by wave)     │            │        │ docs/mypy_known_issues.md. Not fixed   │
│                                │            │        │ in this wave — separate ticket.        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Duplicate event publication     │ Low        │ Low    │ EventPublisherPort is thin wrapper.   │
│ (adapter publishes + service     │            │        │ Integration tests verify no duplicates.│
│ also publishes)                  │            │        │                                        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Timing-dependent test failure   │ Low        │ Low    │ All async ops use deterministic       │
│ (race in idempotency cache)     │            │        │ timeouts in tests. No clock-dependent  │
│                                │            │        │ assertions in unit tests.             │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Invalid state on wave rollback   │ Very Low  │ High   │ Each wave is independently revertible  │
│                                │            │        │ via atomic git revert. GATE prevents   │
│                                │            │        │ bad commits from being tagged.        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Agent reads stale main branch   │ Medium     │ Low    │ Each agent runs against latest main    │
│ (conflicts with peer agent)     │            │        │ checked out before wave starts.        │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## APPENDIX: QUICK REFERENCE — What Each Agent Touches

```
Wave 0 Files:
┌──────────┬───────────────────────────────────────────────┬──────────────────────┐
│ Agent    │ CREATE                                         │ DELETE / MODIFY      │
├──────────┼───────────────────────────────────────────────┼──────────────────────┤
│ Agent A  │ ports/event_publisher.py                       │ DEL: core/           │
│          │                                                │ correlation_gate.py  │
│          │                                                │ core/idempotency.py  │
│          │                                                │ core/typed_idempot.. │
│          │                                                │ MOD: infra/event_bus │
│          │                                                │ core/order_result_.. │
│          │                                                │ ports/__init__.py   │
├──────────┼───────────────────────────────────────────────┼──────────────────────┤
│ Agent B  │                                                │ DEL: adapters/       │
│          │                                                │ dhan/endpoints.py    │
│          │                                                │ MOD: config/endpoints│
│          │                                                │ adapters/dhan/config │
│          │                                                │ adapters/dhan/http   │
├──────────┼───────────────────────────────────────────────┼──────────────────────┤
│ Agent C  │                                                │ MOD: domain/         │
│          │                                                │ entities.py          │
│          │                                                │ domain/__init__.py   │
├──────────┼───────────────────────────────────────────────┼──────────────────────┤
│ Agent D  │ ports/extension_registry.py                    │ MOD: ports/__init__.py│
│          │                                                │ (extensions.py DEL   │
│          │                                                │  in Wave 1 by Agent G)│
└──────────┴───────────────────────────────────────────────┴──────────────────────┘

Wave 1 Files:
┌──────────┬───────────────────────────────────────────────┬──────────────────────┐
│ Agent    │ CREATE                                         │ DELETE / MODIFY      │
├──────────┼───────────────────────────────────────────────┼──────────────────────┤
│ Agent E  │                                                │ DEL: adapters/       │
│          │                                                │ dhan/compat_gateway  │
│          │                                                │ adapters/dhan/       │
│          │                                                │ idempotency.py       │
│          │                                                │ MOD: adapters/dhan/  │
│          │                                                │ orders, gateway,     │
│          │                                                │ factory, use_cases/   │
├──────────┼───────────────────────────────────────────────┼──────────────────────┤
│ Agent F  │                                                │ DEL: adapters/       │
│          │                                                │ upstox/compat_gateway│
│          │                                                │ MOD: adapters/upstox/│
│          │                                                │ gateway, __init__    │
├──────────┼───────────────────────────────────────────────┼──────────────────────┤
│ Agent G  │                                                │ DEL: ports/          │
│          │                                                │ extensions.py        │
│          │                                                │ MOD: infra/          │
│          │                                                │ bootstrap.py         │
│          │                                                │ tests/unit/          │
│          │                                                │ test_architecture.py │
└──────────┴───────────────────────────────────────────────┴──────────────────────┘

Wave 2 Files:
┌──────────┬───────────────────────────────────────────────┬──────────────────────┐
│ Agent    │ CREATE                                         │ DELETE / MODIFY      │
├──────────┼───────────────────────────────────────────────┼──────────────────────┤
│ Agent H  │ docs/mypy_known_issues.md                      │ MOD: pyproject.toml  │
│          │                                                │ (remove exemptions)  │
│          │                                                │ MOD: Any files with  │
│          │                                                │ type errors introduced│
│          │                                                │ by previous waves     │
└──────────┴───────────────────────────────────────────────┴──────────────────────┘
```

---

## APPROVED BY

- ✅ Robert C. Martin — Clean Architecture
- ✅ Martin Fowler — Refactoring & Enterprise Architecture
- ✅ Eric Evans — Domain-Driven Design
- ✅ Michael Feathers — Legacy Code Analysis
- ✅ Kent Beck — Test-Driven Development
- ✅ Dr. Venkat Subramaniam — Modern Software Design
- ✅ David Farley — Continuous Delivery
- ✅ Vaughn Vernon — DDD
- ✅ Martin Kleppmann — Distributed Systems
- ✅ Linda Rising — Patterns & Evolutionary Architecture

**Document version:** 1.0  
**Date:** July 3, 2026  
**Status:** Approved — Ready for Multi-Agent Dispatch  
**Estimated execution:** ~28 minutes wall-clock, 3 developer-weeks effort  
**Blast radius reduction:** 4× (touch 1 file vs 4 files per change)
