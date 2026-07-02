---
name: agents-think-together
description: Parallel multi-agent design deliberation. Spawn N agents with different design constraints, let each produce a radical solution, then compare and synthesize the best elements. Use when designing interfaces, module boundaries, APIs, data models, or any non-trivial architectural decision. Based on Ousterhout's "Design It Twice" principle: your first idea is unlikely to be the best.
---

# Agents Think Together — Parallel Multi-Agent Deliberation

Spawn multiple agents in parallel, each with a different design constraint, then synthesize the strongest result.

## Philosophy

> **"Your first idea is unlikely to be the best. Design it twice. Design it three times."** — John Ousterhout

Different design constraints produce radically different solutions. The best design often combines elements from multiple approaches.

## When to Use

| Decision Type | N Agents | Typical Constraints |
|---------------|----------|-------------------|
| Interface design | 3-4 | Minimize surface / Maximize flexibility / Optimize for common case / Optimize for testing |
| Module boundary | 3 | Cohesion-first / Coupling-minimizing / Migration-easiest |
| Data model | 3 | Storage-efficient / Query-optimized / Evolution-friendly |
| API contract | 3 | Minimal params / Self-documenting / Backward-compatible |
| Error handling strategy | 3 | Fail-fast / Resilient / Auditable |
| Configuration design | 3 | Simple defaults / Environment-flexible / Validation-strict |

## Process

### Phase 1: Frame the Problem

Write a user-facing explanation of the problem space:

```markdown
## Design Problem: [Title]

### Context
[What we're trying to solve, what constraints exist]

### Requirements
- [Must-have 1]
- [Must-have 2]
- [Must-have 3]

### Constraints
- [Constraint 1: e.g., "Must not break existing callers"]
- [Constraint 2: e.g., "Must be testable without external services"]

### Success Criteria
- [What "good" looks like]
- [How we'll evaluate designs]
```

### Phase 2: Spawn Agents with Constraints

> **Implementation Note**: This skill uses Codebuff's `spawn_agents` tool to run multiple agents in parallel. Each agent gets a unique design constraint and the same problem context. Agents run independently — they cannot see each other's output until all complete.

Spawn N agents in parallel using `spawn_agents`. Each receives a different design constraint:

```markdown
# Agent 1 — Minimal Interface
Constraint: "Minimize the interface — aim for 1-3 entry points max."

# Agent 2 — Maximum Flexibility
Constraint: "Maximize flexibility — support many use cases and extension points."

# Agent 3 — Common Case First
Constraint: "Optimize for the most common caller — make the default case trivial."

# Agent 4 — Testability First (optional)
Constraint: "Optimize for testability — ensure every path can be tested in isolation."
```

Each agent uses `set_output` to report its design containing:
1. **Interface** (types, methods, params, invariants, error modes, ordering)
2. **Usage example** showing how callers use it
3. **What the implementation hides** behind the seam
4. **Dependency strategy** — what adapters are needed
5. **Trade-offs** — where leverage is high, where it's thin

**Parallel execution**: Use `spawn_agents` with multiple agents to run them concurrently. Wait for all to complete before proceeding to compare.

**Agent isolation**: Each agent receives identical context but different constraints. No agent sees another's work until the comparison phase.

### Phase 3: Present and Compare

Present designs sequentially, then compare:

```
## Design Comparison

### Design A (Minimal Surface)
_Agent 1_

**Interface:**
[3 entry points, ultra-simple]

**Trade-offs:**
+ Very easy to learn
- Cannot express complex cases without workarounds

### Design B (Maximum Flexibility)
_Agent 2_

**Interface:**
[10 entry points, many options]

**Trade-offs:**
+ Supports every use case
- Steep learning curve, many ways to misuse

### Design C (Common Case First)
_Agent 3_

**Interface:**
[2 common cases as simple, 1 advanced case as flexible]

**Trade-offs:**
+ 80% of users never need the advanced mode
- Advanced users must learn two patterns
```

### Phase 4: Synthesize

Propose a recommendation:

```markdown
## Recommendation: Design A + C Hybrid

### Selected Elements
- From A: the simple entry point for the common case
- From C: the parameter object pattern for advanced cases
- From B: the error classification scheme

### Rationale
[Why this combination serves the actual use cases best]

### Open Questions
- [What needs user input before finalizing]
```

### Phase 5: Validate

Run the selected design through `/blast-radius` before implementation:

```
- Which existing code changes?
- Which tests need updating?
- Which downstream consumers are affected?
```

## Output Format

```markdown
## Agents-Think-Together: [Design Problem]

### Process
- [ ] Phase 1: Problem framed
- [ ] Phase 2: [N] agents spawned with constraints
- [ ] Phase 3: Designs presented and compared
- [ ] Phase 4: Recommendation synthesized
- [ ] Phase 5: Validated (or scheduled for validation)

### Designs Produced
| # | Constraint | Entry Points | Key Trade-off |
|---|------------|-------------|---------------|
| 1 | Minimal | [N] | [primary trade-off] |
| 2 | Flexible | [N] | [primary trade-off] |
| 3 | Common-case | [N] | [primary trade-off] |

### Recommendation
[Selected design with rationale]

### Memory
- [ ] Written to .qoder/memory/decisions/
```

## Constraints

- NEVER spawn fewer than 3 agents for a design decision
- NEVER let one agent see another's design before all are complete (parallel only)
- If two agents produce identical designs, that convergence is itself a signal
- If designs are fundamentally incompatible, flag it — don't force a hybrid
- Write the decision to memory so future sessions reference it
