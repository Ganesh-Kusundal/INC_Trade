# TradeXV2 Elite Quantitative Engineering Organization

## Mission

Design, build, validate, and evolve TradeXV2 into a modular, extensible, broker-agnostic quantitative trading platform — governed by institutional-grade engineering discipline.

---

## Executive Engineering Council

The Council governs all architectural decisions. No implementation bypasses council approval.

| Role | Agent | Authority | Perspective |
|------|-------|-----------|-------------|
| **Chief Quant Architect** | `chief-quant-architect` | Long-term architecture, ADRs, dependency rules | Structural integrity over time |
| **Head of Trading Systems** | `head-of-trading-systems` | Order/position/portfolio lifecycle, exchange interactions | Real trading correctness |
| **Quant Research Director** | `quant-research-director` | Indicators, strategy engine, backtesting, walk-forward | Mathematical model validity |
| **Platform Engineering Director** | `platform-engineering-director` | Backend/frontend, event bus, lifecycle, configuration | Extensibility and maintainability |

---

## Engineering Divisions

Each division owns one bounded context. No division modifies another without review.

| Division | Agent | Bounded Context | Council |
|----------|-------|----------------|---------|
| Product Discovery | `product-discovery-analyst` | Requirements, specs, trading workflows | All 4 |
| Domain Engineering | `domain-model-engineer` | `domain/` (entities, ports, events) | Chief Quant Architect |
| OMS & Execution | `oms-execution-specialist` | `application/oms/`, `execution/`, `trading/` | Head of Trading Systems |
| Broker Platform | (existing `broker-auditor`) | `brokers/` (dhan, upstox, paper) | Head of Trading Systems |
| Market Data | `market-data-engineer` | `market_data/`, `datalake/` | Head of Trading Systems |
| Quantitative Research | `quant-research-methodologist` | `analytics/` (indicators, strategy, backtest) | Quant Research Director |
| Frontend Platform | `frontend-platform-engineer` | `frontend/` | Platform Engineering Director |
| Integration | `integration-test-coordinator` | `api/`, `infrastructure/`, cross-system | Platform Engineering Director |
| Architecture Review | `architecture-review-board` | `.import-linter.ini`, `docs/adr/` | Chief Quant Architect |
| **AI Platform** | `memory-curator`, `experiment-runner`, `codebase-cartographer`, `metric-historian`, `blast-radius-analyst`, `from-scratch-architect` | `.qoder/memory/`, `.qoder/metrics/`, `.qoder/skills/` (Karpathy skills) | Platform Engineering Director |

### Governance Bodies

| Body | Agent | Authority |
|------|-------|-----------|
| Architecture Review Board | `architecture-review-board` | Enforces coupling, dependencies, layer compliance |
| Product Validation Council | `product-validation-council` | Final gate — "Would a trader trust this?" |

---

## Existing Tactical Auditors

These agents perform hands-on code reviews. They are NOT governance bodies.

| Agent | Division | Purpose |
|-------|----------|---------|
| `architecture-reviewer` | Architecture Review | 9-phase repo organization audit |
| `broker-auditor` | Broker Platform | External adapter integration audit |
| `code-reviewer` | Integration | Code quality, security, performance |
| `deep-static-auditor` | Architecture Review | Static code analysis, SOLID |
| `eda-auditor` | Architecture Review | Event-driven architecture audit |
| `principle-architect-reviewer` | Architecture Review | 5-Why root cause analysis |
| `production-readiness-reviewer` | Integration | Production readiness assessment |
| `quant-platform-orchestrator` | Integration | 8-agent orchestration master |
| `quant-platform-reviewer` | Quantitative Research | Quant trading readiness |
| `reliability-readiness-reviewer` | Integration | Reliability audit |
| `testing-strategy-auditor` | Integration | Testing strategy assessment |

---

## Decision Tree

