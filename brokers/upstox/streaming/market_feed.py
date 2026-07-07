"""Upstox V3 market data WebSocket feed — subclass :class:`BaseMarketFeed`.

Connects to Upstox's V3 protobuf market data WebSocket and streams
real-time feed frames.

Tracking: ``UpstoxV3SubscriptionManager`` enforces tier-based subscription
limits. ``change_mode`` overrides the base suspend/resume because V3
treats mode as a connection-wide property.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

import websockets

from brokers.common.streaming.base_market_feed import BaseMarketFeed
from brokers.infrastructure.logging import get_logger
from brokers.infrastructure.streaming.stream_health import (
    MarketTickEvent,
)
from brokers.infrastructure.streaming.subscription import (
    InstrumentKey,
    StreamMode,
    SubscriptionPlan,
)

from .authorizer import UpstoxFeedAuthorizer
from .decoder import decode_market_message
from .payloads import (
    build_subscribe_payload,
    encode_payload,
)
from .subscription_manager import UpstoxV3SubscriptionManager, PlanTier

logger = get_logger(__name__)


# Map StreamMode to Upstox V3 protocol mode strings
_MODE_MAP: dict[StreamMode, str] = {
    StreamMode.LTP: "ltpc",
    StreamMode.QUOTE: "full",
    StreamMode.FULL: "full",
    StreamMode.DEPTH: "full_d30",
}


class UpstoxMarketFeed(BaseMarketFeed):
    """Async Upstox V3 market data feed — subclass :class:`BaseMarketFeed`."""

    BROKER_ID: ClassVar[str] = "upstox"
    MAX_INSTRUMENTS: ClassVar[int] = 5000  # V3 STANDARD tier cap

    def __init__(
        self,
        *,
        http_client: Any,
        tier: PlanTier = PlanTier.STANDARD,
        on_tick: Callable[[MarketTickEvent], None] | None = None,
        on_health_change: Callable | None = None,
    ) -> None:
        super().__init__(on_tick=on_tick, on_health_change=on_health_change)
        self._http_client = http_client
        self._authorizer = UpstoxFeedAuthorizer(http_client=http_client)
        self._subscription_mgr = UpstoxV3SubscriptionManager(tier=tier)

    @property
    def subscription_manager(self) -> UpstoxV3SubscriptionManager:
        return self._subscription_mgr

    async def _resolve_url_and_headers(self) -> tuple[str, dict[str, str] | None]:
        ws_url = await self._authorizer.authorize_market_data_v3()
        return (ws_url, None)

    async def _connect_ws(self, url: str, extra_headers: dict[str, str] | None = None) -> Any:
        ws = await websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        )
        logger.info("upstox_ws_connected")
        return ws

    def _track_subscribe(
        self, instrument_key: InstrumentKey, mode: StreamMode
    ) -> None:
        upstox_mode = _MODE_MAP.get(mode, "full")
        self._subscription_mgr.subscribe(
            [instrument_key.security_id], mode=upstox_mode
        )

        if len(self._subscription_mgr.active_instruments) > self.MAX_INSTRUMENTS:
            # Roll back the subscription we just added.
            self._subscription_mgr.unsubscribe([instrument_key.security_id])
            raise ValueError(
                f"Max {self.MAX_INSTRUMENTS} instruments per connection"
            )

    def _track_unsubscribe(self, instrument_key: InstrumentKey) -> None:
        self._subscription_mgr.unsubscribe([instrument_key.security_id])

    def _build_plan(self) -> SubscriptionPlan:
        instruments: set[InstrumentKey] = set()
        for inst_key in self._subscription_mgr.active_instruments:
            parts = inst_key.split("|", 1)
            symbol = parts[-1] if len(parts) > 1 else inst_key
            exchange = parts[0].split("_")[0] if "_" in parts[0] else "NSE"
            instruments.add(
                InstrumentKey(
                    symbol=symbol,
                    exchange=exchange,
                    security_id=inst_key,
                )
            )
        return SubscriptionPlan(instruments=frozenset(instruments), mode=self._mode)

    async def _send_subscription(
        self, transport: Any, plan: SubscriptionPlan
    ) -> None:
        if not plan.instruments:
            return
        upstox_mode = _MODE_MAP.get(plan.mode, "full")
        instruments = [key.security_id for key in plan.instruments]

        payload = build_subscribe_payload(instruments, mode=upstox_mode)
        encoded = encode_payload(payload)
        await transport.send(encoded)

        logger.info(
            "upstox_ws_subscribed",
            count=len(instruments),
            mode=upstox_mode,
        )

    def _decode_message(  # type: ignore[override]
        self, raw: str | bytes
    ) -> list[MarketTickEvent]:
        return decode_market_message(raw)

    async def _release_subscriptions(self) -> None:
        """Override release hook to clear the subscription manager state."""
        self._subscription_mgr.clear()

    async def change_mode(
        self,
        instrument_key: InstrumentKey,
        mode: StreamMode,
    ) -> None:
        """Change the data mode for a subscribed instrument.

        Note: Upstox V3 WS uses a single mode for the whole connection.
        Changing mode for one instrument effectively changes it for all.
        """
        if self._orchestrator is None:
            return

        upstox_mode = _MODE_MAP.get(mode, "full")
        security_id = instrument_key.security_id
        if security_id in self._subscription_mgr.active_instruments:
            self._subscription_mgr.unsubscribe([security_id])
            self._subscription_mgr.subscribe([security_id], mode=upstox_mode)

        self._mode = mode
        plan = self._build_plan()
        await self._orchestrator.update_plan(plan)


__all__ = ["UpstoxMarketFeed"]
