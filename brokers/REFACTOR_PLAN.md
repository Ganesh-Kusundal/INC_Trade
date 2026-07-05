# Broker Architecture Refactoring Plan

## Phase 1: Problem Assessment

### Issues Identified

| # | Issue | Severity | Location |
|---|-------|----------|----------|
| 1 | God Object: `DhanGatewayBuilder` wires 13 attributes | High | `adapters/dhan/gateway.py:262-392` |
| 2 | Facade delegation: direct `gateway.xxx` access | High | `services/broker_facade.py:263-286` |
| 3 | `getattr` anti-pattern in facade init | Medium | `services/broker_facade.py:79` |
| 4 | `getattr` anti-pattern in session | Medium | `services/broker_session.py:93,102` |
| 5 | Manual retry loop, no circuit breaker | Medium | `services/broker_session.py:135-176` |
| 6 | `create_broker()` does manual construction | Low | `brokers/__init__.py` |
| 7 | Contract tests incomplete | Low | `brokers/tests/contract/` |

### Impact Analysis

**Modules Affected:**
- `brokers/adapters/dhan/` — builder pattern
- `brokers/services/` — facade, session
- `brokers/resilience/` — circuit breaker (exists but unused in session)
- `brokers/tests/contract/` — test coverage

**Dependencies:**
- Facade depends on `BrokerGateway` protocol
- Session depends on facade
- Builder creates all adapter components

---

## Phase 2: Target State Design

### Issue 1: God Object Decomposition

**Current:** `DhanGatewayBuilder.build()` wires 13+ attributes inline

**Target:** Split into focused factory classes:

```
DhanGatewayBuilder
├── DhanAuthFactory      → auth, token_store
├── DhanClientFactory    → http_client, connection_manager
├── DhanServiceFactory   → orders, market_data, portfolio, instruments, historical, options
├── DhanStreamingFactory → streaming, order_stream, depth streams
└── DhanHealthFactory    → health_reporter
```

**Migration Path:**
1. Create factory classes in `brokers/adapters/dhan/factories/`
2. Refactor `DhanGatewayBuilder.build()` to delegate to factories
3. Verify all tests pass
4. Remove inline wiring

---

### Issue 2: Facade Delegation Cleanup

**Current:**
```python
def capabilities(self) -> Any:
    return self._gateway.capabilities  # direct access

@property
def auth(self) -> Any:
    return self._gateway.auth  # direct access

@property
def streaming(self) -> Any:
    return self._gateway.streaming  # direct access

def close(self) -> None:
    self._gateway.close()  # direct access
```

**Target:** Route through service layer or remove if unnecessary

**Options:**
- **Option A:** Add `CapabilityService`, `AuthService`, `StreamingService`, `LifecycleService`
- **Option B:** Remove properties if facade doesn't need them (consumers use `BrokerSession`)
- **Option C:** Keep as deprecated, route through session only

**Recommendation:** Option B — Remove direct delegation. `BrokerSession` is the public API.

---

### Issue 3: `getattr` Anti-Pattern

**Current:**
```python
# broker_facade.py:79
self._options_service = OptionsService(getattr(gateway, "options", None))

# broker_session.py:93,102
return getattr(self._facade, "streaming", self._facade)
return getattr(self._facade, "auth", self._facade)
```

**Target:** Use protocol `None` checks or explicit capability detection

**Fix:**
```python
# Use protocol's Optional return
self._options_service = OptionsService(gateway.options)  # options is Optional[OptionsPort]

# Session: check facade attribute directly
if self._facade is not None and hasattr(self._facade, 'streaming'):
    return self._facade.streaming
```

---

### Issue 4: Circuit Breaker Integration

**Current:**
```python
# broker_session.py:135-176
for attempt in range(3):
    try:
        disconnect()
        break
    except Exception:
        time.sleep(0.1)
```

**Target:** Use existing `CircuitBreaker` from `resilience/`

**Implementation:**
```python
from brokers.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

class BrokerSession:
    def __init__(self, ...):
        self._close_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
            success_threshold=1,
        )
    
    def close(self) -> None:
        if self._close_breaker.state == CircuitState.OPEN:
            logger.warning("Circuit open, skipping close")
            return
        
        try:
            self._close_breaker.record_success()
            # actual close logic
        except Exception as e:
            self._close_breaker.record_failure()
            raise
```

---

### Issue 5: Contract Tests Completion

**Current:** `test_broker_contract.py` exists with mock adapter

**Target:** Full contract test suite:

