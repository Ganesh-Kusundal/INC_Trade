---
name: autoresearch-loop
description: >
  Andrej Karpathy-style Autoresearch loop for quantitative model optimization, backtesting strategies,
  and hyperparameter tuning. Enforces the strict three-file architecture (mutable Target, immutable Harness,
  and Program instructions) with automated Git-based ratcheting and rollback.
mode: agent
agent: thinking-loop-orchestrator
---

# Autoresearch Loop (Karpathy Pattern)

This skill guides the implementation of the **Autoresearch Pattern** to systematically optimize quantitative signals, strategy execution parameters, or backtesting models.

---

## 1. The Three-File Architecture

To prevent the agent from "cheating" (e.g., simplifying the evaluation metric or modifying historical price data), the codebase is partitioned into three roles:

1.  **The Mutable Target File** (e.g., `brokers/runtime/strategy.py`):
    *   This contains entry/exit parameters, risk logic, indicator weights, or mathematical models.
    *   This is the **only** code file the Proposer agent is allowed to edit.
2.  **The Immutable Evaluation Harness** (e.g., `brokers/runtime/prepare.py`, `tests/backtest_runner.py`):
    *   This handles historical data loading, slippage calculations, commission modeling, and scoring logic.
    *   It outputs a standard metric (e.g., Sharpe Ratio, validation loss, maximum drawdown).
    *   The agent is **never** permitted to modify this file.
3.  **The Program Instructions** (`program.md`):
    *   This defines the optimization objective, search constraints, target metrics, and maximum iterations.

---

## 2. Autoresearch Execution Loop

The loop runs continuously using the following state machine:

```
[Read program.md] ──> [Propose Target edit] ──> [Run Harness Backtest]
     ^                                                 │
     │                 [Update baseline] <── Improved ─┼─ Metric check
     └─ [Revert change] <── Declined ──────────────────┘
```

### Protocol Steps:

1.  **Hypothesis Formulation**: The Proposer reads the current state of `strategy.py` and `program.md`, identifies parameters or signal rules to change, and applies the edit.
2.  **Simulation & Backtesting**: The Tester runs the Immutable Evaluation Harness. The run is capped (e.g., maximum 5 minutes or 100 historical trades) to maintain velocity.
3.  **Fitness Calculation**: The Evaluator parses the run logs to extract:
    *   `sharpe_ratio`
    *   `net_profit_in_r`
    *   `max_drawdown_pct`
4.  **Ratchet or Revert**:
    *   **If fitness improved**: The Orchestrator performs a git commit to lock in the progress:
        `git commit -am "Autoresearch Ratchet: Sharpe Ratio improved from X to Y"`
        The new score becomes the baseline.
    *   **If fitness declined or tests failed**: The Orchestrator reverts the workspace immediately:
        `git checkout HEAD -- brokers/runtime/strategy.py`
5.  **Iteration**: Repeat from Step 1 with a new hypothesis.

---

## 3. Integration with repo-graph

During the proposal phase:
*   The Proposer must call `repo-graph:impact` on `strategy.py` to ensure changes do not break event sub-subscriptions in execution modules.
*   The Orchestrator must call `repo-graph:flow` to verify that modified strategy logic does not introduce asynchronous race conditions in the order dispatcher.
