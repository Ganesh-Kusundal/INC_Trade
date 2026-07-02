The TradeXV2 repository employs a **hybrid, file-and-environment-variable-based configuration system** designed for multi-broker algorithmic trading. It avoids heavy external dependencies (like `python-dotenv` in core logic) in favor of a lightweight, custom `.env` parser and structured dataclasses.

### 1. Core Approach & Patterns
- **Dataclass-Based Settings**: Configuration is modeled using frozen `dataclasses` (e.g., `DhanConnectionSettings`, `UpstoxConnectionSettings`) that inherit from a common `BrokerSettings` base. This ensures immutability and type safety.
- **Loader Pattern**: Each broker adapter implements a specific `SettingsLoader` (e.g., `DhanSettingsLoader`, `UpstoxSettingsLoader`) that inherits from `SettingsLoaderBase`. These loaders handle the resolution of values from environment variables, `.env` files, or `.properties` files.
- **Environment Variable Precedence**: The system prioritizes environment variables. Loaders can optionally seed `os.environ` by parsing a specified `.env` file (defaulting to `.env.local` then `.env`).
- **Secrets Management**: Sensitive credentials (TOTP secrets, PINs) are managed via a `SecretsManager` class. It supports fetching values from environment variables first, falling back to reading from gitignored text files in the `config/` directory (e.g., `config/dhan-totp-secret.txt`).

### 2. Key Files and Packages
- **`brokers/common/settings.py`**: Defines the `BrokerSettings` base dataclass and `SettingsLoaderBase` utility class. This is the central contract for all broker configurations.
- **`brokers/common/env_loader.py`**: A minimal, dependency-free `.env` file parser that populates `os.environ`.
- **`config/secrets_manager.py`**: Unified interface for retrieving secrets from env vars or local files.
- **`brokers/dhan/settings.py`** & **`brokers/upstox/auth/config.py`**: Broker-specific implementations of settings dataclasses and loaders.
- **`datalake/api/config.py`**: Uses a simple `APIConfig` dataclass for API server settings (CORS, ports), demonstrating the pattern's use beyond brokers.
- **`config/` Directory**: Contains example `.properties` files (`*.example`) and gitignored credential templates. It also holds static configuration like `scan-profiles.json` and `indices.py`.

### 3. Architecture and Conventions
- **Layered Resolution**: 
  1. **Defaults**: Defined in dataclass fields or loader constants.
  2. **Files**: `.env.local` or `.properties` files are parsed if present.
  3. **Environment**: `os.environ` is the final authority, allowing container/orchestrator overrides.
- **Broker Agnosticism**: The `BrokerSettings` base ensures common fields (like `client_id`, `http_timeout`) are consistent across different broker adapters.
- **Security**: Secrets are never committed. The `.gitignore` excludes `*.properties` (non-example) and specific secret files (`*-pin.txt`, `*-totp-secret.txt`).
- **No External Config Libraries**: The project explicitly avoids `python-dotenv` in its core loading logic (`env_loader.py`), implementing a simple parser instead to reduce dependencies.

### 4. Rules for Developers
- **Use Dataclasses**: Always define new configuration structures as frozen dataclasses.
- **Inherit from Base**: New broker adapters must inherit from `BrokerSettings` and `SettingsLoaderBase` to maintain consistency.
- **Secrets Handling**: Never hardcode secrets. Use `SecretsManager` for TOTP/PINs and environment variables for API keys/tokens.
- **File Naming**: Use `.env.local` for local development overrides. Use `.properties.example` files in `config/` to document required keys for production/sandbox environments.
- **Env Var Naming**: Follow the `{BROKER}_{KEY}` convention (e.g., `DHAN_CLIENT_ID`, `UPSTOX_ACCESS_TOKEN`). Loaders support some legacy aliases but new code should stick to the standard.