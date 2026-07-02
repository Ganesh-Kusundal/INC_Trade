"""Central environment bootstrap for all process entry points."""

from __future__ import annotations

import logging
from pathlib import Path

from brokers.common.auth.credential_resolver import CANONICAL_ENV_FILES, CredentialResolver

logger = logging.getLogger(__name__)


def bootstrap_environment(
    project_root: Path | None = None,
    *,
    brokers: tuple[str, ...] = ("dhan", "upstox"),
) -> dict[str, Path | None]:
    """Load canonical broker env files into ``os.environ``.

    Returns a mapping of broker name to the path loaded (or ``None`` when
    missing or not configured). Safe to call multiple times (idempotent).
    """
    root = project_root or Path.cwd()
    loaded: dict[str, Path | None] = {}

    for broker in brokers:
        if broker == "paper":
            continue
        rel = CANONICAL_ENV_FILES.get(broker)
        if rel is None:
            loaded[broker] = None
            continue
        path = root / rel
        if path.exists() and path.stat().st_size > 0:
            CredentialResolver.load_broker_env(broker, path)
            loaded[broker] = path
            logger.debug("bootstrap_environment: loaded %s from %s", broker, path)
        else:
            loaded[broker] = None

    return loaded
