# Finding: Broker Architecture Review — Dhan, Upstox, Paper

**Date**: 2026-07-02
**Discovered During**: Comprehensive system walkthrough using the Karpathy agent system (memory-read, repo-graph structural analysis, codebase cartography)
**Method**: Read 10 key interface/gateway files, analyzed module tree (brokers/), reviewed STEP 1 analysis from earlier session

---

## 1. Architecture Overview

The brokers module implements a **hexagonal architecture** with two coexisting port abstractions:

| Port | Type | Used By | Status |
|------|------|---------|--------|
| `MarketDataGateway` (ABC) | `brokers/common/gateway.py` | Legacy CLI, analytics, paper broker | **Primary contract** — 8 ISP interfaces composed into one ABC |
| `CommonBrokerGateway` (Protocol) | `brokers/common/broker_port.py` | OMS, execution layer, trading orchestrator | **Newer contract** — structural typing, cleaner API |

**Adapters:**
- `brokers/dhan/gateway.py` → `BrokerGateway`
- `brokers/upstox/gateway.py` → `UpstoxBrokerGateway`
- `brokers/paper/paper_gateway.py` → `PaperGateway`

---

## 2. Finding: Two-port design is a known debt (P2-1)

The codebase intentionally maintains two gateway abstractions. `broker_port.py` docstring explicitly states: *"The two interfaces will be merged in a future release (tracked as P2-1 technical debt)."*

The adapter bridge lives in `brokers/common/common_broker_access.py` via `wrap_market_gateway()`.

**Risk**: Low — both interfaces are maintained and tested. But new contributors must understand both.

**Symptom**: `CommonBrokerGateway` uses `async` methods + `QuotaToken`; `MarketDataGateway` uses sync methods + no quota. The OMS uses the async Protocol; the CLI uses the sync ABC.

---

## 3. Finding: Dhan has the richest implementation

**BrokerGateway** (`brokers/dhan/gateway.py`):
- Full `ObservabilityProvider` implementation (connection status, circuit breakers, token refresh metrics)
- Deep streaming support: depth_20 WS, depth_200 WS, SubscriptionEngine
- Extended capabilities via `DhanExtendedCapabilities` (super orders, forever orders, conditional triggers, EDIS, IP management, ledger)
- GatewayOptionsFacade for broker-agnostic options access
- 2,900+ lines across gateway + connection + adapters
- Test suite: 58 unit tests, 20 integration tests, contract tests

**Notable strengths:**
- `cancel_order()` has post-cancellation verification (H1 fix) — detects race condition where order fills between cancel send and response
- `_complete_depth_snapshot()` merges WS depth + REST fallback
- `_get_legacy_gateway()` resolves through mock objects safely

---

## 4. Finding: Upstox has the cleanest adapter split

**UpstoxBrokerGateway** (`brokers/upstox/gateway.py`):
- Clean adapter pattern: `MarketDataAdapter`, `HistoricalAdapter`, `StreamManagerAdapter`, `PortfolioAdapter`
- Each adapter is a separate class with single responsibility
- Order pipeline: `place_order()` → `OrderCommandAdapter` → V3 API with idempotency
- `UpstoxExtendedCapabilities` for IPOs, P&L, mutual funds, news, kill switch, static IP
- V3 WebSocket with protobuf decoding
- Test suite: 51 unit tests, 19 integration tests, contract tests

**Notable strengths:**
- Security guards: `analytics_only` and `allow_live_orders` settings prevent accidental live orders
- Instrument key resolution: index → instrument master → fallback chain
- Depth stream translates raw ticks to canonical `MarketDepth`