```
Need a review or decision?
│
├── Strategic/policy decision → COUNCIL AGENT
│   ├── Architecture strategy → chief-quant-architect
│   ├── Trading correctness → head-of-trading-systems
│   ├── Research methodology → quant-research-director
│   └── Platform extensibility → platform-engineering-director
│
├── Domain-specific review → DIVISION AGENT
│   ├── Product specs → product-discovery-analyst
│   ├── Domain model → domain-model-engineer
│   ├── OMS/execution → oms-execution-specialist
│   ├── Market data → market-data-engineer
│   ├── Quant methodology → quant-research-methodologist
│   ├── Frontend → frontend-platform-engineer
│   └── Integration → integration-test-coordinator
│
├── Karpathy system operation → AI PLATFORM AGENT
│   ├── Memory read/write → memory-curator
│   ├── Codebase structure → codebase-cartographer
│   ├── Metrics tracking → metric-historian
│   ├── Experiment/optimization → experiment-runner
│   ├── Blast radius analysis → blast-radius-analyst
│   └── First-principles design → from-scratch-architect
│
├── Tactical code audit → EXISTING AUDITOR
│   ├── Architecture → architecture-reviewer
│   ├── Broker integration → broker-auditor
│   ├── Code quality → code-reviewer
│   ├── Static analysis → deep-static-auditor
│   ├── Event-driven → eda-auditor
│   ├── Full platform → quant-platform-orchestrator
│   ├── Production → production-readiness-reviewer
│   ├── Reliability → reliability-readiness-reviewer
│   └── Testing → testing-strategy-auditor
│
├── Memory protocol → MEMORY SYSTEM
│   ├── Before acting → /memory-read — check past relevant knowledge
│   ├── After learning → /memory-write — save what you discovered
│   └── Quality governance → memory-curator
│
└── Governance gate
    ├── ADR/dependency policy → architecture-review-board
    └── Product validation → product-validation-council
```

---

## Engineering Advisory Council (Methodology Personas)

Engineering personas inspired by respected industry leaders. Every significant architectural decision, implementation, and refactoring must pass review from this council.

| Advisor | Agent | Philosophy | Authority |
|---------|-------|-----------|-----------|
| **Clean Architecture Advisor** | `clean-architecture-advisor` | Robert C. Martin ("Uncle Bob") — SOLID, dependency direction, cohesion | May reject any implementation violating architectural principles |
| **Pragmatic Engineering Advisor** | `pragmatic-engineering-advisor` | Venkat Subramaniam — elegant APIs, evolutionary architecture, simplicity | May require redesign when APIs/abstractions become unmaintainable |

---

## Quantitative Engineering Review Board

The review board continuously challenges every implementation from multiple perspectives. Every major feature must be independently reviewed before acceptance.

| Panel | Responsible For | Key Question |
|-------|----------------|--------------|
| **Architecture Review** | Layer boundaries, module ownership, dependency graph, extensibility | Will this architecture still work in five years? |
| **Backend Engineering** | OMS, Execution Engine, Broker Framework, Event Bus, Services | Is the implementation modular and deterministic? |
| **Frontend Engineering** | Dashboard, Widget Framework, Charts, State Management | Does this improve trader productivity? |
| **Quantitative Research** | Indicators, Strategies, Scanner, Backtesting, Walk-forward | Is the mathematical model correct and validated? |
| **Product Engineering** | Trading workflow validation, edge case coverage | Would an experienced trader use it? |
| **Quality Engineering** | Test strategy, contract testing, E2E validation, regression | Are we testing behaviour, not implementation? |
| **Continuous Refactoring** | Readability, maintainability, simplicity, naming, API consistency | Is the platform cleaner than before? |

### Multi-Perspective Review Pipeline (12 Steps)

Every significant feature must pass through `/multi-perspective-review`:

```
1. Product Review → 2. Trading Workflow → 3. Domain → 4. Architecture →
5. Backend Engineering → 6. Frontend Engineering → 7. Quantitative Research →
8. API & Contract → 9. Testing & QA → 10. Integration →
11. Documentation → 12. Final Product Validation
```

If any reviewer identifies a blocking issue, implementation returns to the earliest affected phase.

---

## Execution Planning Before Implementation (Mandatory)

Before writing or modifying any production code, the organization must produce a complete execution plan via `/execution-planning`.

### Phase 0 Deliverables
- Product/Domain/Module/Architecture decomposition
- Dependency graph (domain + code level)
- Critical path analysis
- Parallel execution matrix (Queue A/B/C/D)
- Multi-agent work allocation
- Risk register
- ADRs

### Execution Queues

| Queue | Type | When |
|-------|------|------|
| **A — Parallel Immediately** | No dependencies | Start now |
| **B — Parallel After Foundation** | Waits for contracts/domain | Start when prerequisites complete |
| **C — Sequential** | Requires completed earlier phases | Never begin early |
| **D — Validation** | Verifies completed work | Runs continuously |

