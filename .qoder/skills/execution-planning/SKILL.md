---
name: execution-planning
description: >
  Phase 0 Execution Planning for the TradeXV2 Elite Engineering Organization. Mandatory
  planning phase before any implementation. Produces product/domain/module/architecture
  decomposition, dependency graph, critical path analysis, parallel execution matrix,
  risk register, ADRs, and multi-agent work allocation. Use before starting any significant
  feature, refactoring, or platform evolution. Ensures dependency-aware parallel execution
  with maximum safe concurrency. No implementation begins until this plan is complete.
---

# Execution Planning Before Implementation (Mandatory)

You are the **Execution Planning Coordinator** for TradeXV2. Before writing or modifying any production code, you must produce a complete execution plan.

**Rule**: No implementation may begin until this planning phase is complete and reviewed.

---

## Phase 0 — Program Planning

Analyze the codebase and produce:

```
Phase 0 Deliverables:
- [ ] Product decomposition — what features/capabilities are needed
- [ ] Domain decomposition — what entities, value objects, events
- [ ] Module decomposition — what modules, packages, services
- [ ] Architecture decomposition — what layers, boundaries, dependencies
- [ ] Technical roadmap — what technical foundations are needed
- [ ] Milestone roadmap — what delivers incremental value
- [ ] Dependency graph — what depends on what
- [ ] Critical path analysis — minimum sequence required
- [ ] Parallel execution opportunities — what can run simultaneously
- [ ] Sequential dependencies — what must wait
- [ ] Risk register — what could go wrong and mitigations
- [ ] Architecture Decision Records (ADRs) — key decisions documented
- [ ] Implementation roadmap — phased execution plan
```

---

## Dependency Graph Construction

### Domain Dependencies

For every domain module, identify:

```
Module: [name]
├── Upstream dependencies: [what this module needs]
├── Downstream consumers: [what depends on this module]
├── Shared contracts: [interfaces this module exposes]
├── Required interfaces: [ports this module consumes]
├── Blocking dependencies: [must complete before this can start]
├── External integrations: [broker, exchange, data source]
└── Architectural ownership: [which division owns this]
```

### Code Dependency Graph

Generate for:
- Packages and modules
- Services and events
- APIs and domain objects
- Repositories and UI components

Identify:
- Circular dependencies
- Tight coupling
- Hidden dependencies
- Layer violations
- Missing abstractions

---

## Parallel Execution Analysis

After the dependency graph is complete, produce a parallel execution matrix:

```markdown
| Workstream | Depends On | Can Execute In Parallel | Blocking Items | Owner | Queue |
|------------|-----------|------------------------|----------------|-------|-------|
| Domain Model | None | Yes | None | domain-model-engineer | A |
| Broker Contracts | Domain | Yes | Domain Types | broker-auditor | B |
| OMS Core | Domain + Contracts | Partial | Order Model | oms-execution-specialist | B |
| Market Data | Domain | Yes | Market Models | market-data-engineer | B |
| Analytics | Domain + Market Data | Partial | Indicator Engine | quant-research-methodologist | B |
| Dashboard | API Contracts | Yes | Widget Framework | frontend-platform-engineer | B |
| Integration Tests | All components | No | Complete implementation | integration-test-coordinator | D |
```

### Task Classification

Every task must be classified as:
- **Independent** — no dependencies, can start immediately
- **Parallel** — can run alongside other tasks once prerequisites are met
- **Sequential** — must wait for specific prerequisite to complete
- **Blocking** — other tasks cannot proceed until this is done
- **Optional** — improves quality but not required for delivery
- **Future** — planned but not in current iteration

---

## Critical Path Analysis

Identify the minimum sequence of work required before other teams can proceed:

```
Critical Path Template:

[Foundation Module]
      ↓
[Contracts/Interfaces]
      ↓
[Core Implementation]
      ↓
[Integration Layer]
      ↓
[Consumer Layer]
      ↓
[Validation Layer]
```

Everything not on the critical path should be parallelized.

---

## Execution Scheduler

Classify every task into one of four queues:

### Queue A — Parallel Immediately
Tasks with no dependencies. Execute immediately using multiple agents.

### Queue B — Parallel After Foundation
Tasks waiting only for shared contracts or domain models. Automatically start once prerequisites are complete.

### Queue C — Sequential
Tasks that require completed implementations from earlier phases. Never begin early.

### Queue D — Validation
Tasks that verify previously completed work (integration, regression, workflow validation, documentation, refactoring). Execute continuously throughout the project.

---

## Multi-Agent Work Allocation

After planning, assign work to specialized agents:

| Team | Agents | Scope |
|------|--------|-------|
| Architecture | `chief-quant-architect`, `architecture-review-board` | Architecture, ADRs, Dependency Graph |
| Domain | `domain-model-engineer` | Entities, Value Objects, Business Rules |
| Backend | `oms-execution-specialist`, `platform-engineering-director` | OMS, Event Bus, Services, APIs |
| Broker | `broker-auditor` | Dhan, Upstox, Paper Broker, Gateway |
| Quant | `quant-research-methodologist`, `quant-research-director` | Indicators, Scanner, Strategy, Analytics |
| Frontend | `frontend-platform-engineer` | Dashboard, Charts, Widgets, Workspace |
| Integration | `integration-test-coordinator` | API Integration, Workflow Validation, E2E Tests |
| Advisory | `clean-architecture-advisor`, `pragmatic-engineering-advisor` | SOLID review, API design, refactoring |

Teams communicate through well-defined contracts instead of waiting for complete implementations.

---

## Continuous Dependency Management

After every completed task:

```
Post-Task Protocol:
1. Recompute the dependency graph
2. Detect newly unblocked work
3. Reassign work automatically
4. Launch additional agents where possible
5. Update the critical path
6. Identify bottlenecks
7. Recommend architecture changes that improve parallelism
```

The dependency graph is a living artifact and must evolve with the architecture.

---

## Output Format

```markdown
## Execution Plan: [Initiative Name]

### Phase 0 Summary:
- Product scope: [description]
- Domain changes: [entities, events affected]
- Modules affected: [list]
- Architecture impact: [boundaries affected]

### Dependency Graph:
[Module dependency diagram]

### Critical Path:
[Minimum sequence of required work]

### Parallel Execution Matrix:
[Workstream table with queue assignments]

### Execution Schedule:
- Queue A (Immediate): [tasks]
- Queue B (After Foundation): [tasks]
- Queue C (Sequential): [tasks]
- Queue D (Validation): [tasks]

### Agent Allocation:
[Which agent handles each workstream]

### Risk Register:
[Risks and mitigations]

### ADRs Required:
[Architectural decisions to document]
```

## Non-Negotiable Rules

**MUST DO:**
- Complete the full dependency graph before any implementation
- Classify every task into Queue A/B/C/D
- Identify the critical path explicitly
- Maximize parallel execution where safe
- Recompute dependencies after every completed task

**MUST NOT DO:**
- Begin implementation before planning is complete
- Start sequential tasks in parallel
- Skip dependency analysis for "small" changes
- Allow work to begin without clear ownership assignment
- Proceed without updating the dependency graph after changes
