# Execution Plan: Broker Layer Refinement

## Phase 0 Summary

**Product scope**: Improve the broker layer by fixing identified bugs, closing ObservabilityProvider gaps, and resolving the dual-port debt — without changing broker behavior for end users.

**Domain changes**: None intended. All fixes are infrastructure/seam-level — domain entities, domain events, and business rules should not change.

**Modules affected**:
- `brokers/common/intelligent_market_gateway.py` — recursion risk, quota allocation
- `brokers/dhan/gateway.py` — already complete, no changes needed
- `brokers/upstox/gateway.py` — add ObservabilityProvider
- `brokers/paper/paper_gateway.py` — add ObservabilityProvider, simulated streams
- `brokers/common/gateway.py` — ObservabilityProvider protocol (already defined)
- `brokers/common/broker_port.py` — reassess P2-1 merge decision
- `brokers/paper/paper_market_data.py` — simulated stream support

**Architecture impact**: Layer boundaries preserved. Only adapter-level changes.

---

## Rationale

The Karpathy loop says: *Every improvement is Measured → Iterated → Revertable → Recorded → Compounded.*

This plan converts the qualitative findings from the broker review into concrete, measurable work items. Each item has a clear metric, a revert strategy (git), and a memory recording step.

**Strategic justification**: The broker layer is the platform's most critical seam. Every trading decision flows through it. Small infrastructure bugs (like the recursion risk) can cause hard-to-debug production failures. Closing ObservabilityProvider gaps makes operational monitoring reliable regardless of which broker is primary. The P2-1 debt determines the entire future architecture of the broker layer.

---

## Dependency Graph

```
Sprint 1 (Foundation — Queue A)
├── Fix recursion risk (_get_legacy_gateway)      ← No dependencies
├── Fix round-robin allocation docstring           ← No dependencies
│
Sprint 2 (Parity — Queue B)
├── Add ObservabilityProvider to Upstox           ← Depends on: ObservabilityProvider protocol (exists in common)
├── Add ObservabilityProvider to Paper            ← Depends on: ObservabilityProvider protocol (exists in common)
│
Sprint 3 (Enhancement — Queue B)
├── Add simulated tick stream to Paper            ← Depends on: Paper gateway refs
│
Sprint 4 (Architecture — Queue C)
├── Assess P2-1 dual-port merge decision          ← Depends on: understanding of both interfaces
│   └── If merge: design and implement merge
│   └── If split: document as permanent
├── Paper CommonBrokerGateway implementation       ← Depends on: P2-1 decision outcome
│
Sprint 5 (Validation — Queue D)
├── Run full test suites after each change
├── Verify contract tests pass for all three brokers
├── Write memory entries for each completed work item
```

---

## Parallel Execution Matrix

| Workstream | Depends On | Can Execute In Parallel | Blocking Items | Owner | Queue |
|------------|-----------|------------------------|----------------|-------|-------|
| Fix recursion risk | None | Yes | None | pragmatic-engineering-advisor | A |
| Fix round-robin docstring | None | Yes | None | pragmatic-engineering-advisor | A |
| ObservabilityProvider — Upstox | None (protocol exists) | Yes | None | broker-auditor | B |
| ObservabilityProvider — Paper | None (protocol exists) | Yes | None | broker-auditor | B |
| Simulated tick stream — Paper | Paper gateway | Yes | None | broker-auditor | B |
| P2-1 dual-port assessment | Understanding both ports | No (alone) | Architecture decision | chief-quant-architect | C |
| Paper CommonBrokerGateway | P2-1 decision | No | P2-1 decision | platform-engineering-director | C |
| Full test suite validation | All changes | No | All implementations | integration-test-coordinator | D |

---

## Critical Path

```
Fix recursion risk (1-2 hours)
      ↓
ObservabilityProvider — Upstox + Paper (2-3 hours each)
      ↓
P2-1 dual-port assessment (2 hours research + ADR)
      ↓
Paper CommonBrokerGateway implementation (if merge or if split requires it)
      ↓
Full test suite validation (CI run)
```

Items NOT on critical path (parallelize):
- Fix round-robin docstring
- Simulated tick stream for Paper
- Memory entries (write after each work item completes)

