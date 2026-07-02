The TradeXV2 project utilizes a modern Python build system centered around `setuptools` and `pyproject.toml`, with dependency management handled by `uv` (evidenced by `uv.lock`). The project is structured as a monorepo containing multiple logical components: a Python backend (brokers, analytics, datalake, CLI) and a TypeScript frontend (Vite-based).

### Build & Dependency Management
- **Backend**: Built using `setuptools` with `pyproject.toml` defining the project metadata, dependencies, and entry points. Dependencies are locked via `uv.lock`, suggesting the use of the `uv` package manager for fast, deterministic installs. A legacy `requirements.txt` is also present but `pyproject.toml` is the primary source of truth.
- **Frontend**: Located in `frontend/` and `archive/frontend-v1-2026-06-14/`, built using Vite with TypeScript. Dependencies are managed via `package.json` and `package-lock.json`.

### Continuous Integration (CI)
The project employs GitHub Actions for CI/CD, defined in `.github/workflows/`:
1. **`ci.yml`**: The primary workflow triggered on push/PR to `main` and `develop`. It includes:
   - **Linting & Type Checking**: Uses `ruff` for linting/formatting and `mypy` for type checking (currently non-blocking due to existing errors).
   - **Security Scanning**: Runs `bandit` for static security analysis and `safety` for dependency vulnerability checks.
   - **Testing**: Executes unit and contract tests using `pytest` with coverage reporting (threshold: 60%). It also runs quant parity tests and replay determinism verifications.
   - **Integration Tests**: Runs Dhan sandbox integration tests on pushes to `main` (gated by secrets).
2. **`production_gate.yml`**: A stricter workflow triggered on release branches/tags. It enforces higher quality standards:
   - **Coverage Threshold**: Requires 90% code coverage.
   - **Chaos & Memory Tests**: Runs chaos engineering tests (network partitions, data corruption) and memory leak regression tests.
   - **Security Gate**: Fails on HIGH severity vulnerabilities.
   - **Certification**: Runs a custom `scripts/production_certification.py` script to validate production readiness.
3. **`load-test.yml`**: Scheduled weekly load testing using the paper broker to enforce performance budgets (latency/RPS).

### Code Quality & Pre-commit
- **Pre-commit Hooks**: Configured in `.pre-commit-config.yaml` to run `ruff` (lint/format), `mypy` (type check), and standard checks (trailing whitespace, YAML/TOML validation) before commits.
- **Linting**: `ruff` is configured for speed and comprehensive rule sets (pycodestyle, pyflakes, isort, bugbear, etc.).
- **Type Checking**: `mypy` is configured with strict settings but currently allows failures in CI to facilitate incremental adoption.

### Deployment & Containerization
- **No Dockerfiles**: The repository currently lacks `Dockerfile` or `docker-compose.yml` configurations. Multiple documentation files (`ACTIONABLE_DEVELOPMENT_PLAN.md`, `COMPREHENSIVE_MULTI_EXPERT_REVIEW.md`) identify this as a critical gap ("Operational Readiness: 3/10") and recommend adding containerization for production deployment.
- **Deployment Strategy**: Currently relies on direct Python execution (`pip install -e .`) within CI environments. Production deployment mechanisms are not yet implemented in the codebase.