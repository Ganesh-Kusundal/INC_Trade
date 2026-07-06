"""Upstox gateway builder — delegates to shared composition module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from brokers.adapters.upstox.auth.config import UpstoxConnectionSettings
from brokers.adapters.upstox.composition import (
    apply_components_to_gateway,
    build_upstox_components,
    resolve_upstox_settings,
)

if TYPE_CHECKING:
    from brokers.adapters.upstox.gateway import UpstoxGateway


class UpstoxGatewayBuilder:
    """Builder that wires Upstox subcomponents onto a gateway instance."""

    def __init__(self, gateway: UpstoxGateway) -> None:
        self.gateway = gateway

    def _resolve_settings(
        self,
        access_token: str | None,
        settings: UpstoxConnectionSettings | None,
        allow_live_orders: bool | None,
    ) -> UpstoxConnectionSettings:
        return resolve_upstox_settings(access_token, settings, allow_live_orders)

    def build(
        self,
        access_token: str | None = None,
        settings: UpstoxConnectionSettings | None = None,
        allow_live_orders: bool | None = None,
        auto_refresh: bool = True,
        lifecycle: Any | None = None,
        load_instruments: bool = False,
    ) -> None:
        components = build_upstox_components(
            access_token=access_token,
            settings=settings,
            allow_live_orders=allow_live_orders,
            auto_refresh=auto_refresh,
            lifecycle=lifecycle,
            load_instruments=load_instruments,
        )
        self.gateway._components = components
        apply_components_to_gateway(self.gateway, components)
