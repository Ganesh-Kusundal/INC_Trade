The project employs a modern, hybrid build system leveraging **UV** for high-performance Python dependency management and **GitHub Actions** for a multi-stage CI/CD pipeline. The frontend is built using **Vite** and **TypeScript**, managed via `npm`. 

### Core Build Tools
- **Python**: Managed via `pyproject.toml` (setuptools backend) and locked with `uv.lock`. The project uses `uv` for fast dependency resolution and installation.
- **Frontend**: Managed via `package.json` in the `frontend/` directory, using Vite for bundling and Vitest for testing.
- **Linting & Formatting**: Enforced via **Ruff** (fast linter/formatter), **MyPy** (static type checking), and **Import Linter** (architectural boundary enforcement).
- **Pre-commit Hooks**: Configured in `.pre-commit-config.yaml` to run Ruff, MyPy, and smoke tests on staged files.

### CI/CD Pipeline (GitHub Actions)
The CI pipeline is split into several specialized workflows:
1. **`ci.yml`**: The main pipeline triggered on PRs and pushes. It includes:
   - **Lint & Type Check**: Runs Ruff, MyPy (non-blocking currently), Bandit (security), and Import Linter.
   - **Unit & Contract Tests**: Runs pytest with coverage enforcement (80% overall, 85% brokers, 90% OMS core).
   - **Quant Parity**: Verifies deterministic behavior of quantitative analytics.
   - **Frontend**: Runs typechecking, unit tests, and builds the React app.
   - **E2E & Stress Tests**: Runs end-to-end trading flow simulations and concurrency stress tests.
   - **Flaky Test Detection**: Automatically detects non-deterministic tests on main branch pushes.

2. **`production_gate.yml`**: A strict gate for release branches (`release/**` or `v*.*.*`). It requires:
   - **Chaos Engineering Tests**: Validates resilience against network partitions and data corruption.
   - **Memory Leak Regression**: Ensures no memory leaks in long-running processes.
   - **Security Scan**: Fails on HIGH severity Bandit findings.
   - **Production Certification**: Runs a custom `scripts/production_certification.py` script that must return `PASS`.

3. **`load-test.yml`** & **`mutation_nightly.yml`**: Specialized jobs for performance benchmarking and mutation testing (mutmut) respectively.

### Key Conventions & Rules
- **Coverage Thresholds**: Strict minimums are enforced: 80% global, 85% for broker adapters, and 90% for the core Order Management System (OMS).
- **Architectural Linting**: `import-linter` enforces layer boundaries (e.g., `domain` cannot import `brokers`, `analytics` cannot import `oms`).
- **Test Markers**: Extensive use of pytest markers (`unit`, `integration`, `sandbox`, `live_readonly`, `chaos`, `stress`) to allow selective test execution.
- **Determinism**: Replay determinism is verified in every CI run to ensure backtesting and live trading parity.
- **Security**: Bandit and Safety checks are integrated into both CI and the production gate, with zero-tolerance for HIGH severity issues in production.