### Continuous Dependency Management
After every completed task: recompute dependency graph, detect unblocked work, reassign, update critical path.

---

## Continuous Engineering Loop

Every change follows this lifecycle. No stage may be skipped.

```
Plan (Phase 0) → Understand → Challenge → Design → Architecture → Domain → Contract → Test → Implement → Review → Integrate → Validate → Document → Ship → Repeat
```

---

## Organizational Principles

| Principle | Rule |
|-----------|------|
| **Product First** | Build the correct trading product, not more code |
| **Trading Workflow First** | Every feature serves a complete trading workflow |
| **Architecture First** | Architecture exists before implementation |
| **Domain First** | Business logic in domain, infrastructure serves domain |
| **Contract First** | Explicit contracts before implementation |
| **Test First** | Behavior specified before implementation |
| **Plan First** | Execution plan before any implementation |
| **Continuous Validation** | Passing tests ≠ correctness |
| **Incremental Delivery** | Every iteration produces a working improvement |

---

## Engineering Culture

This organization does NOT optimize for: lines of code, velocity, story points, test coverage percentages.

This organization DOES optimize for: correct trading workflows, clean architecture, domain correctness, maintainability, extensibility, deterministic behaviour, quantitative correctness, end-to-end validation, continuous improvement, long-term product evolution, metric-driven optimization, and persistent learning across sessions.

---

## Karpathy Continuous Improvement Loop

This organization operates on Karpathy-inspired loop engineering. Every improvement is:

1. **Measured** — defined by a numeric metric before any change
2. **Iterated** — hypothesize → implement → score → keep/revert
3. **Revertable** — if metric worsens, the change is discarded
4. **Recorded** — every experiment is logged to persistent memory
5. **Compounded** — knowledge survives across sessions via the memory system

The loop itself is the skill. The human defines the metric; the agents run the iterations.

```
Define Metric → Baseline → Hypothesize → Implement → Score → Keep or Revert → Log to Memory → Repeat
```

---

## Memory System (Persistent Agent Knowledge)

Codebuff's persistent memory ensures knowledge survives across sessions. Every decision, finding, experiment, and architecture change is recorded.

```
.qoder/memory/
├── decisions/     — ADR-style decision records
├── findings/      — Bug patterns and diagnosis insights
├── experiments/   — Git-based experiment logs
└── architecture/  — Living architecture map (module deps, seams, migrations)
```

**Memory Curator** (`memory-curator`) governs quality: validates entries, tags for searchability, links related entries, and flags stale knowledge.

**Memory Protocol:** `/memory-read` before acting, `/memory-write` after learning.

---

## Karpathy-Inspired Agents (New Division: AI Platform)

These agents extend the governance model with Karpathy's loop-engineering and first-principles design philosophy.

| Agent | Role | Philosophy | Key Skill |
|-------|------|-----------|-----------|
| `memory-curator` | Memory system governance | What you don't remember, you repeat | `/memory-read`, `/memory-write` |
| `codebase-cartographer` | Living codebase structure map | Structure must be visible to be reasoned about | `/blast-radius` |
| `metric-historian` | Quality metric tracking | If you can't measure it, you can't improve it | `/auto-optimize` |
| `experiment-runner` | Autoresearch optimization loop | The loop is the skill | `/experiment-track` |
| `blast-radius-analyst` | Change impact analysis | Know what breaks before you break it | `/blast-radius` |
| `from-scratch-architect` | First-principles design | Build from essential concepts outward | `/from-scratch` |

---

## Skills

| Skill | Purpose |
|-------|---------|
| `/execution-planning` | Phase 0: dependency graph, critical path, parallel execution matrix |
| `/multi-perspective-review` | 12-step review pipeline for all significant changes |
| `/governance-review` | Route decisions through Council agents and governance bodies |
| `/division-workflow` | Division-specific implementation patterns |
| `/create-skill` | Create new skills following governance model |
| `/create-subagent` | Create new subagents following governance model |
| `/ultra-plan` | Multi-phase planning with orchestrator |
| `/ultra-review` | 9-phase architecture review |
| `/tdd` | Test-driven development |
| `/diagnose` | Bug diagnosis |

### Karpathy-Inspired Skills (New)

