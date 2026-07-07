"""Unit tests for Trading bounded context.

Covers:
- Account entity (creation, status transitions, display)
- AccountRegistry (thread-safe one-instance-per-key guarantee)
- AccountHandle (order execution, portfolio delegation)
- TradingContext (account lookup, default account, multi-account)
- Integration with connect()
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from brokers.domain.entities import Balance, Order, OrderResponse, Position
from brokers.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from brokers.trading.account import Account, AccountStatus, AccountType
from brokers.trading.account_registry import AccountRegistry
from brokers.trading.context import AccountHandle, TradingContext

# ═══════════════════════════════════════════════════════════════
# Account entity tests
# ═══════════════════════════════════════════════════════════════


class TestAccount:
    def test_default_account_id(self) -> None:
        acct = Account(account_id="dhan/default", broker_id="dhan")
        assert acct.account_id == "dhan/default"

    def test_default_status_is_active(self) -> None:
        acct = Account(account_id="test", broker_id="test")
        assert acct.status is AccountStatus.ACTIVE

    def test_default_type_is_margin(self) -> None:
        acct = Account(account_id="test", broker_id="test")
        assert acct.type is AccountType.MARGIN

    def test_display_name_uses_name_when_set(self) -> None:
        acct = Account(account_id="dhan/default", broker_id="dhan", name="My Account")
        assert acct.display_name() == "My Account"

    def test_display_name_uses_broker_when_no_name(self) -> None:
        acct = Account(account_id="dhan/default", broker_id="dhan")
        assert "dhan" in acct.display_name()

    def test_active_account_can_trade(self) -> None:
        acct = Account(account_id="test", broker_id="test")
        assert acct.status.can_trade is True

    def test_disabled_account_cannot_trade(self) -> None:
        acct = Account(account_id="test", broker_id="test", status=AccountStatus.DISABLED)
        assert acct.status.can_trade is False

    def test_suspended_account_cannot_trade(self) -> None:
        acct = Account(account_id="test", broker_id="test", status=AccountStatus.SUSPENDED)
        assert acct.status.can_trade is False

    def test_closed_account_is_terminal(self) -> None:
        acct = Account(account_id="test", broker_id="test", status=AccountStatus.CLOSED)
        assert acct.status.is_terminal is True


# ═══════════════════════════════════════════════════════════════
# AccountRegistry tests
# ═══════════════════════════════════════════════════════════════


class TestAccountRegistry:
    def test_get_or_create_returns_same_instance(self) -> None:
        registry = AccountRegistry()
        acct1 = registry.get_or_create(
            "test/default", lambda: Account(account_id="test/default", broker_id="test")
        )
        acct2 = registry.get_or_create(
            "test/default", lambda: Account(account_id="test/default", broker_id="test")
        )
        assert acct1 is acct2

    def test_different_keys_return_different(self) -> None:
        registry = AccountRegistry()
        acct1 = registry.get_or_create(
            "broker1/default", lambda: Account(account_id="broker1/default", broker_id="broker1")
        )
        acct2 = registry.get_or_create(
            "broker2/default", lambda: Account(account_id="broker2/default", broker_id="broker2")
        )
        assert acct1 is not acct2

    def test_factory_called_once(self) -> None:
        call_count = 0

        def factory() -> object:
            nonlocal call_count
            call_count += 1
            return object()

        registry = AccountRegistry()
        registry.get_or_create("test:key", factory)
        registry.get_or_create("test:key", factory)
        registry.get_or_create("test:key", factory)
        assert call_count == 1

    def test_get_returns_none_for_missing(self) -> None:
        registry = AccountRegistry()
        assert registry.get("nonexistent") is None

    def test_thread_safety(self) -> None:
        import threading

        registry = AccountRegistry()
        results: list[object] = []
        lock = threading.Lock()

        def create() -> None:
            acct = registry.get_or_create(
                "test/default", lambda: Account(account_id="test/default", broker_id="test")
            )
            with lock:
                results.append(acct)

        threads = [threading.Thread(target=create) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        first = results[0]
        for r in results[1:]:
            assert r is first, "Thread-safety violation: different objects for same key"

    def test_contains(self) -> None:
        registry = AccountRegistry()
        registry.get_or_create(
            "test/default", lambda: Account(account_id="test/default", broker_id="test")
        )
        assert "test/default" in registry
        assert "other" not in registry

    def test_len(self) -> None:
        registry = AccountRegistry()
        assert len(registry) == 0
        registry.get_or_create("a", lambda: Account(account_id="a", broker_id="x"))
        registry.get_or_create("b", lambda: Account(account_id="b", broker_id="x"))
        assert len(registry) == 2


# ═══════════════════════════════════════════════════════════════
# TradingContext tests
# ═══════════════════════════════════════════════════════════════


class _FakeOrderExecution:
    """Minimal OrderExecutionPort fake."""

    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}

    def place_order(
        self,
        symbol,
        exchange,
        side,
        quantity,
        order_type=OrderType.MARKET,
        price=Decimal("0"),
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
        trigger_price=Decimal("0"),
    ) -> OrderResponse:
        order_id = f"FAKE-{len(self.orders) + 1}"
        order = Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
            status=OrderStatus.OPEN,
        )
        self.orders[order_id] = order
        return OrderResponse(order_id=order_id, success=True, status=OrderStatus.OPEN)

    def modify_order(
        self, order_id, quantity=None, price=None, order_type=None, validity=None
    ) -> OrderResponse:
        return OrderResponse(order_id=order_id, success=True)

    def cancel_order(self, order_id) -> OrderResponse:
        return OrderResponse(order_id=order_id, success=True)

    def get_order(self, order_id) -> Order | None:
        return self.orders.get(order_id)

    def get_orderbook(self) -> list[Order]:
        return list(self.orders.values())


class _FakePortfolio:
    """Minimal PortfolioPort fake."""

    def positions(self) -> list[Position]:
        return [Position(symbol="RELIANCE", exchange="NSE", quantity=10)]

    def holdings(self) -> list:
        return []

    def funds(self) -> Balance:
        return Balance(available_cash=Decimal("100000.00"))

    def trades(self) -> list:
        return []


@pytest.fixture
def fake_order_execution() -> _FakeOrderExecution:
    return _FakeOrderExecution()


@pytest.fixture
def fake_portfolio() -> _FakePortfolio:
    return _FakePortfolio()


@pytest.fixture
def context(
    fake_order_execution: _FakeOrderExecution, fake_portfolio: _FakePortfolio
) -> TradingContext:
    from brokers.trading.account_registry import AccountRegistry

    registry = AccountRegistry()
    return TradingContext(
        registry=registry,
        order_execution=fake_order_execution,
        portfolio=fake_portfolio,
        broker_id="test",
    )


class TestTradingContext:
    def test_default_account_auto_created(self, context: TradingContext) -> None:
        acct = context.default_account()
        assert acct.account_id == "test/default"
        assert acct.broker_id == "test"

    def test_account_by_id(self, context: TradingContext) -> None:
        acct = context.account("test/default")
        assert acct.account_id == "test/default"

    def test_account_none_returns_default(self, context: TradingContext) -> None:
        acct = context.account(None)
        assert acct.account_id == "test/default"

    def test_account_not_found_raises_key_error(self, context: TradingContext) -> None:
        with pytest.raises(KeyError):
            context.account("nonexistent")

    def test_accounts_returns_all(self, context: TradingContext) -> None:
        all_accts = context.accounts()
        assert len(all_accts) >= 1
        assert all(isinstance(a, AccountHandle) for a in all_accts)

    def test_repr(self, context: TradingContext) -> None:
        assert "TradingContext" in repr(context)


class TestAccountHandle:
    def test_delegates_account_id(self, context: TradingContext) -> None:
        acct = context.default_account()
        assert acct.account_id == "test/default"

    def test_delegates_broker_id(self, context: TradingContext) -> None:
        acct = context.default_account()
        assert acct.broker_id == "test"

    def test_delegates_display_name(self, context: TradingContext) -> None:
        acct = context.default_account()
        assert acct.display_name() == "Test Default Account"

    def test_place_order(self, context: TradingContext) -> None:
        acct = context.default_account()
        resp = acct.place_order("RELIANCE", "NSE", Side.BUY, 10)
        assert resp.success is True
        assert resp.order_id.startswith("FAKE-")

    def test_place_order_with_limit(self, context: TradingContext) -> None:
        acct = context.default_account()
        resp = acct.place_order(
            "TCS", "NSE", Side.BUY, 5, order_type=OrderType.LIMIT, price=Decimal("3500")
        )
        assert resp.success is True

    def test_get_orders(
        self, context: TradingContext, fake_order_execution: _FakeOrderExecution
    ) -> None:
        fake_order_execution.place_order("RELIANCE", "NSE", Side.BUY, 10)
        acct = context.default_account()
        orders = acct.get_orders()
        assert len(orders) >= 1

    def test_modify_order(self, context: TradingContext) -> None:
        acct = context.default_account()
        resp = acct.modify_order("order-1", quantity=20)
        assert resp.success is True

    def test_cancel_order(self, context: TradingContext) -> None:
        acct = context.default_account()
        resp = acct.cancel_order("order-1")
        assert resp.success is True

    def test_positions(self, context: TradingContext) -> None:
        acct = context.default_account()
        positions = acct.positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"

    def test_holdings(self, context: TradingContext) -> None:
        acct = context.default_account()
        holdings = acct.holdings()
        assert isinstance(holdings, list)

    def test_funds(self, context: TradingContext) -> None:
        acct = context.default_account()
        balance = acct.funds()
        assert balance.available_cash == Decimal("100000.00")

    def test_trades(self, context: TradingContext) -> None:
        acct = context.default_account()
        trades = acct.trades()
        assert isinstance(trades, list)

    def test_repr(self, context: TradingContext) -> None:
        acct = context.default_account()
        assert "AccountHandle" in repr(acct)

    def test_getattr_raises_for_private(self, context: TradingContext) -> None:
        acct = context.default_account()
        with pytest.raises(AttributeError):
            _ = acct._secret

    def test_disabled_account_raises_on_place(self, context: TradingContext) -> None:
        """Disabled accounts should reject order placement."""
        from brokers.domain.exceptions import BrokerError
        from brokers.trading.account_registry import AccountRegistry

        registry = AccountRegistry()
        disabled = Account(
            account_id="test/disabled", broker_id="test", status=AccountStatus.DISABLED
        )
        registry.get_or_create("test/disabled", lambda: disabled)

        ctx = TradingContext(
            registry=registry,
            order_execution=_FakeOrderExecution(),
            portfolio=_FakePortfolio(),
            broker_id="test",
        )
        acct = ctx.account("test/disabled")
        with pytest.raises(BrokerError, match="DISABLED"):
            acct.place_order("RELIANCE", "NSE", Side.BUY, 10)


# ═══════════════════════════════════════════════════════════════
# Integration: connect() wiring
# ═══════════════════════════════════════════════════════════════


class TestTradingIntegration:
    def test_connect_wires_trading_context(self) -> None:
        """Verify connect() creates TradingContext on BrokerSession."""
        import brokers

        broker = brokers.connect("paper")
        try:
            from brokers.trading.context import TradingContext

            # broker.trading should be a TradingContext
            assert isinstance(broker.trading, TradingContext)

            # Default account exists
            acct = broker.trading.default_account()
            assert acct.account_id == "paper/default"
            assert acct.broker_id == "paper"

            # AccountHandle delegates
            assert acct.display_name is not None
        finally:
            broker.close()

    def test_place_order_through_trading_context(self) -> None:
        """Verify orders can be placed through broker.trading."""
        from brokers.domain.enums import Side

        import brokers

        broker = brokers.connect("paper")
        try:
            acct = broker.trading.default_account()
            resp = acct.place_order("RELIANCE", "NSE", Side.BUY, 10)
            assert resp.success is True
            assert resp.order_id.startswith("PAPER-")
        finally:
            broker.close()

    def test_portfolio_through_trading_context(self) -> None:
        """Verify portfolio access through broker.trading."""
        from brokers.domain import Balance

        import brokers

        broker = brokers.connect("paper")
        try:
            acct = broker.trading.default_account()
            balance = acct.funds()
            assert isinstance(balance, Balance)
            assert balance.available_cash > 0
        finally:
            broker.close()

    def test_legacy_orders_still_work(self) -> None:
        """Verify old broker.orders.place_order() still works."""
        from brokers.domain.enums import Side

        import brokers

        broker = brokers.connect("paper")
        try:
            resp = broker.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
            assert resp.success is True
        finally:
            broker.close()

    def test_both_paths_coexist(self) -> None:
        """Verify old and new order paths both work simultaneously."""
        from brokers.domain.enums import Side

        import brokers

        broker = brokers.connect("paper")
        try:
            # New path: through trading context
            acct = broker.trading.default_account()
            resp1 = acct.place_order("RELIANCE", "NSE", Side.BUY, 10)
            assert resp1.success is True

            # Old path: through orders property
            resp2 = broker.orders.place_order("TCS", "NSE", Side.SELL, 5)
            assert resp2.success is True

            # Both orders exist
            orders_new = acct.get_orders()
            orders_old = broker.orders.get_orders()
            assert len(orders_new) >= 1
            assert len(orders_old) >= 2
        finally:
            broker.close()

    def test_market_isolated_from_trading(self) -> None:
        """Verify market context does not leak into trading context."""
        import brokers

        broker = brokers.connect("paper")
        try:
            # Market data works
            q = broker.market.quote("RELIANCE")
            assert q is not None

            # Trading works
            acct = broker.trading.default_account()
            assert acct is not None

            # Market context does not have trading methods
            assert not hasattr(broker.market, "place_order")
        finally:
            broker.close()
