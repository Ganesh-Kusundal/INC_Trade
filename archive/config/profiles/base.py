"""Base profile definition for environment-specific configuration.

All environment profiles inherit from this base class and override
specific settings.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EnvironmentProfile(ABC):
    """Abstract base class for environment profiles."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Profile name (dev/staging/prod)."""
        pass

    @property
    @abstractmethod
    def log_level(self) -> str:
        """Logging level for this environment."""
        pass

    @property
    @abstractmethod
    def debug_enabled(self) -> bool:
        """Whether debug features are enabled."""
        pass

    @property
    @abstractmethod
    def mock_brokers_allowed(self) -> bool:
        """Whether mock/sandbox brokers are allowed."""
        pass

    @property
    @abstractmethod
    def strict_validation(self) -> bool:
        """Whether strict configuration validation is enforced."""
        pass

    @property
    @abstractmethod
    def allow_live_orders_by_default(self) -> bool:
        """Whether live orders are allowed by default."""
        pass

    @property
    def encryption_required(self) -> bool:
        """Whether encryption is required for token state files."""
        return False

    @property
    def api_auth_required(self) -> bool:
        """Whether API authentication is required."""
        return False

    @property
    def rate_limit_enabled(self) -> bool:
        """Whether rate limiting is enabled."""
        return False

    @property
    def rate_limit_per_minute(self) -> int:
        """Rate limit requests per minute."""
        return 0

    @property
    def cors_origins(self) -> list[str]:
        """Allowed CORS origins."""
        return ["http://localhost:5173", "http://localhost:3000"]

    @property
    def observability_enabled(self) -> bool:
        """Whether observability features are enabled."""
        return False

    @property
    def metrics_endpoint(self) -> str | None:
        """Metrics endpoint URL (if enabled)."""
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to dictionary.

        Returns:
            Dict representation of profile settings.
        """
        return {
            "name": self.name,
            "log_level": self.log_level,
            "debug_enabled": self.debug_enabled,
            "mock_brokers_allowed": self.mock_brokers_allowed,
            "strict_validation": self.strict_validation,
            "allow_live_orders_by_default": self.allow_live_orders_by_default,
            "encryption_required": self.encryption_required,
            "api_auth_required": self.api_auth_required,
            "rate_limit_enabled": self.rate_limit_enabled,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "cors_origins": self.cors_origins,
            "observability_enabled": self.observability_enabled,
            "metrics_endpoint": self.metrics_endpoint,
        }


@dataclass
class BaseProfile(EnvironmentProfile):
    """Base profile with common defaults.

    Subclasses should override specific properties.
    """

    _name: str = "base"
    _log_level: str = "INFO"
    _debug_enabled: bool = False
    _mock_brokers_allowed: bool = False
    _strict_validation: bool = True
    _allow_live_orders_by_default: bool = False
    _encryption_required: bool = False
    _api_auth_required: bool = False
    _rate_limit_enabled: bool = False
    _rate_limit_per_minute: int = 0
    _cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    _observability_enabled: bool = False
    _metrics_endpoint: str | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def log_level(self) -> str:
        return self._log_level

    @property
    def debug_enabled(self) -> bool:
        return self._debug_enabled

    @property
    def mock_brokers_allowed(self) -> bool:
        return self._mock_brokers_allowed

    @property
    def strict_validation(self) -> bool:
        return self._strict_validation

    @property
    def allow_live_orders_by_default(self) -> bool:
        return self._allow_live_orders_by_default

    @property
    def encryption_required(self) -> bool:
        return self._encryption_required

    @property
    def api_auth_required(self) -> bool:
        return self._api_auth_required

    @property
    def rate_limit_enabled(self) -> bool:
        return self._rate_limit_enabled

    @property
    def rate_limit_per_minute(self) -> int:
        return self._rate_limit_per_minute

    @property
    def cors_origins(self) -> list[str]:
        return self._cors_origins

    @property
    def observability_enabled(self) -> bool:
        return self._observability_enabled

    @property
    def metrics_endpoint(self) -> str | None:
        return self._metrics_endpoint
