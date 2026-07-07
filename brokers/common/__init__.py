"""brokers.common — shared infrastructure across all broker providers.

Public API:
    - InstrumentResolver, InMemoryInstrumentResolver, ResolvedInstrument
    - AuthManager, TokenState, TokenStateStore, TotpGenerator, TotpCooldownGuard
    - CredentialResolver, DhanCredentials, UpstoxCredentials
    - SharedInstrumentRegistry, ResolvedInstrumentInfo
    - BaseReconciliation, ReconciliationDrift
    - BaseMarketFeed, BaseOrderStream
    - IdempotencyCacheProtocol, MemoryIdempotencyCache
"""

from brokers.common.instrument_resolver import (
    InstrumentNotFoundError,
    InstrumentResolver,
    InMemoryInstrumentResolver,
    ResolvedInstrument,
)
from brokers.common.auth.token_manager import (
    AuthManager,
    EnvTokenStateStore,
    JsonTokenStateStore,
    TokenSource,
    TokenState,
    TokenStateStore,
    TotpCooldownGuard,
    TotpGenerator,
)
from brokers.common.auth.credential_resolver import (
    CredentialResolver,
    DhanCredentials,
    UpstoxCredentials,
)
from brokers.common.instrument_registry import SharedInstrumentRegistry, ResolvedInstrumentInfo
from brokers.common.reconciliation import BaseReconciliation, ReconciliationDrift
from brokers.common.streaming.base_market_feed import BaseMarketFeed
from brokers.common.streaming.base_order_stream import BaseOrderStream
from brokers.common.idempotency import (
    IdempotencyCacheProtocol,
    IdempotencyStats,
    MemoryIdempotencyCache,
    RedisIdempotencyCache,
)

__all__ = [
    # Instrument resolution
    "InstrumentNotFoundError",
    "InstrumentResolver",
    "InMemoryInstrumentResolver",
    "ResolvedInstrument",
    # Auth
    "AuthManager",
    "EnvTokenStateStore",
    "JsonTokenStateStore",
    "TokenSource",
    "TokenState",
    "TokenStateStore",
    "TotpCooldownGuard",
    "TotpGenerator",
    # Credentials
    "CredentialResolver",
    "DhanCredentials",
    "UpstoxCredentials",
    # Instrument registry
    "SharedInstrumentRegistry",
    "ResolvedInstrumentInfo",
    # Reconciliation
    "BaseReconciliation",
    "ReconciliationDrift",
    # Streaming bases
    "BaseMarketFeed",
    "BaseOrderStream",
    # Idempotency
    "IdempotencyCacheProtocol",
    "IdempotencyStats",
    "MemoryIdempotencyCache",
    "RedisIdempotencyCache",
]
