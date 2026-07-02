# ADR-003: P2-1 Dual-Port Assessment — MarketDataGateway vs CommonBrokerGateway

**Date**: 2026-07-02
**Status**: Assessment Complete — Recommendation: **Split Permanently (Keep Both)**

---

## Context

The codebase has two coexisting gateway abstractions:

| Port | Type | File | Purpose |
|------|------|------|---------|
| `MarketDataGateway` | ABC | `brokers/common/gateway.py` | **Producer contract** — what broker adapters implement |
| `CommonBrokerGateway` | Protocol | `brokers/common/broker_port.py` | **Consumer contract** — what infrastructure consumes |

Previously tracked as **P2-1 technical debt** with the assumption they should eventually be merged. This ADR evaluates whether that merge is still the right path.

---

## Approach

1. Read both interfaces line-by-line
2. Catalog all consumers of each interface
3. Analyze the adapter bridge
4. Evaluate effort, risk, and value of merging
5. Make a recommendation

---

## Interface Comparison

### MarketDataGateway (ABC) — 8 ISP interfaces, ~30 methods

```python
class MarketDataGateway(
    MarketDataProvider,      # history, quote, ltp, depth
    DerivativesProvider,     # option_chain, future_chain
    BatchMarketDataProvider, # ltp_batch, quote_batch, history_batch
    TradingExecutor,        # place_order, cancel_order, modify_order, get_orderbook, get_trade_book
    PortfolioReader,        # positions, holdings, funds, trades
    InstrumentProvider,     # search, load_instruments
    StreamProvider,         # stream, stream_depth, stream_order
    LifecycleAware,         # describe, capabilities, close
    ABC
): ...
```

**Key characteristics:**
- Sync (blocking I/O)
- Flat parameter style: `place_order(symbol, exchange, side, quantity, ...)`
- Returns mixed types: domain entities + `pd.DataFrame` (history)
- No quota awareness
- Has batch methods: `ltp_batch`, `quote_batch`, `history_batch`
- Has derivative methods: `option_chain`, `future_chain`

### CommonBrokerGateway (Protocol) — ~13 methods

```python
@runtime_checkable
class CommonBrokerGateway(Protocol):
    # Identity: broker_id, list_capabilities, supports
    # Order execution: place_order(OrderRequest, *, quota), cancel_order(order_id, *, quota), modify_order
    # Portfolio: get_positions, get_margins, get_orders, get_trades
    # Market: get_quote_snapshot, get_depth_snapshot
    # Historical: get_historical_bars(HistoricalBarRequest, *, quota)
    # Stream factories: open_market_stream, open_order_stream
    # Lifecycle: health, close
    ...
```

**Key characteristics:**
- Async (coroutines)
- Object parameter style: `place_order(request: OrderRequest, *, quota: QuotaToken)`
- Returns domain entities only (no pandas)
- **Requires QuotaToken on every mutating/quota-consuming call**
- No batch methods
- No derivative methods (option_chain, future_chain)
- Stream model uses `open_*_stream(BrokerStreamPlan)` → `BrokerStreamHandle`
- No `modify_order` (consumer uses extension pattern)

---

## Consumer Analysis

### MarketDataGateway is implemented BY:

| Consumer | Relationship | Notes |
|----------|-------------|-------|
| `BrokerGateway` (Dhan) | Extends ABC | 48-line class declaration |
| `UpstoxBrokerGateway` | Extends ABC | 68-line class declaration |
| `PaperGateway` | Extends ABC | 38-line class declaration |
| `IntelligentMarketDataGateway` | Extends ABC | Smart routing facade |

Total: **4 implementations** — all broker adapters + the smart routing layer.

### MarketDataGateway is imported BY:

| Consumer | File | Usage |
|----------|------|-------|
| Factory | `brokers/common/factory.py` | `create()` returns `MarketDataGateway` |
| Dhan Factory | `brokers/dhan/factory.py` | Returns `MarketDataGateway` |
| Upstox Factory | `brokers/upstox/factory.py` | Returns `MarketDataGateway` |
| Bootstrap | `brokers/common/bootstrap.py` | Type annotation for gateways |
| Download Engine | `brokers/common/services/download_engine.py` | Consumer: `gw: MarketDataGateway = PaperGateway()` |
| Broker Contract | `brokers/common/contracts/broker_contract.py` | Test suite fixture type |
| Extension Bundles | `brokers/*/common_extensions.py` | Consumer of specific methods |
| Adapter Bridge | `brokers/common/adapters/market_data_gateway_adapter.py` | Wraps to CommonBrokerGateway |
| Observability | `brokers/common/observability/health_check.py` | Instances check |
| Test Suites | Various test files | Fixture types and mock targets |

### CommonBrokerGateway is consumed BY:

| Consumer | File | Relationship |
|----------|------|-------------|
| `BrokerInfrastructure` | `brokers/common/infrastructure.py` | `gateway_for()` returns `CommonBrokerGateway` |
| `BrokerRegistry` | `brokers/common/registry.py` | Stores `CommonBrokerGateway` instances |
| `HistoricalDataCoordinator` | `brokers/common/historical_coordinator.py` | Calls `get_historical_bars()` |
| `StreamOrchestrator` | `brokers/common/stream_orchestrator.py` | Calls `open_market_stream()`, `open_order_stream()` |
| `QuotaScheduler` | `brokers/common/quota_scheduler.py` | Uses `QuotaToken` |
| Dhan Gateway | `brokers/dhan/gateway.py` | Provides `common_broker_gateway()` method |
| In-Memory Gateway | `brokers/common/tests/fixtures/in_memory_gateway.py` | Test implementation of Protocol |

