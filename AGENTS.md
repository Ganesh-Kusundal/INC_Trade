# AGENTS.md — Architecture & Coding Rules for brokers/

## Architecture: Hexagonal (Ports & Adapters)

```
domain/      → zero dependencies (pure business logic)
core/        → zero dependencies (generic utilities)
utils/       → zero dependencies (price math)
config/      → domain.exceptions only
ports/       → domain/ + self-references only
services/    → domain/ + ports/ + utils/ + self only
resilience/  → domain/ + self only
infrastructure/ → (accepts external deps, bridges to adapters)
adapters/    → implements ports, depends on infrastructure
```

### Import Direction Rules

Imports flow **inward only**:
- `domain` never imports from any other brokers package
- `ports` imports only from `domain` and other `ports` modules
- `services` imports from `domain`, `ports`, `utils`, and other `services` modules
- `resilience` imports from `domain` and other `resilience` modules
- `config` imports only from `domain.exceptions`
- `core` and `utils` have zero internal dependencies

**Enforced by**: `brokers/tests/unit/test_architecture.py::TestBoundaryRules`

### Port Protocol Rules

All ports in `brokers/ports/` must:
1. Inherit from `Protocol` (structural typing)
2. Be decorated with `@runtime_checkable`
3. Be exported from `brokers/ports/__init__.py`

**Enforced by**: `brokers/tests/unit/test_architecture.py::TestPortStructure`

### Exception Hierarchy

All exceptions must inherit from `TradeXV2Error` (the root).
Error codes are defined in `domain/error_codes.py` as string constants.

**Enforced by**: `brokers/tests/unit/test_architecture.py::TestExceptionHierarchy`

## Test Mandates

- **781+ tests pass, 0 regressions** — this bar must not drop
- Unit tests: `pytest -m "not integration"` (or default)
- Integration tests: `pytest -m integration` (requires credentials)
- Architecture tests: `pytest -m architecture` (runs in <1s, always)
- All new code must include tests
- Contract tests validate port implementations

## Coding Standards

- **Formatter**: ruff format (double quotes, 100-char line length)
- **Linter**: ruff (E, W, F, I, UP, B, SIM, TCH, RUF rule sets)
- **Type checker**: mypy strict (domain/, ports/, services/)
- **Pre-commit hooks**: ruff lint, ruff format, mypy, architecture boundary check
- **No external dependencies** in domain/, core/, utils/, ports/
- **Docstrings**: module-level only

## Key Files

| File | Purpose |
|------|---------|
| `brokers/tests/unit/test_architecture.py` | Architecture guardrails |
| `brokers/tests/pytest.ini` | Test markers |
| `pyproject.toml` | Tool configs (ruff, mypy, pytest, coverage) |
| `.pre-commit-config.yaml` | Pre-commit hooks |
