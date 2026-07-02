"""CommonBrokerGateway — the universal broker port.

This Protocol defines ONLY operations that are semantically meaningful across
every broker the platform supports.  Broker-specific features are exposed
through typed extension interfaces in ``brokers.common.extensions``.

Design invariants enforced here:
- No broker DTOs, raw payloads, or provider-native errors cross this boundary.
- All return types are normalized domain models from ``domain/``.
- ``quota`` tokens are required on every mutating or quota-consuming call so the
  ``QuotaScheduler`` remains the sole gatekeeper of API budget.
- Stream lifecycle is owned by ``StreamOrchestrator``; the gateway only opens a
  raw transport handle.

Relationship to MarketDataGateway
----------------------------------
There are TWO gateway abstractions in this codebase. This is intentional:

- **CommonBrokerGateway** (this Protocol): Used by the OMS, execution layer,
  and trading orchestrator. Includes trading, portfolio, and quota operations.
  Defined as a ``Protocol`` for structural typing (duck typing).

- **MarketDataGateway** (``brokers.common.gateway``): Used by the data layer,
  analytics, and CLI. Includes market data, batch operations, and instrument
  queries. Defined as an ``ABC`` for nominal typing.

New code should prefer **CommonBrokerGateway** for trading operations and
**MarketDataGateway** for read-only data access. The two interfaces will be
merged in a future release (tracked as P2-1 technical debt).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from brokers.common.capabilities import CapabilityDescriptor
from domain.entities import Balance, Order, OrderResponse, Position, Quote, Trade
from domain.entities.market import MarketDepth
from domain.historical import HistoricalBar, InstrumentRef
from domain.requests import ModifyOrderRequest, OrderRequest

# ---------------------------------------------------------------------------
# Supporting transport types (lifecycle owned by StreamOrchestrator)
# ---------------------------------------------------------------------------


@runtime_checkable
class BrokerStreamHandle(Protocol):
    """Minimal handle returned by open_market_stream / open_order_stream.

    The stream orchestrator holds this handle and uses it to manage connection
    lifecycle.  Consumers never interact with handles directly.
    """

    @property
    def session_id(self) -> str: ...
    @property
    def broker_id(self) -> str: ...
    async def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...


class BrokerStreamPlan:
    """Input to open_*_stream describing what to subscribe to.

    instruments — set of InstrumentRef strings to subscribe.
    modes       — set of broker-specific stream mode names (e.g. ``{"LTP"}``).
    on_raw_frame — callback invoked by the broker transport for each raw message.
                   The StreamOrchestrator wires its own handler here; callers
                   never set this directly.
    """

    __slots__ = ("instruments", "modes", "on_raw_frame")

    def __init__(
        self,
        instruments: frozenset[str],
        modes: frozenset[str],
        on_raw_frame: object = None,
    ) -> None:
        self.instruments = instruments
        self.modes = modes
        self.on_raw_frame = on_raw_frame


class HistoricalBarRequest:
    """Input to CommonBrokerGateway.get_historical_bars — a single-broker request.

    The HistoricalDataCoordinator creates these from a larger federated query
    after range clipping and chunking.
    """

    __slots__ = (
        "from_date",
        "instrument",
        "request_id",
        "timeframe",
        "to_date",
    )

    def __init__(
        self,
        instrument: InstrumentRef,
        timeframe: str,
        from_date: str,
        to_date: str,
        request_id: str,
    ) -> None:
        self.instrument = instrument
        self.timeframe = timeframe
        self.from_date = from_date
        self.to_date = to_date
        self.request_id = request_id


class BrokerHealthSnapshot:
    """Point-in-time health view of a single broker gateway.

    alive         — whether the gateway can currently serve requests.
    auth_valid    — whether the current access token is valid.
    error_rate    — recent error rate (0.0-1.0) as observed by health monitor.
    latency_p50   — median API latency in milliseconds.
    reason        — human-readable reason if not alive.
    """

    __slots__ = ("alive", "auth_valid", "broker_id", "error_rate", "latency_p50", "reason")

    def __init__(
        self,
        broker_id: str,
        alive: bool,
        auth_valid: bool = True,
        error_rate: float = 0.0,
        latency_p50: float = 0.0,
        reason: str = "",
    ) -> None:
        self.broker_id = broker_id
        self.alive = alive
        self.auth_valid = auth_valid
        self.error_rate = error_rate
        self.latency_p50 = latency_p50
        self.reason = reason


# ---------------------------------------------------------------------------
# QuotaToken — opaque token issued by QuotaScheduler
# ---------------------------------------------------------------------------


class QuotaToken:
    """Opaque token issued by ``QuotaScheduler.acquire()``.

    Passed into gateway methods to prove the call has been budgeted.
    The scheduler validates tokens at release time for accounting.
    """

    __slots__ = ("_token_id", "broker_id", "endpoint_class", "priority_class")

    def __init__(
        self,
        broker_id: str,
        endpoint_class: str,
        priority_class: str,
        token_id: str,
    ) -> None:
        self.broker_id = broker_id
        self.endpoint_class = endpoint_class
        self.priority_class = priority_class
        self._token_id = token_id

    def __repr__(self) -> str:
        return (
            f"QuotaToken({self.broker_id!r}, {self.endpoint_class!r}, "
            f"{self.priority_class!r}, id={self._token_id!r})"
        )


# ---------------------------------------------------------------------------
# CommonBrokerGateway Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class CommonBrokerGateway(Protocol):
    """Universal broker port — all broker adapters must satisfy this protocol.

    Method groups
    -------------
    - Identity / capability discovery
    - Order execution (normalized)
    - Portfolio reads (normalized)
    - Point-in-time market reads (not streaming)
    - Historical data (single-broker; federation uses HistoricalDataCoordinator)
    - Stream handle factories (lifecycle owned by StreamOrchestrator)
    - Lifecycle

    What does NOT belong here
    -------------------------
    - super_order, forever_order → SuperOrderProvider, ForeverOrderProvider
    - news, fundamentals          → NewsProvider, FundamentalsProvider
    - market intelligence         → MarketIntelligenceProvider
    - depth-20/200 WS             → DeepDepthProvider
    - expired options history     → ExpiredOptionsHistoryProvider
    - broker wire DTOs            → never cross this boundary
    - broker-native errors        → mapped to domain errors at the adapter
    """

    @property
    def broker_id(self) -> str:
        """Canonical broker identifier, e.g. ``"dhan"`` or ``"upstox"``."""
        ...

    # ------------------------------------------------------------------
    # Capability discovery
    # ------------------------------------------------------------------

    def list_capabilities(self) -> CapabilityDescriptor:
        """Return the broker's capability descriptor (capabilities + extensions).

        Callers should cache the result for the session TTL rather than calling
        on every request.
        """
        ...

    def supports(self, feature: str) -> bool:
        """Shorthand for ``list_capabilities().capabilities.supports(feature)``."""
        ...

    # ------------------------------------------------------------------
    # Order execution — all return normalized domain models
    # ------------------------------------------------------------------

    async def place_order(
        self,
        request: OrderRequest,
        *,
        quota: QuotaToken,
    ) -> OrderResponse:
        """Place an order and return a normalized ``OrderResponse``.

        Raises
        ------
        QuotaExhaustedError   — if the quota token is invalid.
        BrokerUnavailableError — if the broker is unreachable.
        """
        ...

    async def cancel_order(
        self,
        order_id: str,
        *,
        quota: QuotaToken,
    ) -> OrderResponse:
        """Cancel an order. Returns a structured failure response — never raises for
        already-cancelled or non-existent orders; raises only for infrastructure failures.
        """
        ...

    async def modify_order(
        self,
        request: ModifyOrderRequest,
        *,
        quota: QuotaToken,
    ) -> OrderResponse:
        """Modify an open order.

        Raises ``UnsupportedExtensionError`` if the broker does not support order
        modification (check ``supports("modify_order")`` first).
        """
        ...

    # ------------------------------------------------------------------
    # Portfolio reads
    # ------------------------------------------------------------------

    async def get_positions(self, *, quota: QuotaToken) -> list[Position]:
        """Return current open positions, normalized."""
        ...

    async def get_margins(self, *, quota: QuotaToken) -> Balance:
        """Return fund limits and margin usage, normalized."""
        ...

    async def get_orders(self, *, quota: QuotaToken) -> list[Order]:
        """Return current order book, normalized."""
        ...

    async def get_trades(self, *, quota: QuotaToken) -> list[Trade]:
        """Return trade book for the session, normalized."""
        ...

    # ------------------------------------------------------------------
    # Point-in-time market reads
    # ------------------------------------------------------------------

    async def get_quote_snapshot(
        self,
        instrument: InstrumentRef,
        *,
        quota: QuotaToken,
    ) -> Quote:
        """Return a point-in-time quote, normalized."""
        ...

    async def get_depth_snapshot(
        self,
        instrument: InstrumentRef,
        *,
        quota: QuotaToken,
    ) -> MarketDepth:
        """Return a point-in-time market depth, normalized.

        The ``depth_type`` field on the returned ``MarketDepth`` preserves how
        many levels are available (``DEPTH_5``, ``DEPTH_20``, ``DEPTH_200``).
        Use ``DeepDepthProvider`` for streaming 20/200-level books.
        """
        ...

    # ------------------------------------------------------------------
    # Historical data (single-broker slice)
    # ------------------------------------------------------------------

    async def get_historical_bars(
        self,
        request: HistoricalBarRequest,
        *,
        quota: QuotaToken,
    ) -> Sequence[HistoricalBar]:
        """Fetch historical bars for a single broker slice.

        Called by ``HistoricalDataCoordinator`` after it has planned, chunked,
        and range-clipped the request.  Should not be called directly by
        application code — use the coordinator for federation, provenance, and
        merge logic.
        """
        ...

    # ------------------------------------------------------------------
    # Stream handle factories (lifecycle owned by StreamOrchestrator)
    # ------------------------------------------------------------------

    async def open_market_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        """Open a raw market-data WebSocket transport handle.

        The ``StreamOrchestrator`` calls this; application code should subscribe
        through the orchestrator, not directly.
        """
        ...

    async def open_order_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle:
        """Open a raw order/portfolio update WebSocket transport handle."""
        ...

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def health(self) -> BrokerHealthSnapshot:
        """Return a current health snapshot (auth, latency, error rate)."""
        ...

    async def close(self) -> None:
        """Gracefully close all connections and release resources."""
        ...
