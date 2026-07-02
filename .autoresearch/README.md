# Autoresearch Git-Ratchet Loop: AI Coder Instructions

You are acting as the **Proposer Agent** in a Karpathy-style Autoresearch loop. Your objective is to iteratively modify the code to achieve the goals defined in `.autoresearch/objective.md` without introducing regressions.

---

## 🛑 The Rules of the Loop (Non-Negotiable)

1.  **Strict File Permissions**:
    *   You are permitted to modify **ONLY** the files listed under `target_files` in `.autoresearch/config.json`.
    *   You **MUST NOT** modify any files under `immutable_files` (such as the tests, validation scripts, or the `.autoresearch/` directory itself). Modifying tests to make them pass is considered "cheating" and will invalidate the loop.
2.  **Git-Based Ratchet**:
    *   Every change you make is evaluated empirically.
    *   If your change improves the target metric and passes all test suites, the harness will automatically commit it: `git commit -am "Autoresearch Ratchet: ..."`
    *   If your change causes test failures, type check errors, lint errors, or degrades the target metric, the harness will automatically **revert** your changes (`git restore`).
3.  **One Change per Iteration**:
    *   Apply only one conceptual change/hypothesis at a time. This keeps git histories clean and makes it clear which change resulted in metric improvement.

---

## 🔄 How to Work in the Loop

### Step 1: Read the Goal & Config
1.  Read `.autoresearch/objective.md` to see what you are trying to build or optimize.
2.  Read `.autoresearch/config.json` to verify your target files and check the target metric to optimize.

### Step 2: Codebase Context & Impact Mapping
*   If you have the **`repo-graph` MCP server** connected:
    *   Use `repo-graph:find` to locate the target files and references.
    *   Use `repo-graph:impact` to check which files depend on your target files. This ensures your modifications will not break downstream modules.
*   If `repo-graph` is not connected, use standard read and search tools to understand the codebase.

### Step 3: Implement Your Change
*   **If building a feature from scratch**: Define the abstract class / interface first. Write a failing test in the test suite (if you're allowed, or request the user to add it), then implement the minimal code in the target files.
*   **If optimizing/fixing**: Refactor or adjust the logic in the target files.

### Step 4: Run the Harness
Run the harness script in the terminal:
```bash
python .autoresearch/harness_runner.py
```
*   **If the run is successful**: The change is committed, and the new score is ratcheted. Proceed to the next improvement step.
*   **If the run fails**: The runner will revert your target files. Do not panic. Read the output or `.autoresearch/runs/latest_run.log`, understand what failed, and propose a different solution.

---

## 📊 Objective File Format (`objective.md`)
Specify objectives clearly using this format:
```markdown
# Objective: [Title]
- Goal: [Description]
- Target Metric: [e.g. tests.passed > 5]
```
