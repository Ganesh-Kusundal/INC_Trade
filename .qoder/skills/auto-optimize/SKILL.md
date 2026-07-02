---
name: auto-optimize
description: Karpathy-style autoresearch loop for metric-driven code optimization. Defines a scoring function, runs iterative hypothesize→implement→score→keep/revert cycles, and accumulates improvements. Use when user wants to optimize performance, reduce coupling, increase test coverage, or improve any measurable quality of the codebase. Implements the three-component autoresearch pattern (target, judge, brain).
---

# Auto-Optimize — Karpathy-Style Autoresearch Loop

Run automated optimization loops where each iteration is a measurable improvement or a revert.

## Philosophy (Karpathy's Insight)

> **"The loop is the skill."** — Andrej Karpathy

A structured feedback loop beats unlimited intelligence. The autoresearch pattern has three fixed components:

```
train.py (THE TARGET)    → The code/system being optimized
prepare.py (THE JUDGE)   → Fixed evaluation producing a single score
program.md (THE BRAIN)   → Instructions telling the agent HOW to experiment
```

The agent: hypothesize → edit target → run judge → if score improves, KEEP (commit). If score worsens, REVERT (git reset). The human writes the judge. The agent runs the loop.

## When to Use

| Scenario | Metric | Target |
|----------|--------|--------|
| Reduce module coupling | Number of cross-module imports | ↓ |
| Increase test coverage | Line/branch coverage % | ↑ |
| Improve error handling | Percentage of functions with typed errors | ↑ |
| Reduce code duplication | Duplicate block count | ↓ |
| Improve type coverage | MyPy strict-passing rate | ↑ |
| Reduce function length | Functions > 50 lines count | ↓ |
| Improve naming clarity | Ambiguous identifier count | ↓ |
| Optimize API latency | P50/P95 response time | ↓ |
| Reduce memory usage | Peak memory under load | ↓ |

## Process

### Phase 1: Define the Optimization Target

Work with the user to establish:

```markdown
## Optimization Target

### What to Optimize
[Exact metric: e.g., "number of cross-broker imports in common/ broker_port.py"]

### Current Baseline
[Measured starting value: e.g., "42 imports from broker-specific modules"]

### Target
[Desired value: e.g., "0 imports from broker-specific modules — only interfaces"]

### Scoring Function
[How to measure: e.g., "grep -c 'from brokers.dhan\|from brokers.upstox' brokers/common/broker_port.py"]

### Constraint
[Things that must NOT change: e.g., "public API must remain backward compatible"]

### Max Iterations
[How many attempts before reporting: e.g., 20]
```

**Gate**: If no measurable metric can be defined, do NOT proceed. Ask the user for a different optimization target.

### Phase 2: Define the Metric & Scaffold the Judge

Work with the user to define the metric, then scaffold the judge script for their approval:

```markdown
## Metric Definition

### What to Measure
[Description: e.g., "number of cross-broker imports in common/"]

### Scoring Formula
[How to compute: e.g., "100 - (import_count * 10), min 0"]

### Judge Script (Proposed)
```bash
#!/usr/bin/env bash
# judge-<target>.sh — returns a single numeric score (higher is better)

IMPORTS=$(grep -c 'from brokers.dhan\|from brokers.upstox' brokers/common/broker_port.py)
SCORE=$((100 - IMPORTS * 10))
if [ $SCORE -lt 0 ]; then SCORE=0; fi
echo "$SCORE"
```

### Python Alternative (if bash not available)
```python
#!/usr/bin/env python3
import re
with open('brokers/common/broker_port.py') as f:
    content = f.read()
imports = len(re.findall(r'from brokers\.(dhan|upstox)\b', content))
score = max(0, 100 - imports * 10)
print(score)
```
```

**Human approval required** before the loop starts. The human must confirm:
- This metric captures the optimization goal
- The scoring formula is correct
- The judge script is deterministic

**Judge rules (enforced):**
- Must be a deterministic script (same code → same score)
- Must return exactly one integer between 0 and 100
- Must complete in under 30 seconds
- Must be committed to git before the loop starts
- The agent MUST NOT modify the judge during the loop

### Phase 3: Run the Loop

Execute the autoresearch cycle:

```
ITERATION 1:
  1. READ current state (git diff, current score)
  2. HYPOTHESIZE: "If I move X to Y, score will improve because..."
  3. IMPLEMENT: Make the change to the target file(s)
  4. SCORE: Run the judge
  5. IF score improved:
       git commit -m "auto-optimize: [module] [score: +X → +Y] [hypothesis]"
       Log: "Iteration N: ✅ Score improved +X → +Y"
  6. IF score stayed same:
       git checkout -- .  # revert
       Log: "Iteration N: ➖ No change. Reverted."
  7. IF score worsened:
       git checkout -- .  # revert
       Log: "Iteration N: ❌ Score dropped +X → +Y. Reverted."
  8. RECORD: Add to .qoder/memory/experiments/ log

ITERATION 2-N:
  Repeat. Each iteration learns from previous failures.
  After 5 consecutive failures with no improvement, STOP.
  After max iterations reached, STOP.
```

### Phase 4: Report Results

After the loop completes, produce a summary:

```markdown
## Auto-Optimize Report: [Target]

### Summary
- **Starting Score**: [baseline]
- **Final Score**: [end state]
- **Improvement**: [+/- X points] ([+/- X%])
- **Iterations**: [N total, N improved, N reverted, N unchanged]

### What Worked
- [Change 1]: +X points
- [Change 2]: +X points

### What Didn't Work
- [Change 1]: hypothesis was wrong because...
- [Change 2]: caused regression in...

### Recommendation
[Should this be merged permanently? What follow-up optimization would help?]

### Memory
- [ ] Written to .qoder/memory/experiments/
- [ ] Written to .qoder/memory/decisions/ (if structural changes)
```

## Safety Rules

| Rule | Rationale |
|------|-----------|
| NEVER modify the judge during the loop | Otherwise scores aren't comparable |
| ALWAYS revert on score drop | Don't accept regression even temporarily |
| ALWAYS commit working changes first | So revert doesn't destroy uncommitted work |
| NEVER optimize without a metric | Otherwise it's just change, not improvement |
| MAX 30 iterations per session | Prevent runaway loops |
| Flag if 5 consecutive improvements < 1% | Diminishing returns — change target |

## Example Session

```
> User: "Optimize the broker_port.py to reduce Dhan-specific imports"

> Agent: "I'll set up the optimization target.
> Current: 42 imports from brokers.dhan in broker_port.py
> Target: 0 — only interfaces from brokers.common
> Judge: grep -c 'from brokers.dhan' brokers/common/broker_port.py
> Max iterations: 20

> Running iteration 1...
> Hypothesize: Extract GatewayOptionsFacade import to a factory function
> Implement: Moved import inside __init__ method
> Score: 42 → 41 (+1 point)
> ✅ Committed: "auto-optimize: broker_port lazy-load GatewayOptionsFacade [score: 58→60]"

> Running iteration 2...
> Hypothesize: Replace Dhan-specific error imports with common protocol
> ...

> Final: Score improved from 0/100 to 85/100 over 12 iterations.
> 12 iterations: 8 improved, 3 reverted, 1 unchanged
> Remaining 3 imports are in method signatures — need ADR change.
```
