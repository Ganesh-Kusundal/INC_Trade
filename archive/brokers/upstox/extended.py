"""Upstox extended capabilities — broker-specific methods beyond MarketDataGateway ABC.

This module contains Upstox-specific functionality that extends beyond the
frozen MarketDataGateway v1.0 contract (ADR-002). These methods are exposed
via the ``gateway.extended`` property to maintain architectural compliance
while preserving backward compatibility during the deprecation period.

Usage::

    gateway = UpstoxBrokerGateway(broker)

    # New way (recommended)
    ipos = gateway.extended.get_ipos()
    pnl = gateway.extended.get_pnl("INE002A01018")

    # Old way (deprecated, will be removed in future version)
    ipos = gateway.get_ipos()  # Issues DeprecationWarning
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brokers.upstox.broker import UpstoxBroker


class UpstoxExtendedCapabilities:
    """Upstox-specific capabilities beyond the MarketDataGateway ABC.

    This class provides access to broker-specific features including:
    - IPO applications and status
    - Payment/payout management
    - Mutual fund orders and holdings
    - Fundamental data (PnL, balance sheet, cash flow, ratios)
    - User profile information
    - Position conversion
    - Trade PnL calculations

    All methods delegate to the underlying UpstoxBroker adapters.
    """

    def __init__(self, broker: UpstoxBroker) -> None:
        """Initialize with reference to the UpstoxBroker.

        Args:
            broker: The UpstoxBroker instance providing adapter access
        """
        self._broker = broker
        broker._ensure_extended()

    # ── IPO ────────────────────────────────────────────────────────────

    def get_ipos(self, status: str = "open") -> list[dict[str, Any]]:
        """Get list of IPOs filtered by status.

        Args:
            status: Filter by status ("open", "closed", "upcoming")

        Returns:
            List of IPO dictionaries
        """
        return self._broker.ipo.get_ipos(status=status)

    # ── Payments ───────────────────────────────────────────────────────

    def initiate_payout(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Initiate a payout/withdrawal.

        Args:
            payload: Payout request payload

        Returns:
            Payout response dictionary

        Raises:
            RuntimeError: If live orders are disabled
        """
        # Safety guard: check analytics-only mode
        if self._broker.settings.analytics_only:
            raise RuntimeError("Analytics-only mode: live payouts are blocked.")
        if not self._broker.settings.allow_live_orders:
            raise RuntimeError(
                "Live payouts are disabled. Set allow_live_orders=True in configuration."
            )
        return self._broker.payments.initiate_payout(payload)

    def get_payouts(self) -> list[dict[str, Any]]:
        """Get list of payouts.

        Returns:
            List of payout dictionaries
        """
        return self._broker.payments.get_payouts()

    def modify_payout(self, payout_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Modify an existing payout.

        Args:
            payout_id: ID of the payout to modify
            payload: Modification payload

        Returns:
            Modified payout response dictionary
        """
        return self._broker.payments.modify_payout(payout_id, payload)

    def cancel_payout(self, payout_id: str) -> dict[str, Any]:
        """Cancel a payout.

        Args:
            payout_id: ID of the payout to cancel

        Returns:
            Cancellation response dictionary
        """
        return self._broker.payments.cancel_payout(payout_id)

    # ── Mutual Funds ───────────────────────────────────────────────────

    def get_mutual_fund_holdings(self) -> list[dict[str, Any]]:
        """Get mutual fund holdings.

        Returns:
            List of mutual fund holding dictionaries
        """
        return self._broker.mutual_funds.get_holdings()

    def place_mutual_fund_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Place a mutual fund order.

        Args:
            payload: Order payload

        Returns:
            Order response dictionary

        Raises:
            RuntimeError: If live orders are disabled
        """
        # Safety guard: check analytics-only mode
        if self._broker.settings.analytics_only:
            raise RuntimeError("Analytics-only mode: live mutual fund orders are blocked.")
        if not self._broker.settings.allow_live_orders:
            raise RuntimeError(
                "Live mutual fund orders are disabled. Set allow_live_orders=True in configuration."
            )
        return self._broker.mutual_funds.place_order(payload)

    # ── Fundamentals ───────────────────────────────────────────────────

    def get_pnl(self, isin: str) -> dict[str, Any]:
        """Get PnL statement for a security.

        Args:
            isin: ISIN of the security

        Returns:
            PnL data dictionary
        """
        return self._broker.fundamentals.get_pnl(isin)

    def get_balance_sheet(self, isin: str) -> dict[str, Any]:
        """Get balance sheet for a security.

        Args:
            isin: ISIN of the security

        Returns:
            Balance sheet data dictionary
        """
        return self._broker.fundamentals.get_balance_sheet(isin)

    def get_cash_flow(self, isin: str) -> dict[str, Any]:
        """Get cash flow statement for a security.

        Args:
            isin: ISIN of the security

        Returns:
            Cash flow data dictionary
        """
        return self._broker.fundamentals.get_cash_flow(isin)

    def get_ratios(self, isin: str) -> dict[str, Any]:
        """Get financial ratios for a security.

        Args:
            isin: ISIN of the security

        Returns:
            Financial ratios dictionary
        """
        return self._broker.fundamentals.get_ratios(isin)

    # ── User Profile & Positions ───────────────────────────────────────

    def get_user_profile(self) -> dict[str, Any]:
        """Get user profile information.

        Returns:
            User profile dictionary
        """
        return self._broker.portfolio.get_profile()

    def convert_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Convert position (e.g., intraday to delivery).

        Args:
            payload: Position conversion payload

        Returns:
            Conversion response dictionary
        """
        return self._broker.portfolio_client.convert_position(payload)

    def get_trade_pnl(self) -> list[dict[str, Any]]:
        """Get PnL for all trades.

        Returns:
            List of trade PnL dictionaries
        """
        pnl_results = self._broker.trade_pnl_calculator.calculate_all_pnl()
        return [
            {
                "symbol": pnl.symbol,
                "exchange": pnl.exchange,
                "realized_pnl": float(pnl.realized_pnl),
                "unrealized_pnl": float(pnl.unrealized_pnl),
                "total_pnl": float(pnl.total_pnl),
                "trades": pnl.trades,
            }
            for pnl in pnl_results
        ]
