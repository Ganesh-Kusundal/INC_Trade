"""Process-wide registry ensuring one gateway/connection per broker account."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class AccountConnectionRegistry:
    """Ensures exactly one live gateway per ``(broker_id, account_id)`` pair."""

    _lock = threading.Lock()
    _gateways: dict[tuple[str, str], Any] = {}

    @classmethod
    def get_or_create(
        cls,
        broker_id: str,
        account_id: str,
        factory_fn: Callable[[], Any],
    ) -> Any:
        """Return existing gateway or create via *factory_fn*."""
        key = (broker_id.lower(), account_id)
        with cls._lock:
            existing = cls._gateways.get(key)
            if existing is not None:
                logger.debug(
                    "account_registry.reuse",
                    extra={"broker_id": broker_id, "account_id": account_id},
                )
                return existing
            gateway = factory_fn()
            cls._gateways[key] = gateway
            logger.info(
                "account_registry.created",
                extra={"broker_id": broker_id, "account_id": account_id},
            )
            return gateway

    @classmethod
    def get(cls, broker_id: str, account_id: str) -> Any | None:
        with cls._lock:
            return cls._gateways.get((broker_id.lower(), account_id))

    @classmethod
    def release(cls, broker_id: str, account_id: str) -> None:
        with cls._lock:
            key = (broker_id.lower(), account_id)
            gateway = cls._gateways.pop(key, None)
        if gateway is not None:
            close = getattr(gateway, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    logger.debug("account_registry.close_failed: %s", exc)

    @classmethod
    def release_all(cls) -> None:
        with cls._lock:
            keys = list(cls._gateways.keys())
        for broker_id, account_id in keys:
            cls.release(broker_id, account_id)

    @classmethod
    def active_count(cls) -> int:
        with cls._lock:
            return len(cls._gateways)
