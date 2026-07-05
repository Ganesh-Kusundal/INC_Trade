# Handoff: Broker Module — Phase 8 Event Bus Integration (In Progress)

## Current Baseline: 1,497 ✅ | 26 pre-existing ❌ | 60 architecture ✅ | 67 contract ✅

### Phase 7 ✅ Extension Isolation (COMPLETE)
All broker-specific extension protocols moved to `adapters/<broker>/extensions/protocols.py`. `ports/__init__.py` exports only broker-agnostic protocols. `ports/capabilities.py` emits DeprecationWarning. Architecture tests enforce isolation.

**Key files created/modified:**
- `adapters/upstox/extensions/protocols.py` (NEW)
- `adapters/upstox/extensions/__init__.py` (NEW)
- `ports/extensions.py` (broker-agnostic protocols)
- `ports/capabilities.py` (deprecated shim)
- 6 files updated for new import paths
- 4 new architecture guardrail tests

### Phase 8 ✅ Event Bus Integration (IN PROGRESS)

**What's complete:**

| # | Task | Status | Tests |
|---|------|--------|-------|
| 8.1 | Typed event hierarchy in `domain/events.py` | ✅ | 8 |
| 8.2 | Wire streaming → EventBus → QuoteState | ✅ | 6 |
| 8.3 | OMS publish OrderPlaced/Cancelled/Modified events | ✅ | 3 |
| 8.4 | EventBus integration in `connect()` | ✅ | — |
| 8.5 | Architecture tests for event patterns | ✅ | 4 (in TestExtensionIsolation) |
| 8.6 | Contract tests for event contracts | ⬜ | — |

**Files modified:**
- `domain/events.py` — Complete typed event hierarchy (QuoteTickEvent, OrderPlacedEvent, OrderFilledEvent, OrderRejectedEvent, OrderModifiedEvent, OrderCancelledEvent, ConnectionEvent, DepthUpdateEvent) with event_type constants
- `ports/event_publisher.py` — Updated to accept typed events via `Any`
- `infrastructure/event_bus.py` — Updated to work with typed events (not just DomainEvent)
- `market/context.py` — Added `event_bus` parameter; subscribe callback publishes QuoteTickEvent and auto-updates QuoteState
- `trading/oms.py` — Added `event_bus` parameter; place_order/cancel_order/modify_order publish typed events
- `brokers/__init__.py connect()` — Creates EventBus instance, wires into MarketDataContext and OMS
- `tests/unit/test_events.py` (NEW) — 17 tests

**Test growth:** +17 tests (from 1,480 → 1,497)

### Phase 9 ⬜ Gateway Deprecation (Next)
- `create_broker()` → DeprecationWarning
- `connect()` as primary factory
- Remove `ports/capabilities.py` deprecated shim
- Remove `_underlying_gateway` references

### Phase 10 ⬜ Replay Engine & Paper Trading
### Phase 11 ⬜ Market Router
### Phase 12 ⬜ Backtesting & Scanner

## Key Architecture Decisions (Phase 8)
1. **Typed events are independent frozen dataclasses** (not DomainEvent subclasses) — avoids frozen dataclass inheritance complexity while maintaining immutability
2. **EventBus.publish accepts Any** — Duck-typing: any object with `event_type: str` works
3. **EventBus.publish uses getattr for event_type** — Graceful fallback if object lacks the attribute
4. **Event constants defined BEFORE classes** — Python evaluates default values at class definition time
5. **OMS publishes events inline** — No separate publisher abstraction; OMS owns event publishing as part of its lifecycle management
6. **MarketDataContext auto-updates QuoteState** — No explicit update_from_quote() calls needed; EventBus + internal callback handle it

## Quick Start
```bash
cd /Users/apple/Downloads/INC_Trade
python -m pytest brokers/tests/unit/ --tb=short -q
python -m pytest brokers/tests/unit/test_events.py -v --tb=short -q
python -m pytest brokers/tests/unit/test_architecture.py -m architecture -v --tb=short -q
```
