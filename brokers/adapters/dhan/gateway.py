"""Dhan gateway — composes all Dhan adapters into BrokerGateway.

Wires up the complete token lifecycle: auth, HTTP client with 401 auto-retry,
streaming with lazy token access, background refresh scheduler, token broadcast,
and optional persistence.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from brokers.adapters.dhan.alerts import DhanAlerts
from brokers.adapters.dhan.auth import DhanAuth
from brokers.adapters.dhan.capabilities import dhan_capabilities
from brokers.adapters.dhan.conditional_triggers import DhanConditionalTriggers
from brokers.adapters.dhan.depth20 import DhanDepth20Stream
from brokers.adapters.dhan.depth200 import DhanDepth200Stream
from brokers.adapters.dhan.edis import DhanEDIS
from brokers.adapters.dhan.exit_all import DhanExitAll
from brokers.adapters.dhan.extensions.forever_orders import DhanForeverOrders
from brokers.adapters.dhan.extensions.margin import DhanMargin
from brokers.adapters.dhan.extensions.super_orders import DhanSuperOrders
from brokers.adapters.dhan.futures import DhanFutures
from brokers.adapters.dhan.historical import DhanHistorical
from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.identity import DhanInstrumentRef, DhanInstrumentResolver
from brokers.adapters.dhan.instruments import DhanInstruments
from brokers.adapters.dhan.ip_management import DhanIpManagement
from brokers.adapters.dhan.ledger import DhanLedger
from brokers.adapters.dhan.market_data import DhanMarketData
from brokers.adapters.dhan.mtf import DhanMTF
from brokers.adapters.dhan.options import DhanOptions
from brokers.adapters.dhan.order_stream import DhanOrderStream
from brokers.adapters.dhan.orders import DhanOrders
from brokers.adapters.dhan.portfolio import DhanPortfolio
from brokers.adapters.dhan.reconciliation import DhanReconciliation
from brokers.adapters.dhan.streaming import DhanStreaming
from brokers.adapters.dhan.symbol_validator import DhanSymbolValidator
from brokers.adapters.dhan.token_broadcast import TokenBroadcast
from brokers.adapters.dhan.user_profile import DhanUserProfile
from brokers.domain import MarketDepth
from brokers.domain.capabilities import BrokerCapabilities
from brokers.infrastructure.event_bus import EventBus
from brokers.infrastructure.token_persistence import (
    JsonTokenStateStore,
    update_env_token,
)
from brokers.ports.risk_manager import RiskManagerPort
from brokers.ports.streaming import StreamingPort
from brokers.resilience.token_scheduler import TokenRefreshScheduler

logger = logging.getLogger(__name__)


class DhanGateway:
    """Dhan broker adapter implementing BrokerGateway protocol.

    Manages the complete token lifecycle:
    - Auth with TOTP generation and state tracking
    - HTTP client with 401 auto-retry via token refresh
    - Streaming with lazy token access (reconnects use latest token)
    - Background refresh scheduler with rate-limit backoff
    - Token broadcast to notify all consumers of refreshes
    - Optional persistence to JSON store and .env file

    Args:
        access_token: Pre-configured access token (skips TOTP if provided).
        client_id: Dhan client ID.
        pin: PIN for TOTP login.
        totp_secret: Secret for TOTP login.
        allow_live_orders: Enable live order placement (kill switch).
        env_path: Path to .env file for token persistence.
        token_state_dir: Directory for JSON token state persistence.
        auto_refresh: Enable background token refresh scheduler.
        refresh_interval_seconds: How often to check token validity.
        refresh_buffer_seconds: Refresh if token expires within this window.
        lifecycle: Optional lifecycle manager to register scheduler with.
    """

    _broker_id: str = "dhan"

    @property
    def broker_id(self) -> str:
        """Canonical broker identifier."""
        return self._broker_id

    def capabilities(self) -> BrokersCapabilities:
        """Return Dhan broker capability matrix."""
        return dhan_capabilities()

    def __init__(
        self,
        access_token: str | None = None,
        client_id: str | None = None,
        pin: str | None = None,
        totp_secret: str | None = None,
        allow_live_orders: bool = False,
        env_path: Path | None = None,
        token_state_dir: Path | None = None,
        auto_refresh: bool = True,
        refresh_interval_seconds: int = 60,
        refresh_buffer_seconds: float = 300.0,
        lifecycle: Any | None = None,
        event_bus: EventBus | None = None,
        risk_manager: RiskManagerPort | None = None,
    ):
        self._env_path = env_path
        self._token_state_dir = token_state_dir
        self._auto_refresh = auto_refresh

        # Create token store if directory provided
        token_store = None
        if token_state_dir:
            token_state_dir.mkdir(parents=True, exist_ok=True)
            token_store = JsonTokenStateStore(token_state_dir / "dhan-token-state.json")

        self._auth = DhanAuth(
            access_token=access_token,
            client_id=client_id,
            pin=pin,
            totp_secret=totp_secret,
            token_store=token_store,
        )

        self._refresh_lock = threading.Lock()
        self._broadcast = TokenBroadcast()

        token = self._auth.get_token()
        self._client = DhanHttpClient(
            client_id=client_id or "",
            access_token=token,
            token_refresh_fn=self._refresh_token_for_http,
            refresh_lock=self._refresh_lock,
        )

        self._resolver = DhanInstrumentResolver()
        self._orders = DhanOrders(
            self._client,
            self._resolver,
            allow_live_orders=allow_live_orders,
            event_bus=event_bus,
            risk_manager=risk_manager,
        )
        self._market_data = DhanMarketData(self._client, self._resolver)
        self._portfolio = DhanPortfolio(self._client)
        self._instruments = DhanInstruments(self._resolver)
        self._historical = DhanHistorical(self._client, self._resolver)
        self._super_orders = DhanSuperOrders(self._client, self._resolver)
        self._forever_orders = DhanForeverOrders(self._client, self._resolver)
        self._margin = DhanMargin(self._client, self._resolver)
        self._mtf = DhanMTF(self._client, self._resolver)
        self._options = DhanOptions(self._client, self._resolver)
        self._futures = DhanFutures(self._client, self._resolver)
        self._conditional_triggers = DhanConditionalTriggers(
            self._client, self._resolver
        )
        self._exit_all = DhanExitAll(self._client)
        self._edis = DhanEDIS(self._client, self._resolver)
        self._ledger = DhanLedger(self._client)
        self._alerts = DhanAlerts(self._client)
        self._ip_management = DhanIpManagement(self._client)
        self._user_profile = DhanUserProfile(self._client)
        self._reconciliation = DhanReconciliation(self._orders, self._portfolio)
        self._symbol_validator = DhanSymbolValidator(self._resolver)

        self._streaming = DhanStreaming(
            access_token=self._auth.get_token,
            client_id=client_id or "",
            resolver=self._resolver,
        )

        self._order_stream = DhanOrderStream(
            access_token=self._auth.get_token,
            client_id=client_id or "",
        )

        self._depth20_stream = DhanDepth20Stream(
            access_token=self._auth.get_token,
            client_id=client_id or "",
            resolver=self._resolver,
        )

        self._depth200_stream = DhanDepth200Stream(
            access_token=self._auth.get_token,
            client_id=client_id or "",
            resolver=self._resolver,
        )

        self._broadcast.register_receiver(self._client.update_token)
        self._broadcast.register_receiver(self._streaming.update_token)
        self._broadcast.register_receiver(self._order_stream.update_token)
        self._broadcast.register_receiver(self._depth20_stream.update_token)
        self._broadcast.register_receiver(self._depth200_stream.update_token)

        self._scheduler: TokenRefreshScheduler | None = None
        if auto_refresh and pin and totp_secret:
            self._scheduler = TokenRefreshScheduler(
                auth=self._auth,
                interval_seconds=refresh_interval_seconds,
                buffer_seconds=refresh_buffer_seconds,
                refresh_lock=self._refresh_lock,
                on_refresh=self._on_token_refreshed,
            )
            if lifecycle is not None:
                lifecycle.register(self._scheduler)
            else:
                self._scheduler.start()

        self._persist_initial_token()

    def _refresh_token_for_http(self) -> str | None:
        """Refresh token for HTTP 401 handler. Called under refresh_lock."""
        try:
            token = self._auth.generate_token()
            if token:
                self._persist_token(token)
            return token
        except Exception as exc:
            logger.warning("http_401_token_refresh_failed", extra={"error": str(exc)})
            return None

    def _on_token_refreshed(self, new_token: str) -> None:
        """Callback when token is refreshed by scheduler."""
        self._persist_token(new_token)
        self._broadcast.broadcast(new_token)
        logger.info("token_refresh_broadcast_complete")

    def _persist_initial_token(self) -> None:
        """Persist the initial token if persistence is configured."""
        token = self._auth.get_token()
        if token:
            self._persist_token(token)

    def _persist_token(self, token: str) -> None:
        """Persist token to JSON store and/or .env file."""
        if self._token_state_dir is not None:
            try:
                store = JsonTokenStateStore(
                    self._token_state_dir / "dhan-token-state.json"
                )
                state = self._auth.state
                if state is not None:
                    store.save(state)
            except Exception as exc:
                logger.warning("token_state_persist_failed", extra={"error": str(exc)})

        if self._env_path is not None:
            try:
                update_env_token(self._env_path, token)
            except Exception as exc:
                logger.warning("env_token_persist_failed", extra={"error": str(exc)})

    @property
    def resolver(self) -> DhanInstrumentResolver:
        return self._resolver

    def resolve_ref(
        self,
        symbol: str,
        exchange: str,
        *,
        expected_segment: str | None = None,
    ) -> DhanInstrumentRef:
        return self._resolver.resolve(
            symbol, exchange, expected_segment=expected_segment
        )

    def depth_20_snapshot(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_depth: Callable[[MarketDepth], Any] | None = None,
    ) -> MarketDepth:
        """Subscribe depth-20 feed and return merged REST/WS snapshot."""
        ref = self._resolver.resolve(symbol, exchange)
        sid = ref.security_id_int()
        feed = self._depth20_stream
        if on_depth is not None:
            feed.on_depth(on_depth)
        feed.subscribe(symbol, exchange)
        feed.register_symbol(sid, symbol)
        if not getattr(feed, "is_connected", getattr(feed, "_is_connected", False)):
            feed.start()
        cached = feed.latest_depth(sid)
        if cached is not None and cached.bids and cached.asks:
            return cached
        rest = self._market_data.depth(symbol, exchange)
        if cached is None:
            return rest
        bids = cached.bids if cached.bids else rest.bids
        asks = cached.asks if cached.asks else rest.asks
        return MarketDepth(
            symbol=symbol,
            bids=list(bids),
            asks=list(asks),
            timestamp=cached.timestamp or rest.timestamp,
        )

    def stream_market(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Callable[[dict], Any] | None = None,
    ) -> None:
        """Subscribe to live market feed in LTP, QUOTE, or FULL mode."""
        self._streaming.set_mode(mode)
        if on_tick is not None:
            self._streaming.register_tick_handler(symbol, exchange, on_tick)
        self._streaming.subscribe(symbol, exchange)
        if not self._streaming.is_connected:
            self._streaming.start()

    def unstream_market(self, symbol: str, exchange: str = "NSE") -> None:
        """Unsubscribe and stop the market feed for one symbol."""
        self._streaming.unsubscribe(symbol, exchange)
        self._streaming.stop()

    @property
    def orders(self) -> DhanOrders:
        return self._orders

    @property
    def super_orders(self) -> DhanSuperOrders:
        return self._super_orders

    @property
    def forever_orders(self) -> DhanForeverOrders:
        return self._forever_orders

    @property
    def margin(self) -> DhanMargin:
        return self._margin

    @property
    def mtf(self) -> DhanMTF:
        return self._mtf

    @property
    def options(self) -> DhanOptions:
        return self._options

    def get_option_expiries(self, underlying: str, exchange: str) -> list[str]:
        """Convenience: fetch available expiry dates for an options underlying."""
        return self._options.get_expiries(underlying, exchange)

    @property
    def futures(self) -> DhanFutures:
        return self._futures

    @property
    def order_stream(self) -> DhanOrderStream:
        return self._order_stream

    @property
    def conditional_triggers(self) -> DhanConditionalTriggers:
        return self._conditional_triggers

    @property
    def exit_all(self) -> DhanExitAll:
        return self._exit_all

    @property
    def edis(self) -> DhanEDIS:
        return self._edis

    @property
    def depth20_stream(self) -> DhanDepth20Stream:
        return self._depth20_stream

    @property
    def depth200_stream(self) -> DhanDepth200Stream:
        return self._depth200_stream

    @property
    def ledger(self) -> DhanLedger:
        return self._ledger

    @property
    def alerts(self) -> DhanAlerts:
        return self._alerts

    @property
    def ip_management(self) -> DhanIpManagement:
        return self._ip_management

    @property
    def user_profile(self) -> DhanUserProfile:
        return self._user_profile

    @property
    def reconciliation(self) -> DhanReconciliation:
        return self._reconciliation

    @property
    def symbol_validator(self) -> DhanSymbolValidator:
        return self._symbol_validator

    @property
    def market_data(self) -> DhanMarketData:
        return self._market_data

    @property
    def portfolio(self) -> DhanPortfolio:
        return self._portfolio

    @property
    def instruments(self) -> DhanInstruments:
        return self._instruments

    @property
    def auth(self) -> DhanAuth:
        return self._auth

    @property
    def historical(self) -> DhanHistorical:
        return self._historical

    @property
    def streaming(self) -> StreamingPort:
        return self._streaming

    @property
    def broadcast(self) -> TokenBroadcast:
        return self._broadcast

    @property
    def scheduler(self) -> TokenRefreshScheduler | None:
        return self._scheduler

    def health(self) -> dict:
        """Health status including token lifecycle metrics."""
        result: dict = {
            "auth_valid": self._auth.is_valid(),
            "scheduler": self._scheduler.health() if self._scheduler else None,
            "broadcast": self._broadcast.token_refresh_metrics,
            "connections": self.get_connection_status(),
            "circuit_breakers": self.get_circuit_breaker_states(),
        }
        return result

    def get_connection_status(self) -> dict[str, bool]:
        """Per-feed WebSocket connection status (ObservabilityProvider parity)."""
        return {
            "market_feed": self._streaming.is_connected,
            "order_stream": self._order_stream.is_connected,
            "depth_20": self._feed_connected(self._depth20_stream),
            "depth_200": self._feed_connected(self._depth200_stream),
            "has_active_subscriptions": bool(
                getattr(self._streaming, "_subscriptions", None)
                and len(self._streaming._subscriptions) > 0
            ),
        }

    @staticmethod
    def _feed_connected(feed: Any) -> bool:
        connected = getattr(feed, "is_connected", None)
        if callable(connected):
            return bool(connected())
        if connected is not None:
            return bool(connected)
        return bool(getattr(feed, "_is_connected", False))

    def get_connection_metadata(self) -> dict[str, Any]:
        """Non-bool diagnostic metadata for feeds."""
        metadata: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            if hasattr(self._streaming, "health"):
                health = self._streaming.health()
                metrics = getattr(health, "metrics", None) or {}
                metadata["market_feed_stale"] = bool(metrics.get("is_stale", False))
        return metadata

    def get_circuit_breaker_states(self) -> dict[str, int]:
        """Circuit breaker states: 0=CLOSED, 1=OPEN, 2=HALF_OPEN."""
        return self._client.circuit_breaker_states()

    def get_token_refresh_metrics(self) -> dict[str, int]:
        """Token refresh counters from broadcast + scheduler."""
        metrics = dict(self._broadcast.token_refresh_metrics)
        if self._scheduler is not None:
            sched = self._scheduler.health()
            if isinstance(sched, dict):
                metrics["scheduler_restarts"] = int(sched.get("restart_count", 0))
        return metrics

    def close(self) -> None:
        """Stop scheduler, streaming, and close HTTP client."""
        if self._scheduler is not None:
            self._scheduler.stop()

        pool = getattr(self, "_depth_200_pool", None)
        if pool is None:
            pool = getattr(self._depth200_stream, "_pool", None)
        if pool is not None:
            with contextlib.suppress(Exception):
                pool.close_all()

        for feed in (
            self._streaming,
            self._order_stream,
            self._depth20_stream,
            self._depth200_stream,
        ):
            self._stop_feed(feed)

        self._client.close()

    @staticmethod
    def _stop_feed(feed: Any) -> None:
        stop = getattr(feed, "stop", None)
        if stop is not None:
            with contextlib.suppress(Exception):
                stop()
        admission = getattr(feed, "_admission", None)
        if admission is not None:
            with contextlib.suppress(Exception):
                admission.release()