Consumers of `QuotaToken` only: Extension bundles (fundamentals, news, super_order, common_extensions).

---

## The Adapter Bridge

`MarketDataGatewayAdapter` (`brokers/common/adapters/market_data_gateway_adapter.py`) wraps a sync `MarketDataGateway` into a `CommonBrokerGateway`-compatible object:

```
MarketDataGateway (sync)
    ↓ wrap_market_gateway()
MarketDataGatewayAdapter
    ↓ satisfies structural typing
CommonBrokerGateway (Protocol)
    ↓ consumed by
BrokerInfrastructure, BrokerRegistry, HistoricalCoordinator, StreamOrchestrator
```

The bridge uses `asyncio.to_thread()` to convert sync→async for every method. This is a thin, correct, zero-coupling translation layer:

```python
async def place_order(self, request, *, quota):
    return await asyncio.to_thread(self._place_order_sync, request)

def _place_order_sync(self, request):
    kwargs = { ... }
    return self._gateway.place_order(**kwargs)
```

---

## Merge Analysis

### What a merge would require:

| Item | Effort | Risk |
|------|--------|------|
| **Sync vs Async**: Must pick one. All 3 gateway implementations are sync. Infrastructure consumers are async. | **3-5 days** — rewrite all gateways to async, update all tests | **High** — touches every broker adapter |
| **QuotaToken**: Must either add to MarketDataGateway (breaking all tests) or drop from CommonBrokerGateway (breaking QuotaScheduler) | **2-3 days** — either add quota to all gateways or change QuotaScheduler | **High** — core infrastructure change |
| **pandas return types**: `MarketDataGateway.history()` returns `pd.DataFrame`. `CommonBrokerGateway.get_historical_bars()` returns `Sequence[HistoricalBar]`. | **1-2 days** — change history() to return domain types, update all consumers | **Medium** — CLI and analytics consumers use DataFrame |
| **Batch methods**: CommonBrokerGateway has none. MarketDataGateway has 3. | Would need to add to Protocol or drop from ABC | **Low** — batch is an optimization, not semantic |
| **Derivative methods**: option_chain, future_chain not in Protocol | Would need to add to Protocol | **Low** — straightforward addition |
| **Stream model**: Two different patterns | **1-2 days** — merge stream models | **Medium** — Orchestrator currently uses Protocol |
| **Parameter style**: Flat vs object | Pure mechanical transformation | **Low** — well-defined |
| **Test suites**: All contract tests use `MarketDataGateway` type | **2-3 days** — rewrite contract test fixtures | **Medium** — extensive test surface |

**Total estimated effort**: **10-18 days** for a complete merge.

**Total risk**: **High** — regression risk across all 3 broker adapters, infrastructure, OMS, CLI, analytics, and test suites.

### What NOT merging costs:

| Cost | Severity |
|------|----------|
| Two interfaces to learn | 🟢 Low — well-documented, clear producer/consumer split |
| Adapter bridge maintenance | 🟢 Low — 325 lines, rarely changed |
| New brokers must implement MarketDataGateway + optionally expose CommonBrokerGateway | 🟢 Low — Dhan does this in one `common_broker_gateway()` method (20 lines) |
| Someone might try to merge them anyway | 🟡 Medium — resolved by documenting this ADR |

---

## Decision: Split Permanently

**The producer/consumer separation is intentional, correct, and beneficial.**

### Rationale

1. **Different concerns, different contracts**: MarketDataGateway is "what broker adapters must implement." CommonBrokerGateway is "what infrastructure needs to consume." These are fundamentally different concerns.

2. **The adapter bridge is not debt — it's a seam**: `asyncio.to_thread()` is the correct way to bridge sync↔async. Removing the bridge would only make the code less flexible, not more correct.

3. **QuotaToken is an infrastructure concern**: It shouldn't appear in the producer interface. Gateway implementations shouldn't know about quota scheduling.

4. **Merge would create coupling**: If merged, every gateway implementation would need async, QuotaToken, and object-style parameters — even paper trading. This adds friction to adding new brokers.

5. **Current architecture is proven**: 3 broker implementations, 35+ common tests, integration tests. All work correctly with the dual-port model.

### What to do instead of merging

| Action | Priority | Effort |
|--------|----------|--------|
| **Update docstring** in both interfaces: replace "will be merged" with "intentionally separate (see ADR-003)" | **Immediate** | 10 minutes |
| **Close P2-1 ticket** | **Immediate** | 1 minute |
| **Add CommonBrokerGateway to Paper** | 🟢 Low | 2-3 hours — would complete the seam |
| **Add CommonBrokerGateway to Upstox** | 🟢 Low | 1 hour — Upstox infrastructure consumers need it |
| **Document pattern** in repowiki for new broker development | 🟡 Medium | 30 minutes |

---

## Consequences

- All 3 current gateway implementations remain unchanged
- The adapter bridge stays in place
- New brokers: implement `MarketDataGateway` ABC → wrap via `wrap_market_gateway()` → get `CommonBrokerGateway` for free
- Infrastructure (OMS, orchestration, historical) continues consuming the Protocol
- The producer/consumer boundary is now documented as intentional, not debt

---

## References

- `brokers/common/gateway.py` — MarketDataGateway ABC
- `brokers/common/broker_port.py` — CommonBrokerGateway Protocol
- `brokers/common/adapters/market_data_gateway_adapter.py` — Adapter bridge
- `brokers/common/bootstrap.py` — Bootstrap wiring showing both types
- `brokers/common/common_broker_access.py` — Utility functions
- `brokers/dhan/gateway.py` — `common_broker_gateway()` method (lines 66-70)
