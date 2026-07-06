"""Central configuration package for TradeXV2.

Provides configuration schema, validation, and environment profiles.

Usage::

    from brokers_core.config import (
        AppConfig,
        get_config,
        load_dhan_config,
        load_upstox_config,
        validate_config,
        load_profile,
    )

    cfg = get_config()
    dhan_cfg = load_dhan_config()
    profile = load_profile()
"""

from brokers_core.config.defaults import DEFAULT_CONFIG, get_config, reset_config
from brokers_core.config.endpoints import Dhan, Upstox
from brokers_core.config.indices import (
    INDEX_SYMBOLS,
    INDEX_TO_FNO_EXCHANGE,
    IndexEntry,
    get_index_entry,
    index_upstox_key,
    is_index,
    list_indices,
    upstox_index_segment,
)
from brokers_core.config.profiles import EnvironmentProfile, load_profile
from brokers_core.config.schema import (
    ApiConfig,
    AppConfig,
    DhanConfig,
    TradingConfig,
    UpstoxConfig,
    load_api_config,
    load_dhan_config,
    load_trading_config,
    load_upstox_config,
)
from brokers_core.config.secrets_manager import SecretsManager
from brokers_core.config.validator import (
    ConfigValidationError,
    ConfigValidator,
    ValidationProfile,
    validate_config,
)

__all__ = [
    "DEFAULT_CONFIG",
    "INDEX_SYMBOLS",
    "INDEX_TO_FNO_EXCHANGE",
    "ApiConfig",
    "AppConfig",
    "ConfigValidationError",
    "ConfigValidator",
    "Dhan",
    "DhanConfig",
    "EnvironmentProfile",
    "IndexEntry",
    "SecretsManager",
    "TradingConfig",
    "Upstox",
    "UpstoxConfig",
    "ValidationProfile",
    "get_config",
    "get_index_entry",
    "index_upstox_key",
    "is_index",
    "list_indices",
    "load_api_config",
    "load_dhan_config",
    "load_profile",
    "load_trading_config",
    "load_upstox_config",
    "reset_config",
    "upstox_index_segment",
    "validate_config",
]
