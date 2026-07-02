"""Focused gateway interfaces (REF-18 ISP split, REF-028 aligned with MarketDataGateway).

These narrow interfaces decompose the monolithic ``MarketDataGateway``
by concern. Signatures are aligned with the concrete gateway implementations
so that ``MarketDataGateway`` can inherit from all of them.

The file is organised into two sections:

1. **Core gateway interfaces** (top) — decomposed from ``MarketDataGateway``:
   ``MarketDataProvider``, ``DerivativesProvider``, ``BatchMarketDataProvider``,
   ``TradingExecutor``, ``PortfolioReader``, ``InstrumentProvider``,
   ``StreamProvider``, ``LifecycleAware``.

2. **Broker SPI ports** (bottom) — fine-grained capability contracts that
   individual broker adapters implement. Previously in ``brokers.common.api.ports``
   (merged: 2026-06-23, ``ports.py`` deleted).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Generic, TypeVar

import pandas as pd

from domain import (
    Balance,
    ConditionalAlert,
    ConditionalAlertRequest,
    FundLimits,
    FutureChain,
    Holding,
    MarketDepth,
    OptionChain,
    OptionContract,
    Order,
    OrderPreview,
    OrderRequest,
    OrderResponse,
    Position,
    Quote,
    SliceOrderRequest,
    Trade,
)
from domain.constants import DEFAULT_DERIVATIVES_EXCHANGE, DEFAULT_EXCHANGE, DEFAULT_LOOKBACK_DAYS

# ======================================================================
# Section 1 — Core Gateway Interfaces (decomposed MarketDataGateway)
# ======================================================================


class MarketDataProvider(ABC):
    """Narrow interface for OHLCV, quote, LTP, and depth."""

    @abstractmethod
    def history(
        self,
        symbol: str | list[str],
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = "1D",
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame: ...

    @abstractmethod
    def quote(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Quote: ...

    @abstractmethod
    def ltp(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Decimal: ...

    @abstractmethod
    def depth(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> MarketDepth: ...


class DerivativesProvider(ABC):
    """Narrow interface for option and futures chain data."""

    @abstractmethod
    def option_chain(
        self, underlying: str, exchange: str = DEFAULT_DERIVATIVES_EXCHANGE, expiry: str | None = None
    ) -> OptionChain: ...

    @abstractmethod
    def future_chain(self, underlying: str, exchange: str = DEFAULT_DERIVATIVES_EXCHANGE) -> FutureChain: ...


class BatchMarketDataProvider(ABC):
    """Narrow interface for batched LTP, quote, and history."""

    @abstractmethod
    def ltp_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Decimal]: ...

    @abstractmethod
    def quote_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Quote]: ...

    @abstractmethod
    def history_batch(
        self,
        symbols: list[str],
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = "1D",
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> pd.DataFrame: ...


class TradingExecutor(ABC):
    """Narrow interface for order placement, cancellation, and trade/order book.

    The ``place_order`` signature matches the concrete gateway implementations.
    For typed order requests, use :class:`~domain.requests.OrderRequest`
    as an alternative construction pattern.
    """

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        side: str = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> OrderResponse: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse: ...

    @abstractmethod
    def get_orderbook(self) -> list[Order]: ...

    @abstractmethod
    def get_trade_book(self) -> list[Trade]: ...


class PortfolioReader(ABC):
    """Narrow interface for positions, holdings, funds, and trades."""

    @abstractmethod
    def positions(self) -> list[Position]: ...

    @abstractmethod
    def holdings(self) -> list[Holding]: ...

    @abstractmethod
    def funds(self) -> Balance: ...

    @abstractmethod
    def trades(self) -> list[Trade]: ...


class InstrumentProvider(ABC):
    """Narrow interface for instrument search and loading."""

    @abstractmethod
    def search(self, query: str) -> list[dict]: ...

    @abstractmethod
    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None: ...


class StreamProvider(ABC):
    """Narrow interface for real-time streaming."""

    @abstractmethod
    def stream(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any: ...

    @abstractmethod
    def stream_depth(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        depth_type: str = "DEPTH_5",
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Any: ...

    @abstractmethod
    def stream_order(self, on_order: Any | None = None) -> Any: ...


class LifecycleAware(ABC):
    """Narrow interface for broker lifecycle (describe, capabilities, close)."""

    @abstractmethod
    def describe(self) -> dict[str, Any]: ...

    @abstractmethod
    def capabilities(self) -> Any: ...

    @abstractmethod
    def close(self) -> None: ...


# ======================================================================
# Section 2 — Broker SPI Ports (migrated from brokers.common.api.ports)
# ======================================================================


class OrderCommand(ABC):
    """Execute and manage orders. Gateway methods: place_order, cancel_order."""

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place a new order."""
        ...

    @abstractmethod
    def modify_order(self, order_id: str, **changes: Any) -> dict[str, Any]:
        """Modify an existing open order."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by ID."""
        ...

    @abstractmethod
    def preview_order(self, request: OrderRequest) -> OrderPreview:
        """Validate an order without submitting it."""
        ...


