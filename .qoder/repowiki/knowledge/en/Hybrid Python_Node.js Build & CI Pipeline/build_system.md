The TradeXV2 platform employs a hybrid build system combining Python for the backend (analytics, brokers, datalake) and Node.js for the frontend. The system relies on `setuptools` for Python packaging, `uv` for dependency locking, and GitHub Actions for a multi-stage CI/CD pipeline.

### Core Build Tools
- **Python Backend**: Managed via `pyproject.toml` using `setuptools` as the build backend. Dependencies are locked using `uv.lock`, indicating the use of the `uv` package manager for fast resolution and installation. The project defines optional `[dev]` dependencies for testing and linting.
- **Frontend**: A React/TypeScript application built with `Vite`. Dependency management is handled via `npm` (`package-lock.json`).

### CI/CD Architecture (GitHub Actions)
The CI pipeline is split into several specialized workflows:
1.  **`ci.yml`**: The primary workflow triggered on push/PR. It runs in parallel jobs:
    -   **Lint & Type Check**: Runs `ruff`, `mypy` (non-blocking currently), `bandit` (security), and `import-linter` to enforce architectural boundaries.
    -   **Unit & Contract Tests**: Executes `pytest` with coverage enforcement (80% overall, 85% for brokers, 90% for OMS core). Uses `pytest-xdist` for parallel execution.
    -   **Quant Parity**: Verifies deterministic behavior of analytics and replay engines.
    -   **Frontend**: Runs `npm ci`, `typecheck`, `test` (Vitest), and `build`.
    -   **E2E & Stress**: Runs end-to-end trading flow tests and performance benchmarks.
2.  **`production_gate.yml`**: A stricter workflow triggered on release branches. It adds chaos engineering tests, memory leak regression checks, and a final "Production Certification" step that aggregates results from all previous stages.
3.  **`load-test.yml`**: Scheduled weekly load tests against the Paper Broker to ensure performance budgets (latency/RPS) are met.
4.  **`mutation_nightly.yml`**: Nightly mutation testing using `mutmut` on critical domain and OMS code to verify test suite effectiveness.

### Key Conventions & Rules
- **Coverage Gates**: Hard failures if coverage drops below defined thresholds per module.
- **Architectural Linting**: `import-linter` is used in CI to forbid forbidden imports (e.g., `analytics` importing from `brokers.dhan`), ensuring a clean hexagonal/clean architecture.
- **Pre-commit Hooks**: Developers are expected to use `pre-commit` which runs `ruff`, `mypy`, and a subset of unit tests on staged files.
- **Versioning**: The Python package is versioned at `0.1.0` in `pyproject.toml`, while the frontend is at `3.0.0`.