| Skill | Purpose | Core Pattern |
|-------|---------|--------------|
| `/memory-read` | Query persistent agent memory before acting | Memory recall protocol |
| `/memory-write` | Persist decisions, findings, and experiments | Memory storage protocol |
| `/auto-optimize` | Metric-driven autoresearch loop | target → judge → iterate → keep/revert |
| `/blast-radius` | Pre-commit change impact analysis | forward trace → backward trace → risk → test plan |
| `/agents-think-together` | Parallel multi-agent design deliberation | N constraints → N designs → compare → synthesize |
| `/experiment-track` | Git-based experiment management | branch → measure → iterate → merge or archive |
| `/from-scratch` | First-principles system design | core concepts → minimal model → seams → ports |

### Skill Auto-Trigger Rules

| Trigger | Auto-Skill |
|---------|-----------|
| Starting any significant task | `/memory-read` — check past relevant knowledge |
| Completing a significant task | `/memory-write` — save what you learned |
| Modifying production code | `/blast-radius` — what else might break? |
| Designing a new interface | `/agents-think-together` — N agents with different constraints |
| Running an optimization loop | `/experiment-track` + `/auto-optimize` |
| Designing a new subsystem | `/from-scratch` — first principles |

---

## File Inventory

### Council Agents (4)
- `.qoder/agents/chief-quant-architect.md`
- `.qoder/agents/head-of-trading-systems.md`
- `.qoder/agents/quant-research-director.md`
- `.qoder/agents/platform-engineering-director.md`

### Advisory Council Agents (2)
- `.qoder/agents/clean-architecture-advisor.md`
- `.qoder/agents/pragmatic-engineering-advisor.md`

### Division Agents (9)
- `.qoder/agents/product-discovery-analyst.md`
- `.qoder/agents/domain-model-engineer.md`
- `.qoder/agents/oms-execution-specialist.md`
- `.qoder/agents/market-data-engineer.md`
- `.qoder/agents/quant-research-methodologist.md`
- `.qoder/agents/frontend-platform-engineer.md`
- `.qoder/agents/integration-test-coordinator.md`
- `.qoder/agents/architecture-review-board.md`
- `.qoder/agents/product-validation-council.md`

### Karpathy-Inspired Agents (6 — New)
- `.qoder/agents/memory-curator.md` — Persistent memory governance
- `.qoder/agents/codebase-cartographer.md` — Living codebase structure map
- `.qoder/agents/metric-historian.md` — Quality metric tracking
- `.qoder/agents/experiment-runner.md` — Autoresearch optimization loop
- `.qoder/agents/blast-radius-analyst.md` — Change impact analysis
- `.qoder/agents/from-scratch-architect.md` — First-principles system design

### Governance Skills (4)
- `.qoder/skills/governance-review/SKILL.md`
- `.qoder/skills/division-workflow/SKILL.md`
- `.qoder/skills/multi-perspective-review/SKILL.md`
- `.qoder/skills/execution-planning/SKILL.md`

### Meta Skills (2)
- `.qoder/skills/create-skill/SKILL.md`
- `.qoder/skills/create-subagent/SKILL.md`

### Karpathy Skills (7 — New)
- `.qoder/skills/memory-read/SKILL.md` — Query persistent agent memory
- `.qoder/skills/memory-write/SKILL.md` — Persist knowledge across sessions
- `.qoder/skills/auto-optimize/SKILL.md` — Metric-driven autoresearch loop
- `.qoder/skills/blast-radius/SKILL.md` — Pre-commit change impact analysis
- `.qoder/skills/agents-think-together/SKILL.md` — Parallel multi-agent deliberation
- `.qoder/skills/experiment-track/SKILL.md` — Git-based experiment management
- `.qoder/skills/from-scratch/SKILL.md` — First-principles system design

### Infrastructure (New)
- `.qoder/memory/` — Persistent agent memory (decisions, findings, experiments, architecture)
- `.qoder/metrics/` — Time-series quality metric storage
- `.qoder/plans/` — Enhanced execution plans

### Configured External Services
- **repo-graph MCP server** (`mcp-repo-graph`) — Codebase graph via `uvx` (configured in `.mcp.json`)
  - Graph cache: `.ai/repo-graph/` (26MB, 9,429 nodes, 15,602 edges, 77 cross-stack edges)
  - 13 MCP tools: `generate`, `status`, `flow`, `trace`, `impact`, `neighbours`, `read`, `activate`, `find`, `locate`, `dense_text`, `graph_view`, `reload`
  - Instructions: `CLAUDE.md`
