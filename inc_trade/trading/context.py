"""TradingContext — single entry point for the Trading bounded context.

This is the public facade for all trading operations. It manages accounts,
order execution, and portfolio access. Returns ``AccountHandle`` objects
that wrap the raw ``Account`` entity with trading operations.

Usage::

    context = TradingContext(
        registry=account_registry,
        order_execution=dhan_order_execution_port,
        portfolio=dhan_portfolio_port,
        broker_id="dhan",
    )

    account = context.default_account()
    resp = account.place_order("RELIANCE", "NSE", Side.BUY, 10)
    positions = account.positions()
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from inc_trade.domain.entities import Balance, Candle, Holding, Order, OrderResponse, Position, Trade
from inc_trade.domain.enums import OrderType, ProductType, Side, Validity
from inc_trade.ports.order_execution import OrderExecutionPort
from inc_trade.ports.portfolio import PortfolioPort
from inc_trade.trading.account import Account, AccountStatus, AccountType
from inc_trade.trading.account_registry import AccountRegistry
from inc_trade.trading.order_repository import OrderRepository

logger = logging.getLogger(__name__)


class AccountHandle:
    """Lightweight handle wrapping an Account with trading operations.

    Returned by ``TradingContext.account()``. Provides order placement,
    portfolio access, and position management by delegating to the
    injected ports.

    The underlying ``Account`` attributes (``account_id``, ``broker_id``,
    ``name``, …) are accessible via automatic delegation.
    """

    def __init__(
        self,
        account: Account,
        order_execution: OrderExecutionPort,
        portfolio: PortfolioPort,
        oms: Any | None = None,
    ) -> None:
        self._account = account
        self._order_execution = order_execution
        self._portfolio = portfolio
        self._oms = oms

    # ── Automatic delegation to Account ────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying Account.

        Provides transparent access to all Account properties
        (``account_id``, ``broker_id``, ``name``, …) and methods
        (``display_name()``, …).
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._account, name)

    # ── Order Execution ────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str = "",
        exchange: str = "",
        side: Side = Side.BUY,
        quantity: int = 0,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str = "",
    ) -> OrderResponse:
        """Place an order for this account.

        Uses OMS path when available (new), falls back to direct
        ``OrderExecutionPort`` for backward compatibility.

        The OMS path provides:
        - Full field validation via domain validators
        - Kill switch checking
        - Idempotency via correlation_id
        - Order repository tracking
        - Correct broker routing
        """
        if self._account.status is not AccountStatus.ACTIVE:
            from inc_trade.domain.exceptions import BrokerError

            raise BrokerError(
                f"Account {self._account.account_id} is {self._account.status.value}. "
                "Only ACTIVE accounts can place orders."
            )

        # New OMS path
        if self._oms is not None:
            return self._oms.place_order(
                account_id=self._account.account_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price,
                product_type=product_type,
                validity=validity,
                trigger_price=trigger_price,
                correlation_id=correlation_id,
            )

        # Legacy path (backward compatibility)
        return self._order_execution.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            product_type=product_type,
            validity=validity,
            trigger_price=trigger_price,
        )

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> OrderResponse:
        """Modify an existing order.

        Uses OMS path when available (new), falls back to direct
        ``OrderExecutionPort`` for backward compatibility.
        """
        if self._oms is not None:
            return self._oms.modify_order(
                account_id=self._account.account_id,
                order_id=order_id,
                quantity=quantity,
                price=price,
                order_type=order_type,
                validity=validity,
            )
        return self._order_execution.modify_order(
            order_id=order_id,
            quantity=quantity,
            price=price,
            order_type=order_type,
            validity=validity,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an existing order.

        Uses OMS path when available (new), falls back to direct
        ``OrderExecutionPort`` for backward compatibility.
        """
        if self._oms is not None:
            return self._oms.cancel_order(
                account_id=self._account.account_id,
                order_id=order_id,
            )
        return self._order_execution.cancel_order(order_id)

    def get_orders(self) -> list[Order]:
        """Get all orders for this account."""
        return self._order_execution.get_orderbook()

    def get_order(self, order_id: str) -> Order | None:
        """Get a specific order by ID."""
        return self._order_execution.get_order(order_id)

    # ── Portfolio ──────────────────────────────────────────────────────

    def positions(self) -> list[Position]:
        """Get current positions for this account."""
        return self._portfolio.positions()

    def holdings(self) -> list[Holding]:
        """Get current holdings for this account."""
        return self._portfolio.holdings()

    def funds(self) -> Balance:
        """Get available funds for this account."""
        return self._portfolio.funds()

    def trades(self) -> list[Trade]:
        """Get trade history for this account."""
        return self._portfolio.trades()

    def __repr__(self) -> str:
        return f"AccountHandle({self._account!r})"


class TradingContext:
    """Facade for all trading operations.

    Single entry point for the Trading bounded context. Manages accounts,
    order execution, and portfolio access.

    Args:
        registry: AccountRegistry for account lookups.
        order_execution: OrderExecutionPort implementation.
        portfolio: PortfolioPort implementation.
        broker_id: Canonical broker identifier.
    """

    def __init__(
        self,
        registry: AccountRegistry,
        order_execution: OrderExecutionPort,
        portfolio: PortfolioPort,
        broker_id: str,
        oms: Any | None = None,
        order_repository: OrderRepository | None = None,
    ) -> None:
        self._registry = registry
        self._order_execution = order_execution
        self._portfolio = portfolio
        self._broker_id = broker_id
        self._oms = oms
        self._order_repository = order_repository or OrderRepository()

        # Auto-register a default account for this broker
        default_id = f"{broker_id}/default"
        if default_id not in self._registry:
            default_account = Account(
                account_id=default_id,
                broker_id=broker_id,
                name=f"{broker_id.title()} Default Account",
                type=AccountType.MARGIN,
                status=AccountStatus.ACTIVE,
            )
            self._registry.get_or_create(default_id, lambda a=default_account: a)

    # ── Account Access ─────────────────────────────────────────────────

    def account(self, account_id: str | None = None) -> AccountHandle:
        """Look up an account by ID.

        Args:
            account_id: Account identifier. If None, returns the default
                account for this broker.

        Returns:
            AccountHandle instance.

        Raises:
            KeyError: If the account is not found.
        """
        if account_id is None:
            account_id = f"{self._broker_id}/default"
        acct = self._registry.get(account_id)
        if acct is None:
            raise KeyError(f"Account not found: {account_id}")
        return AccountHandle(
            account=acct,
            order_execution=self._order_execution,
            portfolio=self._portfolio,
            oms=self._oms,
        )

    def default_account(self) -> AccountHandle:
        """Get the default account for this broker.

        Equivalent to ``account(None)``.
        """
        return self.account(None)

    def accounts(self) -> list[AccountHandle]:
        """Get all registered accounts."""
        return [
            AccountHandle(
                account=acct,
                order_execution=self._order_execution,
                portfolio=self._portfolio,
                oms=self._oms,
            )
            for acct in self._registry.get_all().values()
        ]

    def __repr__(self) -> str:
        return f"TradingContext(broker_id={self._broker_id!r})"
