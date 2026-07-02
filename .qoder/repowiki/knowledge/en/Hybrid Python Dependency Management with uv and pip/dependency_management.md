The TradeXV2 repository employs a hybrid dependency management strategy for its Python backend, primarily leveraging **uv** for high-performance resolution and locking, while maintaining compatibility with standard **pip** workflows. The frontend is managed via **npm**.

### 1. Python Backend Strategy
- **Primary Tool**: `uv` is used as the package installer and resolver, evidenced by the presence of `uv.lock`. This lockfile provides deterministic, cross-platform dependency resolution with support for multiple Python versions (3.10–3.14) and architectures.
- **Manifest Files**:
  - `pyproject.toml`: Serves as the single source of truth for project metadata, core dependencies, and optional development dependencies (`dev` extra). It configures build backends (`setuptools`) and tooling (pytest, mypy, ruff).
  - `requirements.txt`: A flat list of dependencies, likely used for legacy compatibility or specific deployment environments that do not yet support `uv` or `pyproject.toml` directly. It includes broker-specific SDKs like `dhanhq` and `upstox-totp`.
- **Versioning**: Dependencies use minimum version constraints (e.g., `pandas>=2.0`, `pydantic>=2.5`) in `pyproject.toml`, allowing `uv` to resolve the latest compatible versions into the lockfile.

### 2. Frontend Strategy
- **Package Manager**: `npm` is used for the React-based frontend (`frontend/` and `archive/frontend-v1-2026-06-14/`).
- **Locking**: `package-lock.json` ensures deterministic installs for Node.js dependencies.
- **Key Dependencies**: React 18, Vite 6, TypeScript 5, and Tailwind CSS.

### 3. Automation and Maintenance
- **Dependabot**: Configured in `.github/dependabot.yml` to automatically update Python (`pip`) and GitHub Actions dependencies on a weekly basis. It groups minor and patch updates to reduce PR noise.
- **Pre-commit Hooks**: `.pre-commit-config.yaml` enforces code quality and dependency hygiene before commits. It includes:
  - `ruff` for linting and formatting.
  - `mypy` for static type checking.
  - `pytest-smoke` for running fast unit tests on staged files.
  - Security checks like `detect-private-key` and `check-added-large-files`.

### 4. Developer Conventions
- **Installation**: Developers should prefer `uv sync` or `uv pip install -e .` to leverage the lockfile for consistent environments. 
- **Adding Dependencies**: New dependencies should be added to `pyproject.toml` under `[project.dependencies]` or `[project.optional-dependencies]`, followed by regenerating the lockfile with `uv lock`.
- **Isolation**: The project uses virtual environments (`.venv/`), and `uv` manages these efficiently. Broker-specific SDKs are treated as standard dependencies, with no vendoring observed.