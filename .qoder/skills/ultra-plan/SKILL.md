---
name: ultra-plan
description: >
  Invoke comprehensive multi-phase planning using the quant-platform-orchestrator agent.
  Triggers dependency-aware parallel execution planning, master remediation plan generation,
  and test-first execution protocols. Use when creating implementation plans, designing
  remediation strategies, orchestrating multi-agent workflows, or planning production fixes.
  Automatically sequences specialized agents and synthesizes findings into actionable phases.
mode: agent
agent: quant-platform-orchestrator
---

# Ultra-Deep Planning & Orchestration

You are now in **ultra-plan mode** - performing comprehensive multi-phase planning with dependency-aware orchestration.

## Activation

This skill invokes the `quant-platform-orchestrator` agent for master-level planning.

## Planning Methodology

### Phase 1: Dependency Graph Construction
- Identify all tasks and their relationships
- Map blocking dependencies (A must complete before B)
- Identify parallel execution opportunities
- Create critical path analysis

### Phase 2: Multi-Agent Orchestration Plan
- Assign specialized agents to tasks
- Define execution sequence with dependencies
- Specify handoff points between agents
- Plan parallel execution where safe

### Phase 3: Master Remediation Plan
- **Phase A (Critical)**: Production blockers, security issues, data corruption risks
- **Phase B (Structural)**: Architecture violations, coupling issues, boundary leaks
- **Phase C (Hardening)**: Performance, observability, test coverage, documentation

### Phase 4: Test-First Execution Protocol
- Define test cases BEFORE implementation
- Specify acceptance criteria for each task
- Plan validation checkpoints
- Define rollback strategies

## Output Format

### Task Definition
```
📋 Task: [Task Name]
🎯 Objective: [What needs to be achieved]
📍 Files: [file1.py, file2.py, etc.]
🔗 Dependencies: [Task X, Task Y]
👤 Agent: [Specialized agent assigned]
⚡ Parallel: [Can run with Task Z: Yes/No]
```

### Phase Structure
```
🔷 Phase A: Critical Fixes
   ├── A1: [Task name] - Blocks: [B1, B2]
   ├── A2: [Task name] - Blocks: [B3]
   └── A3: [Task name] - Parallel with: [A2]

🔷 Phase B: Structural Remediation
   ├── B1: [Task name] - Requires: [A1]
   ├── B2: [Task name] - Requires: [A1, A2]
   └── ...

🔷 Phase C: Hardening
   ├── C1: [Task name] - Requires: [All Phase B]
   └── ...
```

### Dependency Graph
```
A1 → B1 → C1
A2 → B2 → C1
A3 → B3 → C2
```

## Non-Negotiable Rules

1. **Dependency enforcement is sacred** - never violate execution order
2. **Test-first always** - define tests before writing code
3. **Parallel only where safe** - verify no shared state conflicts
4. **Interface isolation** - changes must not break public APIs
5. **Cross-auditor verification** - each phase validated by appropriate agent
6. **Rollback plan required** - every change must be reversible

## Agent Sequencing Protocol

### Sequential Agents (strict order)
1. **architecture-reviewer** - Structural audit
2. **eda-auditor** - Event flow analysis
3. **deep-static-auditor** - Code quality analysis
4. **broker-auditor** - External adapter review
5. **quant-platform-reviewer** - Quantitative review
6. **testing-strategy-auditor** - Test coverage audit
7. **reliability-readiness-reviewer** - Failure handling review
8. **production-readiness-reviewer** - Final readiness assessment

### Parallel Execution Rules
- Agents can run in parallel ONLY if:
  - No shared file modifications
  - No output dependencies
  - No state conflicts
- Always run Phase A tasks before Phase B
- Phase C can begin after Phase B is 80% complete

## Final Deliverables

Produce these artifacts:
1. **Dependency Graph** - Visual representation of task relationships
2. **Critical Path Analysis** - Longest execution chain
3. **Master Remediation Plan** - Complete task breakdown with phases
4. **Agent Assignment Matrix** - Which agent does what when
5. **Parallel Execution Map** - What can run simultaneously
6. **Risk Assessment** - What could go wrong and mitigation strategies
7. **Validation Checklist** - How to verify each phase succeeded
8. **Rollback Procedures** - How to undo each change safely
