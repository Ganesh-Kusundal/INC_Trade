# ADR-0004: Capability-Based Architecture for Broker-Specific Features

- **Status**: Accepted
- **Date**: 2026-07-05
- **Deciders**: Elite Quantitative Engineering Review Board

## Context

Each Indian broker exposes a distinct feature surface that does not
generalise:

- **Dhan** — Forever Orders, Super Orders (entry + target + stoploss
  legs), Slice Orders (iceberg), EDIS (e-disclosure), margin
  introspection.
- **Upstox** — GTT (Good-Till-Triggered), News, WebSocket-only market
  data.
- **Paper** — none of the above; deterministic fill simulation.

The naive response was to add these methods to the common interface
(`BrokerGateway`, later the order/portfolio ports). This immediately
produced three problems:

1. **God Interface.** Every new broker feature was a new method on the
   common interface. Adapters that did not implement the feature
   raised `NotSupportedError` at call time.
2. **Open/Closed violation.** Adding a feature to one broker required
   editing the common port and the `ports/__init__.py` export list.
3. **Test pollution.** Tests for the common order path had to be aware
   of the optional capabilities to avoid false negatives.

A previous attempt used `hasattr(gateway, "super_orders")` style duck
typing. This failed because the "feature is supported" predicate was
spread across the codebase, and the call sites silently `AttributeError`
or returned `None` in inconsistent ways.

## Decision

We adopt a **capability-based architecture** with three moving parts:

1. **`BrokerCapabilities` (set of flags).** A frozen set of capability
   names declared in `brokers/domain/capabilities.py`. Each broker
   adapter exposes the set of features it supports.

2. **Broker-specific `Extension Protocols`.** Each broker advertises
   additional protocols in `brokers/adapters/<broker>/extensions/protocols.py`
   — e.g. `ForeverOrderProvider`, `SuperOrderProvider`,
   `SliceOrderProvider`, `GTTProvider`, `NewsProvider`. These protocols
   live next to the broker that owns them, not in the common `ports/`
   package.

3. **`ExtensionRegistryPort` for lookup.** Callers that need a
   broker-specific feature resolve it through the
   `ExtensionRegistryPort` (implemented in
   `brokers/ports/extension_registry.py`). The registry is keyed by
   `(broker_id, protocol)` and returns the provider that implements
   the feature for that broker.

The common interfaces — `OrderExecutionPort`, `MarketDataPort`,
`PortfolioPort`, `StreamingPort`, `HistoricalPort`, `AuthPort` — only
contain features that *every* broker supports (or, in the case of
`StreamingPort`, that the contract is well-defined enough that a
"not implemented" return is meaningful).

The `brokers.connect()` composition root (`brokers/__init__.py`)
populates the registry at startup by calling `registry.register(...)`
for each broker's extensions.

## Consequences

**Positive**

- The common interfaces stay narrow and stable. Adding a new broker
  feature does not modify a shared file.
- New brokers expose their features without modifying any core module.
  Adding a new broker is purely additive: `adapters/<broker>/...` and
  a registration block in `connect()`.
- The `BrokerCapabilities` set provides a discoverable, documented
  inventory of which broker supports what. UI code can introspect
  capabilities to enable or disable menu items.
- Architecture tests (`TestExtensionIsolation` in
  `brokers/tests/unit/test_architecture.py`) enforce that broker-specific
  protocols do not leak into `brokers/ports/`. A PR that adds a
  Dhan-specific protocol to the common ports fails CI.

**Negative**

- Callers that need a broker-specific feature must look it up through
  the registry rather than calling it directly on the broker object.
  This is a small ergonomic tax in exchange for the structural
  cleanliness.
- Two call patterns coexist: the common API (`.place_order()`) and the
  extension API (`.extensions.super_orders.place(...)`). Documentation
  must explain both.
- The capability set is not yet fully populated; some features that
  *should* be broker-specific are still on the common interface
  pending migration. These are tracked as known gaps, not as
  violations.

## Alternatives Considered

- **`hasattr` duck typing (already tried)** — Rejected. The capability
  predicate was implicit and inconsistent, and the OCP violations
  (every feature addition required editing shared code) were the
  exact problem we are solving.
- **Inheritance hierarchies** — `DhanGateway(CommonGateway)`. Rejected.
  Composition (`BrokerFacade` with an `ExtensionRegistryPort`) is more
  flexible than inheritance and avoids the diamond problem when a
  broker wants to compose features from multiple sources.
- **Single "kitchen sink" port with optional methods** — Rejected: this
  is the status quo that produced the God Interface.

## References

- `brokers/domain/capabilities.py` — the `BrokerCapabilities` value
  object and capability name constants.
- `brokers/ports/extension_registry.py` — the
  `ExtensionRegistryPort` and its `DictExtensionRegistry` implementation.
- `brokers/ports/extensions.py` — the broker-agnostic extension
  protocols (e.g. `MarginProvider`, `KillSwitchProvider`).
- `brokers/services/broker_facade.py` — `BrokerFacade`, which composes
  a broker gateway with an extension registry.
- `brokers/tests/unit/test_architecture.py::TestExtensionIsolation` —
  the tests that enforce that broker-specific protocols stay out of
  the common `ports/` package.
