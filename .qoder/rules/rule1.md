---
trigger: always_on
---
# Project Rules

## 1. Virtual Environment Usage

Always use the project's virtual environment (`venv`) when running anything. This includes, but is not limited to:

- Running Python scripts
- Running tests
- Installing dependencies
- Executing build or deployment commands
- Running linting or formatting tools

Before executing any command, ensure the `venv` is activated or the command is invoked using the `venv` interpreter (e.g., `./venv/bin/python` or `venv\Scripts\python.exe` on Windows).

## 2. Completion Gate Process

When any task, feature, bug fix, or code change is marked as **completed**, it must go through the following additional gate before being considered truly done:

1. **Second-Level Review**  
   Perform an additional review of the changes beyond the initial implementation review. Check for correctness, edge cases, design consistency, and alignment with requirements.

2. **Related Test Verifications**  
   - Ensure unit tests cover the changed code.
   - Run integration tests related to the changed area.
   - Confirm all existing tests still pass.
   - Add new tests if coverage is insufficient.

3. **Clean Code & Refactoring**  
   - Refactor for readability, maintainability, and simplicity.
   - Remove dead code, unused imports, and unnecessary comments.
   - Follow project coding standards and naming conventions.

4. **Static Code Analysis**  
   - Run linters (e.g., flake8, pylint, ruff).
   - Run type checkers (e.g., mypy) if applicable.
   - Run formatters (e.g., black, isort) and ensure code is formatted.
   - Address all warnings and errors reported by these tools.

5. **Regression for Code Changes**  
   - Run the full test suite or a targeted regression suite for the affected modules.
   - Verify no existing functionality is broken by the change.
   - Document any behavioral changes or migration notes if needed.

No task is considered complete until all five gates above have been satisfied.
