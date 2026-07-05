"""Credential resolution with environment file and file-based secret fallback.

Each broker has a canonical env file location. Secrets can be provided
either as environment variables or as file paths (Kubernetes-style),
with env var taking precedence.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

CANONICAL_ENV_FILES: dict[str, str | None] = {
    "dhan": ".env.local",
    "upstox": ".env.upstox",
    "paper": None,
}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class CredentialResolver:
    def __init__(self, project_root: Path | None = None):
        self._project_root = project_root or _PROJECT_ROOT

    def resolve_env_path(self, broker: str) -> Path | None:
        filename = CANONICAL_ENV_FILES.get(broker)
        if filename is None:
            return None
        return self._project_root / filename

    def load_broker_env(self, broker: str) -> bool:
        path = self.resolve_env_path(broker)
        if path is None or not path.exists():
            return False
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value
        logger.info("Loaded env file for broker=%s path=%s", broker, path)
        return True


def read_secret(env_key: str, file_key: str | None = None) -> str:
    value = os.environ.get(env_key, "")
    if value:
        return value
    if file_key:
        file_path = os.environ.get(file_key, "")
        if file_path and Path(file_path).is_file():
            return Path(file_path).read_text().strip()
    return ""


@dataclass
class ValidationError:
    """A single credential validation error."""

    broker: str
    key: str
    message: str


@dataclass
class CredentialValidationResult:
    """Result of credential validation."""

    valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def add_error(self, broker: str, key: str, message: str) -> None:
        self.valid = False
        self.errors.append(ValidationError(broker=broker, key=key, message=message))

    def add_warning(self, broker: str, key: str, message: str) -> None:
        self.warnings.append(ValidationError(broker=broker, key=key, message=message))


_BROKER_REQUIRED_VARS: dict[str, list[str]] = {
    "dhan": ["DHAN_CLIENT_ID"],
    "upstox": ["UPSTOX_CLIENT_ID"],
}

_BROKER_SENSITIVE_VARS: dict[str, list[str]] = {
    "dhan": ["DHAN_ACCESS_TOKEN", "DHAN_PIN", "DHAN_TOTP_SECRET"],
    "upstox": ["UPSTOX_ACCESS_TOKEN", "UPSTOX_CLIENT_SECRET"],
}


class CredentialValidator:
    """Validates broker credentials at startup.

    Checks required vars are present, sensitive vars are non-empty,
    and basic format constraints hold.
    """

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = env if env is not None else dict(os.environ)

    def validate(self, brokers: list[str] | None = None) -> CredentialValidationResult:
        """Validate credentials for specified brokers.

        Args:
            brokers: List of broker names to validate. Defaults to all known brokers.
        """
        if brokers is None:
            brokers = list(_BROKER_REQUIRED_VARS.keys())

        result = CredentialValidationResult()

        for broker in brokers:
            self._validate_broker(broker, result)

        return result

    def validate_or_raise(self, brokers: list[str] | None = None) -> CredentialValidationResult:
        """Validate and raise ValueError on failure."""
        result = self.validate(brokers)
        if not result.valid:
            msgs = [f"  [{e.broker}] {e.key}: {e.message}" for e in result.errors]
            raise ValueError(
                f"Credential validation failed with {len(result.errors)} error(s):\n"
                + "\n".join(msgs)
            )
        return result

    def _validate_broker(self, broker: str, result: CredentialValidationResult) -> None:
        required = _BROKER_REQUIRED_VARS.get(broker, [])
        sensitive = _BROKER_SENSITIVE_VARS.get(broker, [])

        for key in required:
            value = self._env.get(key, "")
            if not value:
                result.add_error(broker, key, "Required credential is missing")

        for key in sensitive:
            value = self._env.get(key, "")
            if not value:
                result.add_warning(broker, key, "Sensitive credential is not set")

        if broker == "dhan":
            self._validate_dhan_specific(result)
        elif broker == "upstox":
            self._validate_upstox_specific(result)

    def _validate_dhan_specific(self, result: CredentialValidationResult) -> None:
        pin = self._env.get("DHAN_PIN", "")
        if pin and not pin.isdigit():
            result.add_error("dhan", "DHAN_PIN", "PIN must be numeric")

        totp = self._env.get("DHAN_TOTP_SECRET", "")
        if totp and len(totp) < 16:
            result.add_warning("dhan", "DHAN_TOTP_SECRET", "TOTP secret seems too short")

    def _validate_upstox_specific(self, result: CredentialValidationResult) -> None:
        redirect = self._env.get("UPSTOX_REDIRECT_URI", "")
        if redirect and not re.match(r"^https?://", redirect):
            result.add_error(
                "upstox", "UPSTOX_REDIRECT_URI", "Must be a valid HTTP(S) URL"
            )
