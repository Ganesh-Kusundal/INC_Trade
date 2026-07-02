The repository employs a hybrid dependency management strategy, utilizing **UV** for Python dependencies and **NPM** for the frontend TypeScript/React application.

### Python Dependency Management (UV)
- **Primary Tool**: The project uses `uv` as its package installer and resolver, evidenced by the presence of `uv.lock`. This lockfile ensures deterministic builds by pinning exact versions and hashes for all transitive dependencies.
- **Manifests**: 
  - `pyproject.toml`: Serves as the primary source of truth for project metadata and dependencies. It defines core dependencies (e.g., `pandas`, `pydantic`, `aiohttp`) and optional development dependencies (`pytest`, `ruff`, `mypy`).
  - `requirements.txt`: Exists as a legacy or alternative flat-file manifest, listing direct dependencies without the hierarchical structure of `pyproject.toml`.
- **Build System**: Uses `setuptools` via `pyproject.toml` (`[build-system]`), indicating a standard Python packaging approach compatible with `pip` and `uv`.
- **Security & Auditing**: The `dev` dependencies include `bandit` for static security analysis and `pip-audit` for vulnerability scanning, integrated into the development workflow.

### Frontend Dependency Management (NPM)
- **Primary Tool**: The `frontend/` directory uses `npm` (Node Package Manager) with `package-lock.json` for deterministic installs.
- **Stack**: Built on React 18, Vite, and TypeScript. Key dependencies include `zustand` for state management and `tailwindcss` for styling.
- **Isolation**: Frontend dependencies are strictly isolated within the `frontend/` directory, preventing conflict with the Python backend environment.

### Automation & Updates
- **Dependabot**: Configured in `.github/dependabot.yml` to automatically check for updates weekly for both `pip` (Python) and `github-actions`. It groups minor and patch updates to reduce PR noise.
- **Pre-commit Hooks**: Managed via `.pre-commit-config.yaml`, enforcing code quality and dependency-related checks (e.g., `check-toml`, `detect-private-key`) before commits. It also runs a "smoke test" suite using `pytest` on staged files.
- **Lockfile Strategy**: Both `uv.lock` and `package-lock.json` are committed to the repository, ensuring that CI/CD pipelines and local development environments use identical dependency versions.

### Developer Conventions
- **Installation**: Developers should use `uv sync` or `uv pip install -r requirements.txt` for Python, and `npm install` for the frontend.
- **Updates**: Dependabot handles routine updates. Major version bumps or new dependencies should be added to `pyproject.toml` (Python) or `package.json` (Frontend) and the respective lockfiles regenerated.