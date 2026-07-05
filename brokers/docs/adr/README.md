# Architecture Decision Records — `brokers/`

This directory contains the Architecture Decision Records (ADRs) for the
`brokers/` module. Each ADR captures a significant architectural decision,
the forces that drove it, the consequences of adopting it, and the
alternatives that were considered and rejected.

ADRs are immutable historical records. When a decision is reversed, the
original ADR is marked **Superseded** (with a link to the superseding ADR)
rather than edited or deleted.

## Index

| ADR | Title | Status | Date |
| --- | --- | --- | --- |
| [ADR-0001](0001-instrument-centric-architecture.md) | Instrument-Centric Architecture over Broker-Centric | Accepted | 2026-07-05 |
| [ADR-0002](0002-hexagonal-architecture.md) | Hexagonal Architecture (Ports & Adapters) with Strict Layer Boundaries | Accepted | 2026-07-05 |
| [ADR-0003](0003-bounded-contexts.md) | Domain-Driven Design Bounded Contexts (Market, Trading, Infrastructure) | Accepted | 2026-07-05 |
| [ADR-0004](0004-capability-based-architecture.md) | Capability-Based Architecture for Broker-Specific Features | Accepted | 2026-07-05 |
| [ADR-0005](0005-event-bus-architecture.md) | Event Bus with Typed Events for Cross-Context Communication | Accepted | 2026-07-05 |

## Status Definitions

- **Accepted** — The decision is in force and currently being implemented.
- **Superseded** — A later ADR has replaced this decision. The original is
  preserved for historical context.
- **Deprecated** — The decision is no longer recommended but has not been
  formally replaced.

## How to Read

Each ADR follows a lightweight M. Nygard–style template:

1. **Context** — the problem and the forces at play.
2. **Decision** — what was chosen and why.
3. **Consequences** — the positive and negative effects.
4. **Alternatives Considered** — other options and the reasons they were rejected.
5. **References** — concrete pointers to source code, tests, and design docs.

## How to Add a New ADR

1. Copy the most recent ADR as a starting point.
2. Use the next sequential number (`0006-foo.md`, `0007-bar.md`, ...).
3. Add a row to the index table above.
4. Submit a PR for review by the Elite Quantitative Engineering Review Board.