class OrderQuery(ABC):
    """Query orders and trades. Gateway methods: get_orderbook, get_trade_book, trades."""

    @abstractmethod
    def get_order(self, order_id: str) -> Order | None:
        """Fetch a single order by broker-assigned ID."""
        ...

    @abstractmethod
    def get_order_by_correlation_id(self, correlation_id: str) -> Order | None:
        """Fetch a single order by caller-supplied correlation ID."""
        ...

    @abstractmethod
    def get_order_list(self) -> list[Order]:
        """Fetch all orders for the day."""
        ...

    @abstractmethod
    def get_trades(self) -> list[Trade]:
        """Fetch the trade book."""
        ...

    @abstractmethod
    def get_trades_for_order(self, order_id: str) -> list[Trade]:
        """Fetch executed trades for a given order."""
        ...


class SliceOrderCommand(ABC):
    """Slice large orders into child orders. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def place_slice_order(self, request: SliceOrderRequest) -> list[Order]:
        """Split an order request into executable child orders."""
        ...


class CoverOrderProvider(ABC):
    """Cover order capability. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def place_cover_order(self, request: OrderRequest, stop_loss_price: Decimal) -> Order:
        """Place a cover order."""
        ...

    @abstractmethod
    def exit_cover_order(self, order_id: str) -> Order:
        """Exit a cover order."""
        ...


class GttOrderProvider(ABC):
    """Good-till-triggered order capability. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def place_forever_order(
        self,
        request: OrderRequest,
        order_flag: str,
        quantity2: int | None = None,
        price2: Decimal | None = None,
        trigger_price2: Decimal | None = None,
    ) -> Order:
        """Place a GTT/forever order."""
        ...

    @abstractmethod
    def modify_forever_order(
        self,
        order_id: str,
        order_flag: str,
        leg_name: str,
        quantity: int,
        price: Decimal,
        trigger_price: Decimal,
    ) -> Order:
        """Modify a GTT/forever order."""
        ...

    @abstractmethod
    def cancel_forever_order(self, order_id: str) -> bool:
        """Cancel a GTT/forever order."""
        ...

    @abstractmethod
    def get_forever_orders(self) -> list[Order]:
        """Return GTT/forever orders."""
        ...


class ConditionalAlertProvider(ABC):
    """Conditional alert capability. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def place_alert(self, request: ConditionalAlertRequest) -> str:
        """Place a conditional alert and return its ID."""
        ...

    @abstractmethod
    def get_alert(self, alert_id: str) -> ConditionalAlert:
        """Fetch a conditional alert."""
        ...

    @abstractmethod
    def list_alerts(self) -> list[ConditionalAlert]:
        """List conditional alerts."""
        ...

    @abstractmethod
    def delete_alert(self, alert_id: str) -> bool:
        """Delete a conditional alert."""
        ...


class NewsProvider(ABC):
    """News feed provider. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def get_news(self, **filters: Any) -> list[Any]:
        """Return news items matching optional filters."""
        ...


T = TypeVar("T")


class IdempotencyCachePort(ABC, Generic[T]):
    """Idempotency cache for order placement safety. Infrastructure port; not exposed via gateway."""

    @abstractmethod
    def get(self, key: str) -> T | None:
        """Return a cached response for an idempotency key."""
        ...

    @abstractmethod
    def put(self, key: str, value: T) -> None:
        """Store a response for an idempotency key."""
        ...


class MarketIntelligencePort(ABC):
    """Aggregated market intelligence — PCR, Max Pain, OI, FII/DII, Smartlist."""

    @abstractmethod
    def get_pcr(
        self,
        instrument_key: str,
        expiry: str,
        date: str,
        bucket_interval: int = 1,
    ) -> dict[str, Any]:
        """Return Put/Call ratio data."""
        ...

    @abstractmethod
    def get_max_pain(
        self,
        instrument_key: str,
        expiry: str,
        date: str,
        bucket_interval: int = 1,
    ) -> dict[str, Any]:
        """Return max-pain analysis."""
        ...

    @abstractmethod
    def get_oi(self, instrument_key: str, expiry: str, date: str) -> dict[str, Any]:
        """Return open-interest build-up."""
        ...

    @abstractmethod
    def get_fii_flow(
        self, data_type: str = "NSE_FO|INDEX_FUTURES", interval: str = "1D"
    ) -> dict[str, Any]:
        """Return FII/DII flow."""
        ...

    @abstractmethod
    def get_dii_flow(self, interval: str = "1D") -> dict[str, Any]:
        """Return DII flow."""
        ...

    @abstractmethod
    def get_smartlist(
        self,
        kind: str,
        asset_type: str = "INDEX",
        category: str = "TOP_TRADED",
    ) -> dict[str, Any]:
        """Return the broker's curated symbol list."""
        ...


