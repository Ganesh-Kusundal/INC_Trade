# ADR-0005: Event Bus with Typed Events for Cross-Context Communication

- **Status**: Accepted
- **Date**: 2026-07-05
- **Deciders**: Elite Quantitative Engineering Review Board

## Context

After adopting bounded contexts (ADR-0003), the Market and Trading
contexts still needed to coordinate. Two real needs drove this:

1. **Quote state auto-update.** When a streaming tick arrives for an
   instrument, the `MarketDataContext` needs to keep its cached
   `QuoteState` fresh so subsequent `.quote()` calls return the latest
   price without a network round-trip.
2. **OMS notifications.** When the OMS places, modifies, cancels, or
   receives a fill for an order, downstream consumers (audit logs,
   risk checks, UI updates, paper-trading fill detection) need to
   observe the state change.

The original design had no event system. Coordination was done by direct
method calls, which forced the contexts to know about each other — for
example, the OMS had a reference to the streaming adapter, and the
streaming adapter had a reference back to the OMS. This is a cycle and
violates the bounded-context boundary.

We needed a way for contexts to broadcast facts about their state
without the publisher knowing who is listening.

## Decision

We adopt an **in-process, synchronous `EventBus`** with **typed
immutable events** as the cross-context communication mechanism.

**The bus.** `brokers/infrastructure/event_bus.py` provides an
`EventBus` class with `subscribe(event_type, callback) -> token`,
`unsubscribe(token)`, and `publish(event) -> int` methods. Delivery is
synchronous: every callback runs to completion before `publish()`
returns. The bus is in-process (no network hop) and runs in the same
thread as the publisher unless the publisher explicitly offloads.

**The events.** `brokers/domain/events.py` defines the event hierarchy
as independent frozen dataclasses with an `event_type: str` class
variable:

- `QuoteTickEvent` — published by the streaming layer on each tick.
- `DepthUpdateEvent` — published by the streaming layer on depth
  changes.
- `OrderPlacedEvent` — published by the OMS on successful placement.
- `OrderFilledEvent` — published by the OMS or fill detector on a
  fill.
- `OrderRejectedEvent` — published by the OMS on broker rejection.
- `OrderModifiedEvent` — published by the OMS on a successful modify.
- `OrderCancelledEvent` — published by the OMS on a successful cancel.
- `ConnectionEvent` — published by the connection lifecycle on
  connect / disconnect / reconnect.

Events are independent frozen dataclasses (not subclasses of a common
`DomainEvent` parent) to avoid frozen-dataclass inheritance
complications while still being immutable. The bus uses duck typing —
any object with an `event_type` attribute is publishable.

**Wiring.** The `brokers.connect()` composition root
(`brokers/__init__.py`) creates the single `EventBus` instance, passes
it to `MarketDataContext` (which subscribes a callback that publishes
`QuoteTickEvent` and auto-updates `QuoteState`) and to the
`OrderManagementSystem` (which publishes `OrderPlacedEvent`,
`OrderCancelledEvent`, `OrderModifiedEvent` from its lifecycle
methods).

**Rule.** No context calls another context's methods directly. Cross-
context state propagation goes through the bus.

## Consequences

**Positive**

- Market and Trading are loosely coupled. The OMS does not import
  streaming code; the streaming layer does not import OMS code. They
  share only the event dataclasses in `domain/`.
- Subscribers can be added without modifying publishers. Adding an
  audit log subscriber, a UI update subscriber, or a risk-check
  subscriber is a one-line `bus.subscribe(...)` call in `connect()`.
- Events are immutable, so subscribers cannot accidentally mutate
  state they do not own. The frozen dataclass invariant is enforced
  by the type system.
- The bus is synchronous and in-process, which keeps the reasoning
  simple: `publish()` returns when all subscribers have run, and there
  is no need to think about network failures, message ordering across
  nodes, or at-least-once delivery semantics.
- The bus is testable in isolation: tests construct an `EventBus`,
  register a callback, publish a fake event, and assert the callback
  was invoked with the right payload.

**Negative**

- A subscriber that raises will break the publish chain. We accept
  this in exchange for synchronous, easy-to-reason-about delivery.
  Production subscribers must be defensive.
- The bus is a single point of coordination. If it becomes a
  bottleneck or hot spot, we will need to revisit (e.g. introduce an
  async dispatcher, a queue). Today it is not.
- The "subscribers must check `event_type`" contract is informal —
  enforced by tests rather than by a type-level mechanism. New event
  types must add a matching subscriber in `connect()`.
- In-process delivery is the right answer for a single-process Python
  application. If we ever need to coordinate across processes (e.g.
  a separate scanner service), we will need to revisit this decision.

## Alternatives Considered

- **Observer pattern per context** — Each context owns its own
  observer list. Rejected: produces N observer lists to maintain,
  and re-introduces direct coupling between the publisher and the
  observer list owner.
- **Message queue (Redis, RabbitMQ)** — Rejected: a single-process
  Python module does not need a network broker. The operational
  complexity of running a queue is not justified by the use case.
- **Callback chains** — `Order.place(on_fill=callback)`. Rejected: the
  callback is part of the order's lifetime, which forces the OMS to
  track callbacks per order and complicates the audit trail. The bus
  is stateless with respect to the publisher.

## References

- `brokers/domain/events.py` — the typed event hierarchy
  (`QuoteTickEvent`, `OrderPlacedEvent`, etc.) with `event_type`
  constants.
- `brokers/infrastructure/event_bus.py` — the `EventBus`
  implementation with `subscribe` / `unsubscribe` / `publish`.
- `brokers/trading/oms.py` — the `OrderManagementSystem` that
  publishes `OrderPlacedEvent`, `OrderModifiedEvent`,
  `OrderCancelledEvent`, `OrderRejectedEvent`, `OrderFilledEvent`.
- `brokers/market/context.py` — the `MarketDataContext` that
  subscribes to streaming ticks and auto-updates `QuoteState`.
- `brokers/__init__.py` — the `connect()` composition root that
  instantiates the bus and wires it into both contexts.
- `brokers/tests/unit/test_events.py` — the 17 unit tests covering
  event publication, subscription, and immutability invariants.