```
brokers/tests/contract/
├── __init__.py
├── test_broker_contract.py        ✓ exists
├── test_order_contract.py         ← missing
├── test_market_data_contract.py   ← missing
├── test_historical_contract.py    ← missing
├── test_streaming_contract.py     ← missing
├── test_portfolio_contract.py     ← missing
├── test_instruments_contract.py   ← missing
└── test_options_contract.py       ← missing
```

---

## Phase 3: Implementation Order

### Sprint 1: Facade Cleanup (2-3 hours)

1. **Remove direct gateway delegation** from `BrokerFacade`
   - Delete `capabilities()`, `auth`, `streaming`, `close()`
   - Update `BrokerSession` to not depend on these facade properties

2. **Fix `getattr` patterns**
   - Replace `getattr(gateway, "options", None)` with `gateway.options`
   - Replace `getattr(self._facade, "streaming", ...)` with direct checks

3. **Update tests**
   - Fix any tests depending on removed facade properties

---

### Sprint 2: Builder Decomposition (3-4 hours)

1. **Create factory classes**
   ```python
   # brokers/adapters/dhan/factories/__init__.py
   from .auth_factory import DhanAuthFactory
   from .client_factory import DhanClientFactory
   from .service_factory import DhanServiceFactory
   from .streaming_factory import DhanStreamingFactory
   from .health_factory import DhanHealthFactory
   ```

2. **Refactor `DhanGatewayBuilder.build()`**
   - Delegate to factories
   - Verify `__init__` stays < 30 lines

3. **Add architecture test**
   ```python
   class TestBuilderDecomposition:
       def test_builder_wiring_delegated(self):
           """Builder must not set attributes directly."""
           # Verify factory usage
   ```

---

### Sprint 3: Circuit Breaker Integration (2-3 hours)

1. **Refactor `BrokerSession.close()`**
   - Replace manual retry with `CircuitBreaker`
   - Add configurable retry policy

2. **Add `ClosePolicy` config**
   ```python
   @dataclass
   class ClosePolicy:
       max_retries: int = 3
       backoff_ms: int = 100
       circuit_breaker: bool = True
   ```

3. **Test circuit breaker behavior**
   - Test open circuit skips close
   - Test half-open state transitions
   - Test failure counting

---

### Sprint 4: Contract Tests (3-4 hours)

1. **Create missing contract test files**
   - `test_order_contract.py`
   - `test_market_data_contract.py`
   - `test_historical_contract.py`
   - `test_streaming_contract.py`
   - `test_portfolio_contract.py`
   - `test_instruments_contract.py`
   - `test_options_contract.py`

2. **Validate all adapters pass**
   - Dhan
   - Upstox
   - Paper

---

## Phase 4: Validation Checklist

### Architecture Gates

- [ ] No direct `gateway.xxx` access in facade
- [ ] Builder delegates to factories
- [ ] `getattr` patterns eliminated
- [ ] Circuit breaker used in session close
- [ ] All contract tests pass
- [ ] `TestNoHasattrOnGateway` still passes
- [ ] `TestNoAdapterImportsService` still passes

### Test Gates

- [ ] Unit tests: `pytest -m "not integration"` — all pass
- [ ] Architecture tests: `pytest -m architecture` — all pass
- [ ] Contract tests: `pytest -m contract` — all pass
- [ ] Coverage ≥ 90% for changed files

### Trading Workflow Gates

- [ ] `create_broker("dhan")` still works
- [ ] `broker.place_order()` still works
- [ ] `broker.close()` still works with circuit breaker
- [ ] No regressions in live trading scenarios

---

## Phase 5: ADR Template

```markdown
# ADR-XXX: Broker Architecture Cleanup

## Status
Proposed

## Context
Remaining architectural debt from initial refactoring:
- God Object in builder
- Direct gateway delegation in facade
- Missing circuit breaker integration
- Incomplete contract tests

## Decision
1. Decompose builder into focused factories
2. Remove direct gateway access from facade
3. Integrate circuit breaker in session close
4. Complete contract test suite

## Consequences
- Positive: Cleaner separation of concerns
- Positive: Better testability
- Positive: Resilience patterns applied consistently
- Negative: Short-term refactoring effort (10-14 hours)
- Risk: Must verify all adapters still pass contract tests
```

---

## Summary

| Phase | Effort | Risk | Impact |
|-------|--------|------|--------|
| Facade Cleanup | 2-3h | Low | High |
| Builder Decomposition | 3-4h | Medium | High |
| Circuit Breaker | 2-3h | Low | Medium |
| Contract Tests | 3-4h | Low | Medium |
| **Total** | **10-14h** | **Low-Medium** | **High** |

**Recommended Start:** Sprint 1 (Facade Cleanup) — highest impact, lowest risk.