**Notable gaps:**
- No `ObservabilityProvider` implementation (Dhan has this)
- Less comprehensive post-cancellation verification (added but less robust than Dhan's)

---

## 5. Finding: Paper broker is thorough but has some gaps

**PaperGateway** (`brokers/paper/paper_gateway.py`):
- Full `MarketDataGateway` implementation with simulated data
- `PaperMarketData`, `PaperOrders`, `PaperPortfolio` — each a standalone module
- Synthetic OHLCV generation using `numpy` with deterministic seeds per symbol
- Option chain and futures chain with simulated strikes/pricing
- Seed methods for test setup (`seed_orders`, `seed_trades`, `seed_positions`, `seed_holdings`)

**Notable gaps:**
- Stream methods return no-op handles (no simulated tick streaming)
- No `CommonBrokerGateway` Protocol compliance — only `MarketDataGateway` ABC
- `history()` generates purely synthetic data (no real market correlation)
- No `ObservabilityProvider` implementation

---

## 6. Finding: Common infrastructure is well-factored

| Module | Purpose | Quality |
|--------|---------|---------|
| `broker_port.py` | CommonBrokerGateway Protocol | ✅ Clean, well-documented |
| `gateway.py` | MarketDataGateway ABC | ✅ Legacy but maintained |
| `gateway_interfaces.py` | ISP interfaces + SPI ports | ✅ 21 focused interfaces |
| `intelligent_market_gateway.py` | Smart routing facade | ⚠️ Complex, two modes |
| `common_broker_access.py` | Bridge adapter | ✅ Thin, correct |
| `bootstrap.py` | Wiring composition | ✅ Production bootstrap |
| `infrastructure.py` | BrokerInfrastructure DI | ✅ Clean container |

---

## 7. Finding: IntelligentMarketDataGateway is the most complex module

The `IntelligentMarketDataGateway` (600+ lines) has two modes:
- **smart=True**: Uses BrokerRouter + QuotaScheduler + HistoricalDataCoordinator
- **smart=False**: Direct delegation to primary broker

**Risks:**
- `_allocate_symbols_to_brokers()` uses simple round-robin — no actual quota headroom checking despite the docstring claim
- `_get_legacy_gateway()` has infinite recursion risk: recursive call with same argument, no mutation
- History method in smart mode uses `run_async_compat` but historical coordinator is async-native
- Trading operations always use primary broker — routing is only for market data

---

## 8. Module Dependency Map (from codebase-cartographer analysis)

```
Layer 0 (Domain):    domain/             ← no broker imports
Layer 1 (Ports):     brokers/common/      ← imports domain only
Layer 2 (Adapters):  brokers/dhan/        ← imports common + domain
                     brokers/upstox/      ← imports common + domain
                     brokers/paper/       ← imports common + domain
Layer 3 (Infra):     infrastructure/      ← imports any layer
```

**Key seams (2+ adapters):**
- `MarketDataGateway` — Dhan, Upstox, Paper (3 adapters) ✅
- `CommonBrokerGateway` — Dhan wraps via adapter, others not tracked
- `BatchFetchMixin` — All 3 gateways
- `ObservabilityProvider` — Dhan only (Upstox and Paper missing)

---

## 9. Recommendations

| Priority | Issue | Recommendation |
|----------|-------|---------------|
| **🔴** | `_get_legacy_gateway()` infinite recursion risk | Add a visited-set guard or depth limit |
| **🟠** | `ObservabilityProvider` only implemented by Dhan | Implement for Upstox and Paper for consistent CLI observability |
| **🟠** | Round-robin allocation pretends to check quota | Implement actual quota headroom check or rename method |
| **🟡** | P2-1 dual-port debt | Assess if merge is still planned or if the split is permanent |
| **🟡** | Paper broker missing CommonBrokerGateway | Implement for consistency — would enable paper in OMS pipeline |
| **🟢** | Paper streams return no-op | Add simulated tick callback for more realistic testing |
| **🟢** | Test suite counts | Dhan: 58 unit + 20 integration, Upstox: 51 unit + 19 integration, Paper: 1 test, Common: 35+ tests |

**Overall health**: The broker layer is well-architected with clean hexagonal boundaries, comprehensive test coverage, and careful separation of concerns. Dhan is the most mature implementation. Upstox has the cleanest internal structure. Paper serves its purpose well for testing. The dual-port design is the most significant architectural debt.

**Relevant Modules**:
- brokers/common/broker_port.py
- brokers/common/gateway.py
- brokers/common/gateway_interfaces.py
- brokers/common/intelligent_market_gateway.py
- brokers/common/common_broker_access.py
- brokers/dhan/gateway.py
- brokers/upstox/gateway.py
- brokers/paper/paper_gateway.py
