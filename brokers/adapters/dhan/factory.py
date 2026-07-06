"""Dhan broker factory — singleton gateway via GatewayRegistry."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from brokers.infrastructure.registry import GatewayRegistry

from brokers.adapters.dhan.gateway import DhanGateway

gateway_registry = GatewayRegistry()

logger = logging.getLogger(__name__)

BROKER_ID = "dhan"


class DhanBrokerFactory:
    """Create :class:`DhanGateway` instances with per-client singletons."""

    @classmethod
    def create(
        cls,
        *,
        access_token: str | None = None,
        client_id: str | None = None,
        pin: str | None = None,
        totp_secret: str | None = None,
        allow_live_orders: bool = False,
        env_path: str | Path | None = None,
        token_state_dir: str | Path | None = None,
        auto_refresh: bool = True,
        lifecycle: Any | None = None,
        event_bus: Any | None = None,
        risk_manager: Any | None = None,
        **kwargs: Any,
    ) -> DhanGateway:
        """Return a gateway instance, reusing one gateway per ``client_id``."""
        if kwargs:
            logger.warning("Unknown kwargs ignored: %s", list(kwargs.keys()))
        resolved_client_id = (client_id or access_token or "default")[:64]

        def _build() -> DhanGateway:
            return DhanGateway(
                access_token=access_token,
                client_id=client_id,
                pin=pin,
                totp_secret=totp_secret,
                allow_live_orders=allow_live_orders,
                env_path=Path(env_path) if env_path else None,
                token_state_dir=Path(token_state_dir) if token_state_dir else None,
                auto_refresh=auto_refresh,
                lifecycle=lifecycle,
                event_bus=event_bus,
                risk_manager=risk_manager,
            )

        return gateway_registry.get_or_create(BROKER_ID, resolved_client_id, _build)
