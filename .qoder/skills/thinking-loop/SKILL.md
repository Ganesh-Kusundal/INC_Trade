---
name: thinking-loop
description: >
  Execute the Git-based Ratchet Loop to systematically improve the system. Coordinates
  the Proposer, Tester, Evaluator, and Critic agents. Reads targets from loop_objective.md,
  measures results against baseline_metric.json, and uses repo-graph to prevent boundary leaks.
  Integrates git commit/revert feedback loops.
mode: agent
agent: thinking-loop-orchestrator
---

# Thinking Loop Workflow

This skill executes a feedback-driven optimization loop that iteratively proposes, tests, evaluates, and ratchets codebase changes.

---

## 1. Setup the Objective

Before starting the loop, create a file named `loop_objective.md` at the project root:

```markdown
# Loop Objective: [Objective Name]

## Goal
Optimize execution latency of the order book scanner.

## Target Metric
Scanner update latency < 5ms.

## Target Files
- `brokers/runtime/scanner.py`
- `brokers/common/cache.py`

## Verification Command
`pytest tests/test_scanner.py -v`
```

---

## 2. Core Execution Loop

For each iteration, the system follows this workflow:

### Step 1: Initialize
*   Orchestrator reads `loop_objective.md` and reads `baseline_metric.json`.
*   Orchestrator executes `repo-graph:generate` to map the codebase.

### Step 2: Propose
*   `thinking-proposer` analyzes the target files and structures.
*   Proposer queries `repo-graph:find` to find structural dependencies.
*   Proposer makes targeted edits to the code.

### Step 3: Verify & Test
*   `thinking-tester` runs the tests or simulation defined in `loop_objective.md`.
*   Tester formats output into a structured JSON metrics block.

### Step 4: Evaluate
*   `thinking-evaluator` compares metrics with `baseline_metric.json`.
*   If testing fails or metrics degrade:
    *   Evaluator triggers **`DECIDE:REVERT`**.
    *   Orchestrator runs `git checkout -- <modified_files>` to restore baseline.
*   If metrics improve, Evaluator triggers **`DECIDE:COMMIT`**.

### Step 5: Architecture Gate (Critic)
*   If Evaluator approves, `thinking-critic` uses `repo-graph:flow` to review code boundaries.
*   If Critic rejects, Orchestrator reverts.
*   If Critic approves, Orchestrator commits:
    `git commit -am "Loop Ratchet: Improved scanner latency to 4.2ms"`
    And updates `baseline_metric.json` with the new values.

---

## 3. How to Run

Run the automated loop handler script:
```bash
python .qoder/scripts/thinking_loop_runner.py --objective loop_objective.md
```
Or run interactively, with you (the human) acting as the Proposer or Critic while the loop runner automates testing, evaluation, and git rollback.
