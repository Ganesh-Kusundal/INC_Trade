The TradeXV2 repository employs a hybrid dependency management strategy, utilizing **UV** for Python dependencies and **NPM** for the frontend TypeScript/React application. This approach ensures deterministic builds, rapid resolution, and automated security updates.

### Python Dependency System (UV)
- **Primary Tool**: The project uses `uv` as its package installer and resolver, evidenced by the presence of `uv.lock`. This lockfile provides a comprehensive, cross-platform dependency graph with integrity hashes, replacing traditional `pip` + `requirements.txt` workflows for production consistency.
- **Manifests**: 
  - `pyproject.toml`: Serves as the single source of truth for project metadata, core dependencies (e.g., `pandas`, `pydantic`, `aiohttp`), and optional development dependencies (`dev` group including `pytest`, `ruff`, `mypy`).
  - `requirements.txt`: Exists as a legacy or alternative flat-file manifest, listing direct dependencies without the hierarchical resolution provided by `uv.lock`.
- **Build Backend**: Uses `setuptools` (`setuptools.build_meta`) for packaging, as defined in `[build-system]`.

### Frontend Dependency System (NPM)
- **Primary Tool**: The `frontend/` directory uses `npm` (Node Package Manager) with `package-lock.json` for deterministic installs.
- **Manifest**: `frontend/package.json` defines the React-based UI stack, including `vite` for building, `typescript` for type safety, and `zustand` for state management.
- **Tooling**: Dependencies like `@vitejs/plugin-react` and `tailwindcss` are managed locally within the frontend module's `node_modules`.

### Automation and Maintenance
- **Dependabot**: Configured in `.github/dependabot.yml` to automatically monitor and update dependencies:
  - **Python**: Weekly checks on Mondays for `pip` ecosystem packages, grouped by minor/patch updates to reduce PR noise.
  - **GitHub Actions**: Weekly updates for CI/CD workflow actions.
- **Pre-commit Hooks**: `.pre-commit-config.yaml` enforces code quality and dependency-related checks before commits, including:
  - `ruff` for linting and formatting.
  - `mypy` for static type checking (specifically targeting the `brokers/` module).
  - Security hooks like `detect-private-key` and `check-added-large-files`.

### Developer Conventions
- **Lockfile Priority**: Developers should rely on `uv.lock` for environment reproduction rather than manually editing `requirements.txt`.
- **Environment Isolation**: The presence of `.venv/` and `venv/` directories suggests the use of virtual environments, which `uv` manages efficiently.
- **Security**: Regular automated scans via Dependabot and pre-commit security hooks ensure that third-party libraries remain secure and up-to-date.