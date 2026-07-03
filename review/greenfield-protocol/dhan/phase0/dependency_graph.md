# Phase 0 Dependency Graph — Dhan Broker Foundation

## Internal Dependencies

### Core factory and settings chain

```
archive/brokers/dhan/factory.py
├── archive/brokers/dhan/account_registry.py
├── archive/brokers/dhan/connection.py
├── archive/brokers/dhan/gateway.py
├── archive/brokers/dhan/http_client.py
├── archive/brokers/dhan/settings.py
│   ├── archive/brokers/common/settings.py
│   ├── archive/brokers/dhan/config.py
│   ├── archive/brokers/dhan/config_loader.py
│   ├── archive/config/endpoints.py
│   ├── archive/config/secrets_manager.py
│   └── archive/domain/constants/auth.py
├── archive/brokers/dhan/secret_utils.py
├── archive/brokers/dhan/token_scheduler.py
├── archive/brokers/common/auth/__init__.py  (AuthManager, JsonTokenStateStore, TokenSource, TokenState)
│   └── archive/brokers/common/auth/token.py
├── archive/brokers/common/observability/health_check.py
│   └── archive/infrastructure/health.py
└── archive/brokers/common/gateway.py  (MarketDataGateway)
```

### Configuration systems

```
archive/config/schema.py
├── pydantic (external)
└── os (stdlib)

archive/config/defaults.py
└── archive/config/schema.py

archive/config/feature_flags.py
├── archive/infrastructure/metrics.py
└── hashlib, os, threading (stdlib)

archive/config/secrets_manager.py
├── os, pathlib (stdlib)

archive/config/endpoints.py
└── dataclasses (stdlib)

archive/config/validator.py
├── archive/brokers/common/resilience/errors.py
└── os, dataclasses, enum (stdlib)

archive/config/profiles/__init__.py
├── archive/config/profiles/base.py
├── archive/config/profiles/dev.py
├── archive/config/profiles/staging.py
└── archive/config/profiles/prod.py
```

### Bootstrap and environment loading

```
archive/brokers/common/bootstrap.py
├── archive/brokers/common/adapters/__init__.py
├── archive/brokers/common/adapters/market_data_gateway_adapter.py
├── archive/brokers/common/gateway.py
├── archive/brokers/common/infrastructure.py
├── archive/brokers/common/intelligent_market_gateway.py
└── archive/brokers/common/policy.py

archive/brokers/common/auth/environment_bootstrap.py
└── archive/brokers/common/auth/credential_resolver.py
    └── archive/brokers/common/env_loader.py

archive/brokers/common/env_loader.py
└── os, pathlib (stdlib)
```

### Dependency injection and logging

```
archive/infrastructure/di.py
├── archive/domain/exceptions.py
└── archive/infrastructure/di_scopes.py

archive/infrastructure/logging_config.py
├── archive/infrastructure/correlation.py
└── json, logging, os, re, sys, datetime (stdlib)

archive/infrastructure/health.py
└── abc, dataclasses, enum, threading, time (stdlib)
```

## External Dependencies

| Package | Minimum Version | Where Used | Phase 0 Relevance |
|---------|-----------------|------------|-------------------|
| `pydantic` | >= 2.0.0 | `archive/config/schema.py` | Central `AppConfig` validation |
| `pydantic_settings` | (implied by greenfield) | `brokers/config_app.py` | Greenfield already uses this |
| `requests` | >= 2.31.0 | `archive/brokers/dhan/factory.py` | TOTP token generation HTTP call |
| `pyotp` | >= 2.6.0 | `archive/brokers/dhan/factory.py` | TOTP code generation |
| `dhanhq` | >= 2.0.0 | Broker adapter modules | Out of Phase 0 scope |
| `schedule` | >= 1.2.0 | `archive/brokers/dhan/token_scheduler.py` | Background scheduler (Phase 1) |
| `psutil` | >= 5.0.0 | Various observability modules | Out of Phase 0 scope |

**No `python-dotenv` dependency:** The archived code uses a minimal internal parser in `archive/brokers/common/env_loader.py`. The greenfield `brokers/config_app.py` currently relies on `pydantic_settings` default env file loading.

## Greenfield Baseline Dependencies

```
brokers/config_app.py
└── pydantic, pydantic_settings (external)

brokers/core/di.py
└── typing (stdlib)
```

## Dependency Direction Observations

1. **Bottom-up coupling:** The Dhan factory depends on many upper-layer modules (`gateway`, `connection`, `http_client`, `token_scheduler`). This is expected for a factory, but it also owns lifecycle side effects that should be separated.

2. **Cross-cutting leakage:** `archive/config/feature_flags.py` depends on `archive/infrastructure/metrics.py`, and `archive/infrastructure/logging_config.py` depends on `archive/infrastructure/correlation.py`. These are acceptable cross-cutting dependencies but should be documented.

3. **Duplicate secret reading:** Both `archive/config/secrets_manager.py` and `archive/brokers/dhan/secret_utils.py` implement the same env/file fallback pattern. The greenfield design should consolidate this.

4. **Profile isolation:** `archive/config/profiles` does not depend on other config modules, but other modules do not depend on it either. It is an orphan policy layer.

5. **DI divergence:** The archived `infrastructure.di.Container` is string-keyed with scopes; the greenfield `brokers.core.di.Container` is type-keyed without scopes. Reconciling these is a greenfield design decision, not a behavior to replicate literally.
