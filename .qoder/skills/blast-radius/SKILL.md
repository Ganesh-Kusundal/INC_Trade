---
name: blast-radius
description: Pre-commit change impact analysis. Before modifying any production code, determine what else will break. Traces forward (consumers) and backward (dependencies) from the target, produces a risk assessment, and generates a must-run test list. Use before any significant modification to production code. Inspired by the repo-graph MCP server pattern.
---

# Blast Radius — Change Impact Analysis

Know what breaks before you break it.

## Philosophy

A change to any non-private function is a change to every caller. Blast radius makes those invisible dependencies visible before you commit.

## When to Use

| Scenario | Required? | Why |
|----------|-----------|-----|
| Changing a public function signature | **Mandatory** | Every caller may break |
| Changing module internals (no interface change) | Optional | Impact is contained |
| Adding a new module | Optional | No existing consumers to break |
| Removing a module | **Mandatory** | Every importer breaks |
| Changing exception types | **Mandatory** | Every try/except may break |
| Changing configuration schema | **Mandatory** | Every config consumer breaks |
| Refactoring internal implementation | Optional | Only if interface unchanged |

## Process

### Phase 0: Load the Codebase Graph (Preferred)

Before analysis, try to use the **repo-graph MCP server** if available. repo-graph uses the `glia` Rust engine with `tree-sitter` to provide **entity-level dependency resolution** — it only catches actual function/class/module references, not string matches or comments.

**Setup:**
```json
{
  "mcpServers": {
    "repo-graph": {
      "command": "uvx",
      "args": ["mcp-repo-graph", "--repo", "/path/to/project"]
    }
  }
}
```

**repo-graph tools available:**
- Entity query: find all references to a specific symbol
- Flow trace: end-to-end from API to database layer
- Blast radius scope: minimal file set for a change
- Cross-language links (e.g., TypeScript → Python)

If repo-graph is NOT available, use the fallback grep-based analysis below (less precise — grep matches comments, strings, and variable names too).

### Phase 1: Identify the Target

```markdown
## Target
**File**: [path/to/file.py]
**Symbol**: [class/function/variable name]
**Change Type**: [signature | behavior | removal | addition | exception]
```

### Phase 2: Trace Forward (Consumers)

Find everything that uses the target symbol:

**Primary — repo-graph entity query (preferred):** Resolve all consumers via the codebase graph.

**Fallback — grep (less precise, may match comments/strings):**
```bash
# search for usages excluding the definition itself
# VERIFY each result — grep matches comments and strings too
grep -rn "<symbol>" --include="*.py" . | grep -v "<definition file>"
```

Classify each consumer:

| Consumer | File | Change Required? | Risk |
|----------|------|-----------------|------|
| Direct caller | consumer1.py | If signature changes | 🟡 |
| Indirect via inheritance | consumer2.py | If class hierarchy changes | 🟠 |
| Configuration reference | config.py | If config key changes | 🟢 |
| Test file | test_*.py | Always needs update | 🟢 |

### Phase 3: Trace Backward (Dependencies)

Find everything the target depends on:

**Primary — repo-graph dependency resolution (preferred).**

**Fallback — grep (less precise):**
```bash
# grep for imports — VERIFY each match
head -50 target/file.py | grep "^import\|^from"
```

Classify each dependency:

| Dependency | Type | Stability | Risk if Changed |
|------------|------|-----------|-----------------|
| domain/ | Domain module | High | Low — stable interfaces |
| infrastructure/ | Infrastructure | Medium | Medium — may change |
| brokers/dhan/ | Broker-specific | Low | High — frequently changes |
| external/ | Third-party | External | Low — can't change |

### Phase 4: Risk Assessment

```markdown
## Risk Assessment

### Green (Safe)
- Internal implementation changes
- Test-only changes
- Documentation changes
- New files with no existing consumers

### Yellow (Caution)
- Interface changes with known callers (all callers identified and can be updated)
- Behavior changes that don't change types
- Adding new parameters with defaults

### Red (Danger)
- Interface changes with unknown callers
- Removing symbols
- Breaking backward compatibility
- Changing exception semantics
- Changing configuration schema
```

### Phase 5: Test Plan

Generate a must-run test list:

```markdown
## Required Tests

### Must Run Before & After
- [ ] test_direct_callers.py (tests that call this directly)
- [ ] test_integration.py (tests that exercise this through the stack)

### Should Run
- [ ] test_regression.py (full regression suite for this module)

### Should Add
- [ ] New test for changed behavior
- [ ] New test for edge case discovered during analysis

### How to Run
```bash
pytest path/to/test_files -v
```
```

## Output Format

```markdown
## Blast Radius Report: [Target Symbol]

### Forward Trace
- Direct callers: [N]
- Indirect consumers: [N]
- Test files affected: [N]

### Backward Trace
- Upstream dependencies: [N]
- Stability score: [High | Medium | Low]

### Risk Level: [GREEN | YELLOW | RED]

### Test Plan
- Must-run: [N tests]
- Should-run: [N tests]
- Should-add: [N tests]

### Recommended Action
[Proceed with caution | Block until X is resolved | Safe to proceed]
```

## Constraints

- ALWAYS run blast-radius before modifying production code
- NEVER skip the test plan generation — tests are the safety net
- If RED risk and no mitigation, BLOCK the change until unblocked
- After making the change, run ALL identified must-run tests
- If new dependencies are discovered during implementation, re-run blast-radius