---

## Execution Schedule

### Queue A — Immediate (Parallel)
1. **Fix `_get_legacy_gateway()` recursion risk** — Add `_seen` set guard. If we've already visited this object instance, return it directly. Prevents infinite loop on mock/wrapped/adapted gateways.
   - **File**: `brokers/common/intelligent_market_gateway.py`
   - **Change**: ~5 lines
   - **Metric**: Gateway handles wrapped/mock objects without recursion
   - **Revert**: `git revert` — single-commit change
   - **Test**: Existing tests for IntelligentMarketDataGateway

2. **Fix round-robin allocation docstring** — Rename method or fix implementation to match its contract. The docstring says "based on quota headroom" but it's simple round-robin.
   - **File**: `brokers/common/intelligent_market_gateway.py`
   - **Change**: Docstring fix or actual quota headroom check
   - **Metric**: Docstring accurately describes behavior
   - **Revert**: Single-commit revert

### Queue B — After Foundation (Parallel)
3. **Implement ObservabilityProvider for Upstox** — Follow Dhan's implementation pattern:
   - `get_connection_status()` — expose WebSocket connection states
   - `get_circuit_breaker_states()` — delegate to broker's circuit breakers
   - `get_token_refresh_metrics()` — delegate to broker's token manager
   - `get_rate_limiter_metrics()` — delegate to rate limiter
   - **File**: `brokers/upstox/gateway.py`
   - **Metric**: Health check integration tests pass for Upstox
   - **Test**: Add to `TestObservabilityProvider` contract suite

4. **Implement ObservabilityProvider for Paper** — Simpler implementation since Paper has no real connections:
   - `get_connection_status()` — return empty dict (no real streams)
   - `get_circuit_breaker_states()` — return empty dict
   - `get_token_refresh_metrics()` — return default zeros
   - **File**: `brokers/paper/paper_gateway.py`
   - **Metric**: Paper gateway passes ObservabilityProvider contract tests
   - **Test**: Add to contract test suite

5. **Add simulated tick streaming to Paper** — Replace no-op stream handles with simulated tick generators:
   - Use `threading.Timer` to periodically call `on_tick` with synthetic `Quote` objects
   - Use deterministic seed per symbol for reproducible testing
   - **File**: `brokers/paper/paper_gateway.py`, `brokers/paper/paper_market_data.py`
   - **Metric**: Paper stream callbacks fire at configured interval
   - **Test**: Subscribe to paper stream, verify callbacks received

### Queue C — Sequential
6. **Assess P2-1 dual-port merge decision** — This is the most consequential architectural decision:
   - Read both interfaces completely: `broker_port.py` vs `gateway.py`
   - Analyze usage patterns: what uses `CommonBrokerGateway` vs `MarketDataGateway`
   - Evaluate the sync-vs-async gap (the real obstacle to merging)
   - Evaluate the QuotaToken dependency (only in CommonBrokerGateway)
   - **Options**:
     - **Option A — Merge**: Create a unified async Protocol that replaces both. This is a major refactoring (3-5 days). Requires updating OMS, CLI, legacy analytics, and all three adapters.
     - **Option B — Split permanently**: Accept the dual-port design as intentional. Document the decision as an ADR. Close the P2-1 ticket.
   - **Deliverable**: ADR at `.qoder/memory/decisions/2026-07-02-P2-1-dual-port-decision.md`
   - **Metric**: Decision documented and approved

7. **Implement CommonBrokerGateway for Paper** (conditional on P2-1 outcome):
   - If P2-1 decides **merge**: delay until merge plan is designed
   - If P2-1 decides **split permanent**: implement `CommonBrokerGateway` protocol compliance on `PaperGateway`
   - **File**: `brokers/paper/paper_gateway.py`
   - **Metric**: Paper passes `CommonBrokerGateway` structural type check

### Queue D — Validation (Continuous)
8. **Run full test suites** — After every change:
   - Unit tests: `cd brokers && python -m pytest tests/ -x -q`
   - Contract tests: `cd brokers && python -m pytest contract/ -x -q`
   - Integration tests (if env available)
   - Type check: `mypy brokers/`
   - **Metric**: All tests pass, no type errors

