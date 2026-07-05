# ADR-0003: Domain-Driven Design Bounded Contexts (Market, Trading, Infrastructure)

- **Status**: Accepted
- **Date**: 2026-07-05
- **Deciders**: Elite Quantitative Engineering Review Board

## Context

In the original `brokers/` module, three concerns were intermingled in a
single `services/` package:

- **Market data** — quotes, historical candles, option chains, streaming.
- **Trading** — order placement, OMS, positions, holdings, account
  management.
- **Infrastructure** — HTTP clients, retry, caching, rate limiting, auth.

A "place a market order and wait for a fill" flow had to traverse code
from all three concerns in a single file, with no clear ownership
boundary. This produced several problems:

- Tests for "does the OMS correctly publish an `OrderPlacedEvent`?" had
  to also stand up the entire HTTP client, retry policy, and quote cache.
- Refactoring the market data path (e.g. adding a market router) required
  care to avoid breaking the trading path.
- New contributors could not tell where to add a new feature: is
  `place_order` a service, an OMS, a context, or an adapter?
- The hexagonal layering (ADR-0002) was necessary but not sufficient —
  it described the *shape* of the code, not its *responsibilities*.

## Decision

We adopt three **bounded contexts** in the DDD sense, each with its own
ports, services, and tests:

| Context | Responsibility | Top-level package |
| --- | --- | --- |
| **Market** | Quotes, historical data, option chains, streaming ticks, instrument registry. | `brokers/market/` |
| **Trading** | Orders, OMS, execution routing, account management, positions. | `brokers/trading/` |
| **Infrastructure** | HTTP client, retry, caching, rate limiting, event bus, persistence. | `brokers/infrastructure/` |

The shared kernel is the `domain/` layer (`brokers/domain/`): frozen
dataclass entities (`Order`, `Quote`, `Position`, `Trade`, `Balance`,
`Holding`, `MarketDepth`), enums (`Side`, `OrderType`, `OrderStatus`,
`BrokerID`, `ProductType`, `Validity`), exceptions, and request value
objects. Every context may depend on `domain/`. No context may import
from another context.

Cross-context coordination happens through the **Event Bus** (see
ADR-0005), not through direct method calls. Market publishes
`QuoteTickEvent`; Trading publishes `OrderPlacedEvent`,
`OrderCancelledEvent`, `OrderModifiedEvent`, `OrderFilledEvent`,
`OrderRejectedEvent`. Subscribers register through `EventBus.subscribe`
in the `brokers/__init__.py` `connect()` composition root.

The bounded-context boundary is enforced by `TestBoundaryRules` in
`brokers/tests/unit/test_architecture.py`.

## Consequences

**Positive**

- Each context has a clear owner, a clear test directory, and a clear
  dependency footprint.
- The market data path can evolve (new providers, new caching
  strategies) without touching the trading path.
- The trading path can evolve (new OMS policies, new execution routers)
  without touching the market data path.
- Tests are scoped: a market test does not need an OMS; a trading test
  does not need a real WebSocket.
- The same hexagonal layering (ADR-0002) applies inside each context,
  so the team only has to learn one discipline.

**Negative**

- Some objects naturally span two contexts (a `Position` is a market
  concept that is *owned* by trading). These objects live in `domain/`
  (the shared kernel) and are passed across context boundaries by
  reference.
- Code that wants to coordinate two contexts must go through the event
  bus, which adds an indirection compared to a direct call. The
  indirection is the point: it makes the coordination visible and
  asynchronous.
- The package layout is now `brokers/{domain, ports, services,
  market, trading, infrastructure, adapters, ...}` — more directories
  than a single-bucket design.

## Alternatives Considered

- **Single `services/` layer** — Rejected: this is the status quo that
  produced the entanglement. Forcing market and trading to share a
  package made it too easy to import across concerns.
- **Plugin-based contexts** — Each broker ships its own context.
  Rejected: context ownership is a *domain* concept (market vs. trading),
  not a *broker* concept. Dhan's market and Dhan's trading should be
  able to share `domain/` and `ports/`.
- **Microservices** — Rejected: this is a single deployable Python
  package, not a distributed system. The bounded contexts are
  logical, not physical, boundaries. Premature distribution would
  make local testing painful and add network failure modes that
  are not present in the design.

## References

- `brokers/market/context.py` — `MarketDataContext`, the entry point of
  the Market bounded context.
- `brokers/trading/oms.py` — `OrderManagementSystem`, the entry point of
  the Trading bounded context.
- `brokers/infrastructure/event_bus.py` — the infrastructure context's
  event bus implementation.
- `brokers/tests/unit/test_architecture.py::TestBoundaryRules` — the
  tests that enforce the no-cross-import rule between contexts.
- `brokers/ARCHITECTURE_BLUEPRINT_V3.md` — Section 2.3, "Bounded Context
  Architecture".
