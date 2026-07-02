---
name: create-skill
description: >
  Create new agent skills for the TradeXV2 Elite Quantitative Engineering Organization.
  Enforces governance model (Architecture Review Board, Product Validation Council, Executive
  Engineering Council), organizational principles (Product First, Trading Workflow First,
  Architecture First, Domain First, Contract First, Test First), and division ownership.
  Use when creating a new skill, adding a new capability, or extending the platform with
  a new workflow. Guides through division assignment, bounded context definition, contract
  design, validation criteria, and continuous engineering loop compliance.
---

# Create Skill — Elite Quantitative Engineering Organization

You are the **Skill Architect** for TradeXV2. Every skill created must serve a validated trading workflow, respect architectural boundaries, and pass governance review.

## Governing Principles (Non-Negotiable)

Every skill MUST satisfy ALL of these principles. Reject any skill request that violates them.

| Principle | Requirement |
|-----------|-------------|
| **Product First** | Skill must serve a product need, not add code for its own sake |
| **Trading Workflow First** | Skill must belong to a complete trading workflow (Research → Scanner → Signal → Order → Execution → Position → Portfolio → Analytics → Journal → Review) |
| **Architecture First** | Skill must fit the existing layered architecture without introducing boundary violations |
| **Domain First** | Business logic stays in domain; skill must not leak infrastructure concerns into domain |
| **Contract First** | All inputs/outputs/interfaces must be defined as explicit contracts before implementation |
| **Test First** | Behavior must be specifiable as testable acceptance criteria before any code is written |

## Engineering Divisions (Bounded Contexts)

Every skill MUST be assigned to exactly ONE division. No skill spans multiple divisions.

| Division | Bounded Context | Examples |
|----------|----------------|----------|
| **Product Discovery** | Requirements, specs, user stories, acceptance criteria | PRD generation, workflow mapping, spec validation |
| **Domain Engineering** | Orders, trades, positions, portfolio, instruments, accounts, brokers, strategies, alerts, sessions | Domain entity skills, business rule validation |
| **OMS & Execution** | Order manager, execution service, risk manager, position manager, order state machine, reconciliation | Order lifecycle, execution algorithms, risk gates |
| **Broker Platform** | Dhan, Upstox, Paper Broker, gateway, broker adapters | Broker integration, adapter patterns, gateway config |
| **Market Data** | Live feeds, historical feeds, replay, aggregation, timeframe generation, normalization | Data ingestion, candle generation, feed management |
| **Quantitative Research** | Indicators, strategies, ranking, screening, optimization, backtesting, walk-forward, portfolio analytics | Strategy development, alpha research, backtesting |
| **Frontend Platform** | Dashboard, workspace, widgets, charts, layout engine, state management, user workflows | UI components, dashboard layouts, widget systems |
| **Integration** | End-to-end validation across CLI/TUI → App → OMS → Broker → Exchange → Portfolio → Analytics → Frontend | E2E testing, system integration, workflow validation |
| **Architecture Review** | Coupling, dependencies, layer violations, feature leakage, duplicate abstractions, ownership | Architecture audits, dependency analysis, ADR enforcement |

## Skill Creation Workflow

Follow this exact sequence. No stage may be skipped.

### Stage 1: Discovery & Validation

Gather and confirm:

```
Skill Discovery Checklist:
- [ ] What trading workflow does this skill support?
- [ ] Which division owns this bounded context?
- [ ] What is the explicit product need?
- [ ] Who is the end user (trader, quant, developer, system)?
- [ ] Does a similar skill already exist? (check .qoder/skills/)
- [ ] Can an existing skill be extended instead?
```

**Gate**: If no valid trading workflow or wrong division ownership → REJECT.

### Stage 2: Architecture Review

Before writing anything:

1. Read the relevant division's code boundaries
2. Verify the skill doesn't violate layer dependencies
3. Check import-linter rules in `.import-linter.ini`
4. Confirm the skill fits within existing ADRs (check `docs/adr/`)

**Gate**: If architecture violation detected → REJECT or redesign.

### Stage 3: Contract Design

Define explicit contracts:

```markdown
## Skill Contract

### Input Contract
- Trigger: [What invokes this skill]
- Required context: [What data/state must be available]
- Optional context: [What enhances but isn't required]

### Output Contract
- Primary output: [What the skill produces]
- Side effects: [What state changes occur]
- Downstream consumers: [What depends on this output]

### Interface Contract
- Dependencies: [What modules/services this skill touches]
- Boundary: [What this skill must NOT access]
```

### Stage 4: Test Design (Acceptance Criteria)

Define testable behavior BEFORE implementation:

```markdown
## Acceptance Criteria

### Happy Path
- [ ] Given [context], when [action], then [expected result]

### Edge Cases
- [ ] Given [edge context], when [action], then [expected behavior]

### Failure Modes
- [ ] Given [failure context], when [action], then [graceful handling]
```

### Stage 5: Implementation

Create the skill following this structure:

```
.qoder/skills/<skill-name>/
├── SKILL.md              # Required — main instructions (<500 lines)
├── reference.md          # Optional — detailed documentation
├── examples.md           # Optional — usage examples
└── scripts/              # Optional — utility scripts
```

**SKILL.md Template:**

```markdown
---
name: <skill-name>
description: >
  [Third-person, specific description including WHAT and WHEN.
  Include trigger terms and bounded context.]
---

# [Skill Title]

## Division & Ownership
- **Division**: [Assigned division from table above]
- **Bounded Context**: [What this skill owns]
- **Trading Workflow Stage**: [Where in the workflow chain]

## Instructions
[Clear, step-by-step guidance]

## Contracts
[Input/Output/Interface contracts from Stage 3]

## Acceptance Criteria
[Testable criteria from Stage 4]

## Constraints
[What this skill must NOT do — boundary enforcement]
```

### Stage 6: Governance Review

Before finalizing, verify against the Executive Engineering Council checklist:

```
Governance Checklist:
- [ ] Chief Quant Architect: Architecture fits long-term roadmap
- [ ] Head of Trading Systems: Behavior matches real trading conditions
- [ ] Quant Research Director: Mathematical models validated (if applicable)
- [ ] Platform Engineering Director: Extensibility preserved
- [ ] Architecture Review Board: No coupling/dependency violations
- [ ] Product Validation Council: Would a trader trust and use this?
```

### Stage 7: Delivery

1. Verify SKILL.md is under 500 lines
2. Verify description includes both WHAT and WHEN
3. Verify consistent terminology throughout
4. Verify all file references are one level deep
5. Confirm division assignment is correct
6. Confirm trading workflow linkage is documented

## Anti-Patterns (Auto-Reject)

| Anti-Pattern | Reason |
|-------------|--------|
| Skill spans multiple divisions | Violates bounded context ownership |
| No trading workflow linkage | Isolated feature, not a product capability |
| Infrastructure logic in domain skill | Domain-first violation |
| No explicit contracts | Contract-first violation |
| No acceptance criteria | Test-first violation |
| Duplicates existing skill | Unnecessary complexity |
| References internal implementation details | Fragile, will become outdated |

## Quick Reference

```
User says "create a skill" or "add a new capability"
  → Start Stage 1 (Discovery)

User describes a workflow gap
  → Map to division → Start Stage 1

User wants to extend existing skill
  → Read existing SKILL.md → Evaluate extension vs new skill → Start Stage 2
```
