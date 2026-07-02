"""Paper trading gateway — simulated broker for testing and development."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

import pandas as pd

from brokers.common.batch_mixin import BatchFetchMixin
from brokers.common.broker_port import CommonBrokerGateway
from brokers.common.defaults import (
    DEFAULT_DEPTH_TYPE,
    DEFAULT_DERIVATIVES_EXCHANGE,
    DEFAULT_EXCHANGE,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_ORDER_TYPE,
    DEFAULT_PRODUCT_TYPE,
    DEFAULT_SIDE,
    DEFAULT_STREAM_MODE,
    DEFAULT_TIMEFRAME,
    DEFAULT_VALIDITY,
)
from brokers.common.capabilities import (
    BrokerCapabilities,
    HistoricalWindowConstraint,
    RateLimitProfile,
    StreamLimitProfile,
)
from brokers.common.common_broker_access import to_common_broker_gateway
from brokers.common.identity import BrokerId
from brokers.common.gateway import MarketDataGateway, ObservabilityProvider
from brokers.common.responses import OrderResponseFactory as R
from domain import (
    Balance,
    FutureChain,
    Holding,
    MarketDepth,
    OptionChain,
    Order,
    OrderStatus,
    Position,
    Quote,
    Trade,
)
from domain.constants.defaults import PAPER_INITIAL_CAPITAL

from .paper_market_data import PaperMarketData
from .paper_orders import PaperOrders
from .paper_portfolio import PaperPortfolio


class PaperGateway(BatchFetchMixin, MarketDataGateway, ObservabilityProvider):
    """Unified paper-trading API implementing MarketDataGateway v1.0.

    All market-data, order, and portfolio calls delegate to the
    corresponding adapter objects (``market_data``, ``orders``, ``portfolio``).
    """

    def __init__(
        self,
        initial_capital: Decimal = PAPER_INITIAL_CAPITAL,
        *,
        order_manager: Any | None = None,
        position_manager: Any | None = None,
        trading_context: Any | None = None,
    ) -> None:
        # ``trading_context`` is a backward-compatible injection path; composition
        # roots should prefer explicit order_manager / position_manager.
        if trading_context is not None:
            order_manager = order_manager or getattr(trading_context, "order_manager", None)
            position_manager = position_manager or getattr(
                trading_context, "position_manager", None
            )
        self._trading_context = trading_context
        self._market_data = PaperMarketData()
        self._orders = PaperOrders(
            self._market_data,
            {},
            order_manager=order_manager,
            position_manager=position_manager,
        )
        self._portfolio = PaperPortfolio(self._orders, initial_capital)

    def common_broker_gateway(self) -> CommonBrokerGateway:
        """Native CommonBrokerGateway port for infrastructure bootstrap."""
        return to_common_broker_gateway(self, BrokerId.PAPER)

    @property
    def market_data(self) -> PaperMarketData:
        return self._market_data

    @property
    def orders(self) -> PaperOrders:
        return self._orders

    @property
    def trading_context(self) -> Any | None:
        return self._trading_context

    @property
    def portfolio(self) -> PaperPortfolio:
        return self._portfolio

    def place_order(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        side: str = DEFAULT_SIDE,
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str = DEFAULT_ORDER_TYPE,
        product_type: str = DEFAULT_PRODUCT_TYPE,
        validity: str = DEFAULT_VALIDITY,
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> OrderResponse:
        order = self._orders.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )
        return R.direct(
            success=True,
            order_id=order.order_id,
            message="Order filled (paper)",
            status=order.status,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        # PaperOrders.cancel_order returns True if order was found and cancelled, False otherwise
        success = self._orders.cancel_order(order_id)
        cancelled_order = self._orders.get_order(order_id)

        if success and cancelled_order:
            return R.direct(
                success=True,
                order_id=order_id,
                message="Order cancelled (paper)",
                status=OrderStatus.CANCELLED,
            )
        elif cancelled_order and cancelled_order.status == OrderStatus.FILLED:
            return R.direct(
                success=False,
                order_id=order_id,
                message=f"Order {order_id} was already filled before cancel completed",
                status=OrderStatus.FILLED,
            )
        else:
            return R.order_not_found(order_id)

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        # Map values if they are enums
        mapped_changes = {}
        for k, v in changes.items():
            if k == "order_type":
                mapped_changes[k] = v.value if hasattr(v, 'value') else str(v)
            elif k == "validity":
                mapped_changes[k] = v.value if hasattr(v, 'value') else str(v)
            elif k == "product_type":
                mapped_changes[k] = v.value if hasattr(v, 'value') else str(v)
            else:
                mapped_changes[k] = v

        order = self._orders.modify_order(order_id, **mapped_changes)
        return R.direct(
            success=order is not None,
            order_id=order_id,
            message="Order modified (paper)" if order else "Order not found",
            status=order.status if order else None,
        )

    # =======================================================================
    # Market Data (read-only)
    # =======================================================================

    def history(
        self,
        symbol: str | list[str],
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = DEFAULT_TIMEFRAME,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        import hashlib
        from datetime import datetime, timedelta, timezone

        import numpy as np

        symbols = [symbol] if isinstance(symbol, str) else symbol
        n = lookback_days
        dates = [datetime.now(timezone.utc) - timedelta(days=n - i) for i in range(n)]

        rows = []
        for sym in symbols:
            seed = int(hashlib.sha256(sym.encode()).hexdigest()[:8], 16) % (2**31)
            np.random.seed(seed)
            base_price = 500.0 + np.random.uniform(0, 4500)
            close = base_price + np.cumsum(np.random.randn(n) * base_price * 0.02)
            high = close + abs(np.random.randn(n)) * base_price * 0.01
            low = close - abs(np.random.randn(n)) * base_price * 0.01
            open_ = close + np.random.randn(n) * base_price * 0.005
            volume = np.random.randint(10000, 500000, n).astype(float)

            for i in range(n):
                rows.append(
                    {
                        "timestamp": dates[i],
                        "open": round(open_[i], 2),
                        "high": round(high[i], 2),
                        "low": round(low[i], 2),
                        "close": round(close[i], 2),
                        "volume": int(volume[i]),
                        "oi": 0,
                        "symbol": sym,
                        "exchange": exchange,
                        "timeframe": timeframe,
                    }
                )

        return pd.DataFrame(rows)

    def quote(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Quote:
        q = self._market_data.get_quote(symbol, exchange)
        return Quote(
            symbol=symbol,
            ltp=q.ltp,
            open=q.open,
            high=q.high,
            low=q.low,
            close=q.close,
            volume=q.volume,
            change=q.change,
            bid=q.bid,
            ask=q.ask,
            timestamp=q.timestamp,
        )

    def ltp(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Decimal:
        return self._market_data.get_ltp(symbol, exchange)

    def depth(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> MarketDepth:
        d = self._market_data.get_depth(symbol, exchange)
        return MarketDepth(
            symbol=symbol,
            bids=list(d.bids),
            asks=list(d.asks),
        )

    def option_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
        expiry: str | None = None,
    ) -> OptionChain:
        import numpy as np

        base = float(self._market_data.get_ltp(underlying, "NSE"))
        strikes = [round(base + i * 50, 0) for i in range(-10, 11)]
        chain = []
        for strike in strikes:
            chain.append(
                {
                    "strike": strike,
                    "call": {"ltp": round(max(0, base - strike + np.random.uniform(5, 50)), 2)},
                    "put": {"ltp": round(max(0, strike - base + np.random.uniform(5, 50)), 2)},
                }
            )
        return OptionChain.from_dict(
            {
                "underlying": underlying,
                "exchange": exchange,
                "expiry": expiry or "2026-07-30",
                "strikes": chain,
            }
        )

    def future_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
    ) -> FutureChain:
        import numpy as np

        base = float(self._market_data.get_ltp(underlying, "NSE"))
        from datetime import datetime, timedelta

        expiries = [
            (datetime.now() + timedelta(days=30 * i)).strftime("%Y-%m-%d") for i in range(1, 4)
        ]
        contracts = []
        for exp in expiries:
            contracts.append(
                {
                    "expiry": exp,
                    "ltp": round(base * (1 + np.random.uniform(-0.02, 0.03)), 2),
                    "volume": int(np.random.randint(10000, 500000)),
                    "oi": int(np.random.randint(50000, 1000000)),
                    "change": round(np.random.uniform(-2, 2), 2),
                }
            )
        return FutureChain.from_dict(
            {
                "underlying": underlying,
                "exchange": exchange,
                "expiries": expiries,
                "contracts": contracts,
            }
        )

    def stream(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        mode: str = DEFAULT_STREAM_MODE,
        on_tick: Any | None = None,
    ) -> Any:
        class _PaperStream:
            def connect(self):
                pass

            def disconnect(self):
                pass

            @property
            def is_connected(self):
                return False

        return _PaperStream()

    def stream_depth(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        depth_type: str = DEFAULT_DEPTH_TYPE,
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Any:
        class _PaperStream:
            def connect(self):
                pass

            def disconnect(self):
                pass

            @property
            def is_connected(self):
                return False

        return _PaperStream()

    def stream_order(self, on_order: Any | None = None) -> Any:
        class _PaperStream:
            def connect(self):
                pass

            def disconnect(self):
                pass

            @property
            def is_connected(self):
                return False

        return _PaperStream()

    # =======================================================================
    # Trading
    # =======================================================================





    def seed_orders(self, orders: list[Order]) -> None:
        self._orders._orders = orders

    def seed_trades(self, trades: list[Trade]) -> None:
        self._orders._trades = trades

    def seed_positions(self, positions: dict[str, Position]) -> None:
        self._orders._positions = positions

    def seed_holdings(self, holdings: list[Holding]) -> None:
        self._portfolio._holdings = holdings

    def get_order(self, order_id: str) -> Order | None:
        """Query a single order by ID from the orderbook.

        H1 Critical Fix: Enables post-cancellation verification by allowing
        lookup of individual orders.

        Args:
            order_id: Paper order ID to look up

        Returns:
            Order if found, None if not in orderbook
        """
        return self._orders.get_order(order_id)



    def get_orderbook(self) -> list[Order]:
        return self._orders.get_orderbook()

    def get_trade_book(self) -> list[Trade]:
        return self._orders.get_trade_book()

    # =======================================================================
    # Portfolio
    # =======================================================================

    def positions(self) -> list[Position]:
        return self._portfolio.get_positions()

    def holdings(self) -> list[Holding]:
        return self._portfolio.get_holdings()

    def funds(self) -> Balance:
        return self._portfolio.get_balance()

    def trades(self) -> list[Trade]:
        return self._orders.get_trade_book()

    # =======================================================================
    # Instrument
    # =======================================================================

    def search(self, query: str) -> list[dict]:
        return [{"symbol": query.upper(), "exchange": DEFAULT_EXCHANGE, "name": query.upper()}]

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        pass

    # =======================================================================
    # Lifecycle
    # =======================================================================

    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            broker_id=BrokerId.PAPER,
            supports_place_order=True,
            supports_cancel_order=True,
            supports_modify_order=True,
            supports_historical_data=True,
            supports_intraday_history=True,
            supports_expired_options_history=True,
            supports_live_market_data=True,
            supports_depth=True,
            supports_depth_20_ws=True,
            supports_depth_200_ws=False,
            supports_option_chain=True,
            supports_polling_fallback=True,
            supports_order_stream=True,
            supports_portfolio_stream=False,
            supports_news=False,
            supports_fundamentals=False,
            supports_super_order=False,
            supports_forever_order=False,
            supports_native_slice_order=False,
            rate_limit_profiles=(
                RateLimitProfile(
                    endpoint_class="orders",
                    sustained_rps=1000.0,  # Paper trading has no real limits
                    burst_rps=2000.0,
                    min_interval_ms=0,  # No minimum interval for paper
                    cooldown_on_429_s=None,  # No rate limiting
                ),
                RateLimitProfile(
                    endpoint_class="quotes",
                    sustained_rps=1000.0,
                    burst_rps=2000.0,
                    min_interval_ms=0,
                    cooldown_on_429_s=None,
                ),
                RateLimitProfile(
                    endpoint_class="historical",
                    sustained_rps=1000.0,
                    burst_rps=2000.0,
                    min_interval_ms=0,
                    cooldown_on_429_s=None,
                ),
                RateLimitProfile(
                    endpoint_class="option_chain",
                    sustained_rps=1000.0,
                    burst_rps=2000.0,
                    min_interval_ms=0,
                    cooldown_on_429_s=None,
                ),
            ),
            historical_windows=(
                HistoricalWindowConstraint(
                    timeframe="1m",
                    max_lookback_days=3650,
                    max_chunk_days=365,
                    supports_expired_instruments=True,
                ),
                HistoricalWindowConstraint(
                    timeframe="1D",
                    max_lookback_days=3650,
                    max_chunk_days=365,
                ),
            ),
            stream_limits=StreamLimitProfile(
                max_connections=1,
                max_instruments_per_connection=1000,
                max_depth_levels=20,
                supported_stream_modes=frozenset({"LTP", "QUOTE", "FULL"}),
            ),
            latency_class="low",
            reliability_class="tier1",
            product_types=frozenset({"INTRADAY", "MARGIN", "CNC"}),
            order_types=frozenset({"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"}),
            max_batch_size=100,
        )

    def describe(self) -> dict:
        return {
            "broker": BrokerId.PAPER,
            "name": "paper",
            "version": "1.0.0",
            "connected": True,
            "type": "simulated",
        }

    def close(self) -> None:
        """Close resources (noop for simulated gateway)."""
        pass