9. **Write memory entries** — After every completed work item:
   - Write finding/decision to `.qoder/memory/`

---

## Agent Allocation

| Workstream | Agent | Authority |
|-----------|-------|-----------|
| Fix recursion risk | pragmatic-engineering-advisor | May fix without council approval (bug fix) |
| Fix round-robin docstring | pragmatic-engineering-advisor | May fix without council approval (doc fix) |
| ObservabilityProvider — Upstox | broker-auditor | Reports to Platform Engineering Director |
| ObservabilityProvider — Paper | broker-auditor | Reports to Platform Engineering Director |
| Simulated tick stream — Paper | market-data-engineer + broker-auditor | Reports to Head of Trading Systems |
| P2-1 dual-port assessment | chief-quant-architect | Council-level decision |
| Paper CommonBrokerGateway | platform-engineering-director | Reports to Platform Engineering Director |
| Test suite validation | integration-test-coordinator | Runs continuously |
| Memory entries | memory-curator | Validates entry quality |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| _get_legacy_gateway() fix breaks mock handling | Low | High — tests fail | Start by writing a test that reproduces the recursion |
| P2-1 merge reveals unexpected coupling | Medium | High — days of refactoring | Start with assessment, not implementation |
| ObservabilityProvider exposes internal state | Low | Medium — security concern | Only expose what Dhan already exposes |
| Paper simulated streams create threading bugs | Low | Low — test only, not production | Use thread-safe patterns from existing stream code |
| Changes break existing contract tests | Medium | Medium — CI fails | Run tests after every change |

---

## Metrics (Karpathy Loop)

| Metric | Baseline | Target | How to Measure |
|--------|----------|--------|----------------|
| Recursion risk | Present | Removed | `_get_legacy_gateway()` has visited-set guard |
| ObservabilityProvider coverage | Dhan only (1/3) | All 3 brokers | Count `isinstance(gateway, ObservabilityProvider)` passing |
| Paper stream realism | No-op handles | Callbacks fire | `pytest` subscribing and verifying callbacks |
| P2-1 debt | Open ticket | Closed (merge or permanent) | ADR written to `.qoder/memory/decisions/` |
| Test pass rate | Unknown (baseline) | 100% | `pytest` exit code 0 |
| Memory written | 1 finding entry | All work items recorded | Count entries in `.qoder/memory/` |

---

## Estimated Effort

| Sprint | Effort | Parallel Agents | Wall Time |
|--------|--------|----------------|-----------|
| Sprint 1: Foundation | 1-2 hours | 2 agents | ~1 hour |
| Sprint 2: Parity | 4-6 hours | 2 agents | ~3 hours |
| Sprint 3: Enhancement | 2-3 hours | 1 agent | ~3 hours |
| Sprint 4: Architecture | 2 hours + if merge: 3-5 days | 1 agent | 2 hours to decision |
| Sprint 5: Validation | 1 hour per sprint | 1 agent | Continuous |

**Total (excluding P2-1 merge)**: ~10 hours wall time with parallel agents.
**Total (including P2-1 merge)**: 3-5 days wall time if merge is chosen.

---

## Execution Status

| Item | Status | Date |
|------|--------|------|
| 🔴 Fix _get_legacy_gateway() recursion risk | ✅ **Complete** | 2026-07-02 |
| 🟠 Fix round-robin allocation docstring | ✅ **Complete** | 2026-07-02 |
| 🟢 Update ADR-003 docstrings in gateway.py + broker_port.py | ✅ **Complete** | 2026-07-02 |
| 🟢 Add CommonBrokerGateway to Paper + Upstox | ✅ **Complete** | 2026-07-02 |
| 🟢 Add ObservabilityProvider to Upstox + Paper | ✅ **Complete** | 2026-07-02 |
| 🟡 P2-1 dual-port assessment and ADR | ✅ **Complete** | 2026-07-02 |
| 🟢 Simulated tick streaming for Paper | ⏭️ Pending | — |
| 🟢 Full test suite validation | ⏭️ Blocked on project setup | — |
| 🟢 Memory entries | ✅ **Complete** | 2026-07-02 |

**Next recommended action**: Simulated tick streaming for Paper gateway.
