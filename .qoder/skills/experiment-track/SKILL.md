---
name: experiment-track
description: Git-based experiment management for the autoresearch loop. Each experiment is a git branch with structured commit messages, metric tracking, and auto-revert on regression. Use when running any change where the outcome is uncertain and you want the ability to measure, revert, and learn. Integrates with auto-optimize for structured optimization loops.
---

# Experiment Track — Git-Based Experiment Management

Run structured experiments where every iteration is a measured, recorded, revertable change.

## Philosophy

> **"An experiment that can't fail isn't an experiment."**

Every commit during an experiment should answer: *"Did the metric improve?"* If the answer is "no", revert. The experiment log (all commits, including reverted ones) is more valuable than the final state.

## When to Use

| Scenario | Why Track as Experiment |
|----------|------------------------|
| Trying a new algorithm | May not be faster — need to measure |
| Refactoring a hot path | May introduce regression — need to verify |
| Changing broker adapter | May break equivalence — need contract test |
| Adding a new feature | May not solve the problem — need to validate |
| Optimizing a query | May be slower for different data shapes — need benchmark |
| Changing architecture | May increase coupling — need to measure |

## Process

### Phase 1: Create Experiment Branch

```bash
git checkout -b experiment/<date>/<metric>-<short-description>
```

Branch naming convention:
```
experiment/2026-07-02/coupling-broker-port      # optimizes coupling
experiment/2026-07-02/latency-order-placement     # optimizes latency
experiment/2026-07-02/coverage-error-handling     # improves coverage
```

### Phase 2: Measure Baseline

Before any changes, capture the baseline metric:

```bash
# Run the judge script to get baseline score
BASELINE=$(bash .qoder/metrics/judge-<metric>.sh)
echo "Baseline: $BASELINE"

# Tag this point
git tag "baseline-<metric>-$(date +%Y%m%d)"
```

### Phase 3: Run Iterations

Each iteration follows this pattern:

```bash
# 1. Make the change
# 2. Run the judge
NEW_SCORE=$(bash .qoder/metrics/judge-<metric>.sh)

# 3. Compute delta
DELTA=$((NEW_SCORE - BASELINE))

# 4. Commit or revert
if [ "$DELTA" -gt 0 ]; then
    git commit -am "exp: <description> [score: ${BASELINE}→${NEW_SCORE}, Δ+${DELTA}]"
    BASELINE=$NEW_SCORE
elif [ "$DELTA" -eq 0 ]; then
    git commit -am "exp: <description> [score: ${BASELINE}→${NEW_SCORE}, Δ=0]"
    # Same score — keep or revert? By default revert.
    git checkout -- .
else
    echo "Score dropped by ${DELTA}. Reverting."
    git checkout -- .
fi
```

### Phase 4: Merge or Archive

When the experiment is complete:

```bash
# If metric improved
git checkout main
git merge --squash experiment/<date>/<metric>-<desc>
git commit -m "feat: <description> [baseline: X→ final: Y, Δ+N points over N iterations]"

# If metric did not improve
# Don't merge — keep the branch for reference
git tag "archive-$(date +%Y%m%d)-<metric>-<desc>" experiment/<date>/<metric>-<desc>
```

### Phase 5: Log to Memory

Write the experiment to persistent memory:

```
.qoder/memory/experiments/<YYYY-MM-DD>-<metric>-<desc>.md
```

Including:
- Hypothesis
- Method
- Branch name
- Score trajectory (baseline → each iteration → final)
- What worked and what didn't

## Output Format

```markdown
## Experiment: [Title]

### Metadata
- **Date**: [YYYY-MM-DD]
- **Branch**: [experiment/...]
- **Metric**: [name]
- **Judge**: [path to scoring script]
- **Max Iterations**: [N]

### Results
| Iteration | Change | Score | Delta | Outcome |
|-----------|--------|-------|-------|---------|
| Baseline | — | X | — | — |
| 1 | [description] | X+1 | +1 | ✅ Committed |
| 2 | [description] | X+1 | 0 | ➖ Reverted |
| 3 | [description] | X+3 | +2 | ✅ Committed |
| ... | ... | ... | ... | ... |
| Final | — | Y | Δ+N | Merged |

### What Worked
- [Change that improved score]

### What Didn't Work
- [Change that was reverted]

### Lessons
- [What to try next time]
- [What to avoid]
```

## Constraints

- ALWAYS create a branch — never experiment on main
- ALWAYS measure baseline before first change
- ALWAYS commit or revert — never leave uncommitted changes
- ALWAYS tag baseline for reference
- ALWAYS write to memory after experiment completes
- NEVER run experiments that could cause data loss or financial impact
- MAX 30 iterations per experiment
