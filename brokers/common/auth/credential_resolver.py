"""Canonical credential path resolution for broker bootstrap.

Single source of truth for which env files each broker loads.  Callers
should use :class:`CredentialResolver` instead of hard-coding paths.
"""

from __future__ import annotations

from pathlib import Path

from brokers.common.env_loader import load_env_file

CANONICAL_ENV_FILES: dict[str, str | None] = {
    "dhan": ".env.local",
    "upstox": ".env.upstox",
    "paper": None,
}

# Upstox: dedicated file first, then unified .env.local (same pattern as Dhan TOTP).
UPSTOX_ENV_CANDIDATES: tuple[str, ...] = (".env.upstox", ".env.local")


class CredentialResolver:
    """Resolve and load broker credential files."""

    @staticmethod
    def resolve_upstox_env_path() -> Path | None:
        """First non-empty Upstox env file (.env.upstox, then .env.local)."""
        for name in UPSTOX_ENV_CANDIDATES:
            path = Path(name)
            if path.exists() and path.stat().st_size > 0:
                return path
        return Path(CANONICAL_ENV_FILES["upstox"])

    @staticmethod
    def resolve_env_path(
        broker: str,
        env_path: str | Path | None = None,
    ) -> Path | None:
        """Return the env file path for *broker* (may not exist)."""
        if env_path is not None:
            return Path(env_path)
        key = broker.lower().strip()
        if key == "upstox":
            return CredentialResolver.resolve_upstox_env_path()
        default = CANONICAL_ENV_FILES.get(key)
        if default is not None:
            return Path(default)
        return None

    @staticmethod
    def load_broker_env(
        broker: str,
        env_path: str | Path | None = None,
    ) -> Path | None:
        """Load the broker env file into ``os.environ``.

        Returns the path that was loaded, or ``None`` when the broker
        has no env file (e.g. paper) or the file does not exist.
        """
        path = CredentialResolver.resolve_env_path(broker, env_path)
        if path is None or not path.exists():
            return None
        load_env_file(path)
        return path

    @staticmethod
    def env_file_exists(broker: str, env_path: str | Path | None = None) -> bool:
        path = CredentialResolver.resolve_env_path(broker, env_path)
        return path is not None and path.exists()
