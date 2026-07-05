# ADR-0002: Hexagonal Architecture (Ports & Adapters) with Strict Layer Boundaries

- **Status**: Accepted
- **Date**: 2026-07-05
- **Deciders**: Elite Quantitative Engineering Review Board

## Context

Prior to this decision, the `brokers/` module suffered from a tangle
between adapters, services, and infrastructure. Concrete violations
included:

- Adapters directly importing service-layer helpers (SRP violation).
- Services instantiating concrete HTTP clients rather than depending on
  abstractions (DIP violation).
- Broker-specific symbols (Dhan `client_id`, Upstox `access_token`)
  leaking into the `domain/` layer.
- A single `utils/` module holding both generic helpers and broker
  integration code.
- No automated check that imports flowed in the right direction; the
  boundaries relied on code review and tribal knowledge.

We needed a layering scheme that was self-documenting, machine-checkable,
and easy to teach to new contributors.

## Decision

We adopt **Hexagonal Architecture** (a.k.a. Ports & Adapters) with seven
concentric layers. Imports flow strictly **inward**:

```
domain/        → zero internal dependencies (pure business logic)
core/          → zero internal dependencies (generic utilities)
utils/         → zero internal dependencies (price math)
config/        → domain.exceptions only
ports/         → domain/ + self-references only
services/      → domain/ + ports/ + utils/ + self only
resilience/    → domain/ + self only
infrastructure/ → (accepts external deps, bridges to adapters)
adapters/      → implements ports, depends on infrastructure
```

The `market/`, `trading/`, and `infrastructure/` bounded contexts (see
ADR-0003) live alongside these layers and obey the same import rules.

Two structural rules are enforced on every port in `brokers/ports/`:

1. Every port must inherit from `typing.Protocol` (structural typing).
2. Every port must be decorated with `@runtime_checkable` and exported
   from `brokers/ports/__init__.py`.

The boundaries are enforced by **79 architecture tests** in
`brokers/tests/unit/test_architecture.py` (`TestBoundaryRules`,
`TestPortStructure`, `TestExceptionHierarchy`). These tests run in under
one second in CI and act as a **fitness function** for the architecture.

## Consequences

**Positive**

- Clean separation of concerns: domain has no I/O, ports have no logic,
  services orchestrate, infrastructure adapts external libraries, and
  adapters implement the contracts.
- Adding a new broker is an exercise in the outer layer only — it requires
  no changes to `domain/`, `ports/`, or `services/`.
- The architecture fitness functions (the test module) catch violations
  immediately. A PR that imports the wrong layer fails CI before review.
- New contributors can navigate the codebase by layer name: "where does
  retry logic live?" → `resilience/`. "where is Dhan's HTTP client?" →
  `adapters/dhan/`.
- Mocking for tests is trivial: any object that satisfies a `Protocol`
  can stand in for the real implementation.

**Negative**

- The number of small files and modules is high. A simple operation
  (e.g. place an order) now spans `domain.requests`,
  `ports.order_execution`, `services.oms`, `trading.execution_router`,
  `adapters.dhan.gateway`. The cognitive cost is real for newcomers.
- Strict layering forbids some "obviously safe" shortcuts (e.g. putting a
  domain enum constant in `utils/`). Refusing these shortcuts is the
  point; the discipline must be socialised.
- The architecture tests must be kept in sync with the layer rules. New
  layers require new tests.

## Alternatives Considered

- **N-tier (presentation / business / data)** — Rejected: too coarse. A
  three-layer model cannot express the distinction between *what the
  domain is* (`domain/`) and *how the application orchestrates it*
  (`services/`).
- **Vertical-slice / feature folders** — Rejected: encourages coupling
  between layers within a slice and makes cross-cutting concerns (e.g.
  resilience, cache) hard to factor out.
- **Plain Clean Architecture** — Rejected: Clean Architecture is a
  superset of Hexagonal. By committing to the seven named layers and
  enforcing them with tests, we get a more concrete contract than "the
  dependencies point inward" alone.

## References

- `brokers/tests/unit/test_architecture.py` — the 79 architecture fitness
  function tests that enforce the layer rules and port structure.
- `brokers/AGENTS.md` — the project's architecture and coding rules.
- `brokers/ARCHITECTURE_BLUEPRINT_V3.md` — Section 2, "Future-State
  Architecture Blueprint", including the package organization and
  directed dependency graph.
