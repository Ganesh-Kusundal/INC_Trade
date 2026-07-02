The TradeXV2 configuration system is a **hybrid, layered approach** combining environment variables (`.env` files), broker-specific property files, and centralized Python dataclasses. It prioritizes security for credentials while maintaining flexibility for runtime tuning across multiple brokers (Dhan, Upstox, ICICI) and environments (Live, Sandbox, Paper).

### 1. Core Approach & Patterns

*   **Environment-First Loading**: The primary mechanism for loading secrets and runtime flags is via `.env` files (e.g., `.env.local`, `.env.upstox`). A custom, dependency-free parser (`brokers.common.env_loader`) reads these files into `os.environ` at startup.
*   **Settings Dataclasses**: Configuration is strongly typed using frozen `dataclasses` (e.g., `DhanConnectionSettings`, `UpstoxConnectionSettings`). These inherit from a common `BrokerSettings` base, ensuring consistent fields like `client_id`, `http_timeout`, and `pool_maxsize` across all adapters.
*   **Loader Pattern**: Each broker implements a `SettingsLoader` (e.g., `DhanSettingsLoader`) that inherits from `SettingsLoaderBase`. These loaders handle:
    *   Discovering and parsing `.env` or `.properties` files.
    *   Type conversion (string env vars to `int`, `float`, `bool`).
    *   Validation of required fields (raising `ValueError` if missing).
    *   Support for legacy aliases and multiple candidate keys (e.g., `CLIENT_ID` vs `API_KEY`).
*   **Centralized Endpoints**: API URLs and WebSocket endpoints are decoupled from credentials and stored in `config.endpoints.py` as static constants or factory methods (`Upstox.production()`, `Dhan.REST_BASE`). This prevents hard-coded strings in adapter logic.
*   **Composition Root**: The CLI and API servers use a "composition root" pattern (`cli.services.compose.build_runtime`, `datalake.api.main.create_app`) where configuration is loaded once, services are wired, and the resulting `Runtime` or `FastAPI` app is immutable for the session.

### 2. Key Files & Packages

| File/Package | Role |
| :--- | :--- |
| `brokers/common/settings.py` | Base `BrokerSettings` dataclass and `SettingsLoaderBase` with parsing utilities. |
| `brokers/common/env_loader.py` | Minimalist `.env` parser (no `python-dotenv` dependency) that populates `os.environ`. |
| `brokers/dhan/settings.py` | `DhanConnectionSettings` and `DhanSettingsLoader` for Dhan-specific config (TOTP, PIN, URLs). |
| `brokers/upstox/auth/config.py` | `UpstoxConnectionSettings` and `UpstoxSettingsLoader` for Upstox-specific config (Auth modes, tokens). |
| `config/endpoints.py` | Central registry for all broker API URLs (REST, WebSocket, Asset downloads). |
| `config/scan-profiles.json` | Committed JSON configuration for analytics scanner profiles (universe, criteria). |
| `cli/services/broker_registry.py` | Maps broker names to their default `.env` paths (e.g., `dhan` -> `.env.local`). |
| `cli/services/compose.py` | Composition root that loads config and wires the trading runtime. |
| `datalake/api/config.py` | `APIConfig` dataclass for FastAPI server settings (CORS, ports, rate limits). |
| `pyproject.toml` | Defines tool configurations for `pytest`, `mypy`, `ruff`, and `coverage`. |

### 3. Architecture & Conventions

*   **Layered Precedence**: 
    1.  **Environment Variables**: Highest precedence. Set via shell or loaded from `.env` files.
    2.  **Property Files**: Broker-specific `.properties` files (e.g., `dhan-local.properties`) are supported for backward compatibility but are largely migrated to `.env` format.
    3.  **Defaults**: Sensible defaults are defined in the `Settings` dataclasses (e.g., `http_timeout=15.0`, `pool_connections=50`).
*   **Secrets Management**: 
    *   Credentials (Client IDs, Secrets, Tokens, TOTP secrets) are **never committed**. 
    *   Example templates (`*.example`) are provided in `config/`.
    *   Sensitive files like `dhan-pin.txt` and `dhan-totp-secret.txt` are gitignored and referenced by path in env vars.
    *   Token state is persisted in `runtime/dhan-token-state.json` and updated atomically with file locking.
*   **Broker Agnosticism**: The `BrokerSettings` base class ensures that higher-level services (OMS, Risk Manager) can rely on a consistent configuration interface regardless of the active broker.
*   **Environment Segregation**: Distinct `.env` files are used for different contexts:
    *   `.env.local`: Primary Dhan live credentials.
    *   `.env.upstox`: Upstox credentials (Live/Sandbox controlled by `UPSTOX_ENVIRONMENT`).
    *   `RISK_FAIL_OPEN=1`: A specific env var required to override safety gates for placeholder capital.

### 4. Rules for Developers

*   **Add New Config Fields**: 
    1.  Add the field to the relevant `ConnectionSettings` dataclass with a default.
    2.  Update the corresponding `SettingsLoader.from_env()` to read it via `_get()`, `_get_int()`, etc.
    3.  Add the key to the `.env.example` template.
*   **Accessing Config**: Never read `os.environ` directly in business logic. Use the injected `Settings` object or the `SettingsLoader`.
*   **Adding Endpoints**: All new API URLs must be added to `config/endpoints.py`. Do not hard-code URLs in adapter classes.
*   **Security**: 
    *   Never commit `.env`, `.properties`, or `.txt` secret files.
    *   Use `atomic_write` or file locking when updating token files to prevent race conditions.
*   **Testing**: Use `from_dict` methods in loaders for unit tests to avoid dependency on local `.env` files. Mock `os.environ` if necessary.