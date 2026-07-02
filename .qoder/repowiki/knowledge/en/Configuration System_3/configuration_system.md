The TradeXV2 platform employs a **hybrid, layered configuration system** that combines environment variables, git-ignored property files, and centralized Python constants. It is designed to support multiple broker adapters (Dhan, Upstox, ICICI) with distinct credential requirements while maintaining a unified interface for the application core.

### 1. Configuration Layers & Sources

The system loads configuration in the following order of precedence:
1.  **Environment Variables**: Highest priority. Used for secrets, runtime flags, and overrides.
2.  **.env Files**: Loaded via a custom `brokers.common.env_loader` (no external `python-dotenv` dependency for core logic). 
    -   `.env.local`: Default for Dhan and general CLI usage.
    -   `.env.upstox`: Specific to Upstox broker configuration.
3.  **Property Files (`*.properties`)**: Broker-specific credential templates located in `config/`. These are parsed by broker-specific loaders (e.g., `UpstoxSettingsLoader.from_properties`) and often mirror Java-based trading system conventions.
4.  **Secrets Files**: Git-ignored text files (e.g., `config/dhan-pin.txt`, `config/dhan-totp-secret.txt`) referenced by path in env vars or properties. Managed by `config.secrets_manager.SecretsManager`.
5.  **Python Constants**: Hardcoded defaults and domain-specific mappings in `domain/constants/` and `config/indices.py`.

### 2. Key Components

*   **`config/secrets_manager.py`**: A unified interface for retrieving sensitive data. It checks environment variables first, then falls back to reading from specified file paths. It provides specific helpers for TOTP secrets and PINs for Dhan and Upstox.
*   **`brokers/common/settings.py`**: Defines the base `BrokerSettings` dataclass and `SettingsLoaderBase`. This establishes a consistent pattern for all broker adapters, ensuring fields like `client_id`, `access_token`, and `http_timeout` are handled uniformly.
*   **`brokers/dhan/settings.py` & `brokers/upstox/auth/config.py`**: Broker-specific implementations of settings and loaders. They define prefixes (e.g., `DHAN_`, `UPSTOX_`) and map environment variables/property keys to the `BrokerSettings` dataclass.
*   **`config/endpoints.py`**: A central registry for all broker API URLs (REST and WebSocket). It uses dataclasses and static methods to provide environment-specific endpoints (Production vs. Sandbox) without scattering URLs across the codebase.
*   **`brokers/common/env_loader.py`**: A lightweight, dependency-free `.env` parser that loads key-value pairs into `os.environ`. It is invoked early in the application lifecycle (e.g., in `cli/main.py` and broker factories).
*   **`domain/constants/defaults.py`**: Manages non-secret operational defaults (e.g., `PAPER_INITIAL_CAPITAL`, `RISK_FALLBACK_CAPITAL`). These can be overridden via environment variables (e.g., `PAPER_INITIAL_CAPITAL=500000`).

### 3. Architecture & Conventions

*   **Broker-Specific Prefixes**: Environment variables are namespaced by broker (e.g., `DHAN_CLIENT_ID`, `UPSTOX_API_KEY`). This prevents collisions and allows multiple brokers to be configured simultaneously.
*   **Fail-Safe Defaults**: Most settings have sensible defaults (e.g., `http_timeout=15.0`, `enable_retry=True`). Only critical fields like `client_id` are strictly required.
*   **Immutable Settings**: Configuration is loaded into `@dataclass(frozen=True)` objects. This ensures that settings are read-only after initialization, preventing accidental mutation during runtime.
*   **Separation of Secrets and Config**: Secrets (PINs, TOTP secrets) are kept in separate git-ignored files or env vars, while non-sensitive config (URLs, timeouts) can be committed or stored in `.properties` examples.
*   **Runtime Overrides**: The `TradingRuntimeFactory` and `CLI` allow passing explicit `env_path` arguments, enabling flexible deployment scenarios (e.g., testing with sandbox credentials without changing global env vars).

### 4. Developer Rules

*   **Never Commit Secrets**: All `*.properties` (except `.example`), `*.txt` secrets, and `.env` files are git-ignored. Use the provided `.example` templates as guides.
*   **Use `SettingsLoader`**: Always use the broker-specific `SettingsLoader.from_env()` or `from_properties()` methods to load configuration. Do not access `os.environ` directly for broker credentials.
*   **Centralize Endpoints**: Add new API URLs to `config/endpoints.py`. Do not hardcode URLs in adapter code.
*   **Override via Env Vars**: To change operational defaults (like capital or timeouts), set the corresponding environment variable (e.g., `RISK_FALLBACK_CAPITAL`) rather than modifying Python constants.
*   **Case-Insensitive Keys**: The `env_loader` and property parsers handle keys case-sensitively, but environment variable lookups in `SettingsLoaderBase` typically uppercase keys for consistency.