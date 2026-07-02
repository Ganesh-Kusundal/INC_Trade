---
name: system-from-scratch
description: >
  Guide on bootstrapping new components, packages, or services from zero using the thinking loop.
  Focuses on an interface-first, test-driven approach where code is iteratively created and verified
  in small, incremental steps. Uses repo-graph to check coupling and ensure clean boundaries.
mode: agent
agent: thinking-loop-orchestrator
---

# Bootstrapping Systems from Scratch

This skill details how to use the automated thinking loop to build a new system, package, or major module from scratch. Rather than writing a large volume of untested code at once, we use the loop to build the system incrementally.

---

## 1. Bootstrapping Strategy

When starting from zero, the loop follows a strict **Interface-First, Test-First** evolution:

```
[Define Port/Interface] ──> [Write Failing Test] ──> [Implement Minimum Code]
          ^                                                    │
          │                   [Update baseline] <── Pass ──────┼─ Test verification
          └─ [Revert change] <── Fail/Errors ──────────────────┘
```

### Phase 1: Boundary & Port Design
1.  Map the new module's position in the codebase. Run `repo-graph:graph_view` to see where it fits.
2.  Define the public interfaces (Ports). Use Python abstract base classes (`abc.ABC`) or typing protocols to detail the contracts.
3.  Write these interface definitions and commit them as the foundation.

### Phase 2: Test Harness Setup
1.  Before writing any concrete implementation, write the unit tests for the expected behavior.
2.  Run the tests. Verify that they fail with appropriate import/attribute errors (or assert failures). This establishes the starting baseline (`tests.passed = 0`, `tests.failed = N`).

### Phase 3: Incremental Implementation
1.  **Iteration 1**: Write the absolute minimum code to resolve compilation and import errors. Commit once type-checking passes.
2.  **Iteration 2**: Implement the simplest version of the first interface method (even returning hardcoded values if necessary) to make the first test pass. Commit and ratchet.
3.  **Iteration 3 to N**: Fill in business logic, database queries, or external adapters method by method. Each method implementation is a loop iteration:
    *   Propose method changes.
    *   Run tests.
    *   Verify test passes.
    *   Check for design violations.
    *   Commit and ratchet.

---

## 2. Integration with repo-graph

During bootstrapping, you must actively run:
*   `repo-graph:generate` to index the new code structure.
*   `repo-graph:flow` to trace references and ensure that other modules only call the public interface (Port) and do not import concrete implementation classes directly.
*   `repo-graph:status` to monitor compilation status and type health across the workspace.
