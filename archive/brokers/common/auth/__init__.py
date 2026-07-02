"""Broker auth abstractions and token lifecycle helpers."""

from brokers.common.auth.credential_resolver import (
    CANONICAL_ENV_FILES,
    CredentialResolver,
)
from brokers.common.auth.credential_validator import (
    CredentialIssue,
    CredentialValidator,
)
from brokers.common.auth.environment_bootstrap import bootstrap_environment
from brokers.common.auth.jwt_expiry import JwtExpiry
from brokers.common.auth.registry import BrokerAuthError
from brokers.common.auth.token import (
    AuthManager,
    EnvTokenStateStore,
    JsonTokenStateStore,
    TokenSource,
    TokenState,
    TokenStateStore,
    TotpGenerator,
)
from brokers.common.auth.token_policy import should_generate_token

__all__ = [
    "CANONICAL_ENV_FILES",
    "AuthManager",
    "BrokerAuthError",
    "CredentialIssue",
    "CredentialResolver",
    "CredentialValidator",
    "EnvTokenStateStore",
    "JsonTokenStateStore",
    "JwtExpiry",
    "TokenSource",
    "TokenState",
    "TokenStateStore",
    "TotpGenerator",
    "bootstrap_environment",
    "should_generate_token",
]