class KillSwitchPort(ABC):
    """User-level kill switch."""

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Return current kill-switch state."""
        ...

    @abstractmethod
    def set_status(self, updates: list[dict[str, str]]) -> dict[str, Any]:
        """Toggle kill switches per segment."""
        ...


class StaticIPPort(ABC):
    """Static IP configuration."""

    @abstractmethod
    def get_static_ip(self) -> dict[str, str]:
        """Return the currently registered static IP(s)."""
        ...

    @abstractmethod
    def set_static_ip(self, primary: str, secondary: str | None = None) -> dict[str, str]:
        """Register a new primary (and optional secondary) static IP."""
        ...


class PortfolioProvider(ABC):
    """Portfolio data. Gateway methods: positions, holdings, funds."""

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Return current positions for the day."""
        ...

    @abstractmethod
    def get_holdings(self) -> list[Holding]:
        """Return securities held in the demat account."""
        ...

    @abstractmethod
    def get_fund_limits(self) -> FundLimits:
        """Return account fund limits."""
        ...

    @abstractmethod
    def get_profile(self) -> dict[str, Any]:
        """Return the account profile."""
        ...

    @abstractmethod
    def get_ledger(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        """Return ledger entries between two dates."""
        ...


class OptionsProvider(ABC):
    """Option-chain aware provider. Gateway method: option_chain."""

    @abstractmethod
    def get_expiries(self, underlying: str, exchange_segment: Any) -> list[str]:
        """Return available option expiries."""
        ...

    @abstractmethod
    def get_option_chain(
        self,
        underlying: str,
        exchange_segment: Any,
        expiry: str,
    ) -> list[OptionContract]:
        """Return parsed option contracts."""
        ...


class MarginProvider(ABC):
    """Margin calculations. No direct gateway method; used internally by broker adapters."""

    @abstractmethod
    def calculate_margin(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a margin-calculator request."""
        ...


class MarketStatusProvider(ABC):
    """Market/session status provider. No direct gateway method; extends beyond the base gateway contract."""

    @abstractmethod
    def get_market_status(self) -> dict[str, Any]:
        """Return market/session status."""
        ...


class FuturesProvider(ABC):
    """Futures instrument capability. Gateway method: future_chain."""

    @abstractmethod
    def get_contracts(self, underlying: str, exchange_segment: Any) -> list[Any]:
        """Return futures contracts for an underlying symbol."""
        ...

    @abstractmethod
    def get_nearest_contract(self, underlying: str, exchange_segment: Any) -> Any:
        """Return the nearest active futures contract."""
        ...

    @abstractmethod
    def get_expiries(self, underlying: str, exchange_segment: Any) -> list[Any]:
        """Return futures contract expiries."""
        ...

    @abstractmethod
    def is_commodity(self, underlying: str) -> bool:
        """Return whether the underlying is a commodity."""
        ...


__all__ = [
    # Core gateway interfaces
    "BatchMarketDataProvider",
    # Broker SPI ports (migrated from api.ports)
    "ConditionalAlertProvider",
    "CoverOrderProvider",
    "DerivativesProvider",
    "FuturesProvider",
    "GttOrderProvider",
    "IdempotencyCachePort",
    "InstrumentProvider",
    "KillSwitchPort",
    "LifecycleAware",
    "MarginProvider",
    "MarketDataProvider",
    "MarketIntelligencePort",
    "MarketStatusProvider",
    "NewsProvider",
    "OptionsProvider",
    "OrderCommand",
    "OrderQuery",
    "PortfolioProvider",
    "PortfolioReader",
    "SliceOrderCommand",
    "StaticIPPort",
    "StreamProvider",
    "TradingExecutor",
]
