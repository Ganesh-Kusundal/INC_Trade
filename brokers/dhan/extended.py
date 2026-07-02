"""Dhan extended capabilities — broker-specific methods beyond MarketDataGateway ABC.

This module contains Dhan-specific functionality that extends beyond the
MarketDataGateway contract. These methods are exposed via the
``gateway.extended`` property to maintain architectural compliance.

Usage::

    gateway = BrokerGateway(connection)

    # Broker-specific operations via extended
    expiries = gateway.extended.get_option_expiries("NIFTY", "NFO")
    contracts = gateway.extended.get_futures_contracts("GOLD", "MCX")
    errors = gateway.extended.validate_order(symbol="RELIANCE", ...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.entities import OrderResponse
from domain.symbols import normalize_exchange, normalize_symbol

if TYPE_CHECKING:
    from brokers.dhan.connection import DhanConnection


class DhanExtendedCapabilities:
    """Dhan-specific capabilities beyond the MarketDataGateway ABC.

    This class provides access to broker-specific features including:
    - Super orders (bracket orders)
    - Forever orders (GTT)
    - Conditional triggers
    - Ledger entries
    - User profile
    - IP management
    - EDIS (e-DIS)
    - Option expiry listing
    - Futures contract listing
    - Order validation
    """

    def __init__(self, conn: DhanConnection) -> None:
        self._conn = conn

    @property
    def instruments(self) -> Any:
        """Access the instrument resolver for symbol resolution."""
        return self._conn.instruments

    @property
    def identity(self) -> Any:
        """Access the Dhan identity provider (PR-A).

        The provider is the single source of truth for symbol→security_id
        resolution. Adapters and callers that need to build a Dhan HTTP
        payload must go through ``identity.resolve_ref(symbol, exchange)``
        rather than calling the resolver directly.
        """
        return self._conn.identity

    @property
    def orders(self) -> Any:
        """Access the orders adapter (idempotency cache, validation, etc.)."""
        return self._conn.orders

    # ── Portfolio shortcuts (contract-suite compat) ─────────────────

    def get_positions(self) -> list[Any]:
        """Get current positions."""
        return self._conn.portfolio.get_positions()

    def get_holdings(self) -> list[Any]:
        """Get current holdings."""
        return self._conn.portfolio.get_holdings()

    def get_balance(self) -> Any:
        """Get account balance."""
        return self._conn.portfolio.get_balance()

    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        """Alias for get_option_expiries — used by contract suite."""
        return self.get_option_expiries(underlying, exchange)

    # ── Super Orders (Bracket Orders) ─────────────────────────────────

    def place_super_order(self, **kwargs: Any) -> Any:
        """Place a super order (bracket order with target, SL, trail)."""
        return self._conn.super_orders.place_super_order(**kwargs)

    def modify_super_order(self, order_id: str, **kwargs: Any) -> Any:
        """Modify a super order."""
        return self._conn.super_orders.modify_super_order(order_id, **kwargs)

    def cancel_super_order_leg(self, order_id: str, leg_name: str) -> OrderResponse:
        """Cancel a specific leg of a super order."""
        return self._conn.super_orders.cancel_super_order_leg(order_id, leg_name)

    def get_super_orders(self) -> list[Any]:
        """Get all super orders."""
        return self._conn.super_orders.get_super_orders()

    # ── Forever Orders (GTT) ──────────────────────────────────────────

    def place_forever_order(self, request: Any) -> Any:
        """Place a forever (GTT) order."""
        return self._conn.forever_orders.place_forever_order(request)

    def modify_forever_order(self, order_id: str, request: Any) -> Any:
        """Modify a forever order."""
        return self._conn.forever_orders.modify_forever_order(order_id, request)

    def cancel_forever_order(self, order_id: str) -> OrderResponse:
        """Cancel a forever order."""
        return self._conn.forever_orders.cancel_forever_order(order_id)

    def get_all_forever_orders(self) -> list[Any]:
        """Get all forever orders."""
        return self._conn.forever_orders.get_all_forever_orders()

    # ── Conditional Triggers ──────────────────────────────────────────

    def place_conditional_trigger(self, request: Any) -> Any:
        """Place a conditional trigger/alert."""
        return self._conn.conditional_triggers.place_trigger(request)

    def modify_conditional_trigger(self, alert_id: str, request: Any) -> Any:
        """Modify a conditional trigger."""
        return self._conn.conditional_triggers.modify_trigger(alert_id, request)

    def delete_conditional_trigger(self, alert_id: str) -> bool:
        """Delete a conditional trigger."""
        return self._conn.conditional_triggers.delete_trigger(alert_id)

    def get_conditional_trigger(self, alert_id: str) -> Any:
        """Get a conditional trigger by ID."""
        return self._conn.conditional_triggers.get_trigger(alert_id)

    def get_all_conditional_triggers(self) -> list[Any]:
        """Get all conditional triggers."""
        return self._conn.conditional_triggers.get_all_triggers()

    # ── Ledger ────────────────────────────────────────────────────────

    def get_ledger(self, from_date: str, to_date: str) -> list[Any]:
        """Get ledger entries for a date range."""
        return self._conn.ledger.get_ledger(from_date, to_date)

    # ── User Profile ──────────────────────────────────────────────────

    def get_user_profile(self) -> Any:
        """Get user profile information."""
        return self._conn.user_profile.get_profile()

    # ── IP Management ─────────────────────────────────────────────────

    def set_ip(self, ip_address: str, ip_type: str) -> dict:
        """Set IP address for API access."""
        return self._conn.ip_management.set_ip(ip_address, ip_type)

    def modify_ip(self, ip_address: str, ip_type: str) -> dict:
        """Modify IP address."""
        return self._conn.ip_management.modify_ip(ip_address, ip_type)

    def get_ip(self) -> list[Any]:
        """Get configured IP addresses."""
        return self._conn.ip_management.get_ip()

    # ── EDIS (Electronic Delivery Instruction) ────────────────────────

    def generate_tpin(self) -> dict:
        """Generate TPIN for EDIS."""
        return self._conn.edis.generate_tpin()

    def authorize_edis(self, isin: str, quantity: int, exchange: str) -> dict:
        """Authorize EDIS transaction."""
        return self._conn.edis.authorize_edis(isin, quantity, exchange)

    def check_edis_status(self, isin: str) -> dict:
        """Check EDIS authorization status."""
        return self._conn.edis.check_status(isin)

    # ── Exit All ──────────────────────────────────────────────────────

    def exit_all(self) -> Any:
        """Close all open positions."""
        return self._conn.exit_all.exit_all()

    # ── Options (broker-specific) ────────────────────────────────────

    def get_option_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        """Get available option expiry dates."""
        return self._conn.options.get_expiries(underlying, exchange)

    def get_expired_options_data(
        self,
        security_id: int,
        expiry_flag: str,
        expiry_code: int,
        strike: str,
        option_type: str,
        from_date: str,
        to_date: str,
        required_data: list[str] | None = None,
        interval: int = 1,
    ) -> dict:
        """Fetch expired options OHLCV data from Dhan rolling option API."""
        return self._conn.options.get_expired_options_data(
            security_id=security_id,
            expiry_flag=expiry_flag,
            expiry_code=expiry_code,
            strike=strike,
            option_type=option_type,
            from_date=from_date,
            to_date=to_date,
            required_data=required_data,
            interval=interval,
        )

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> dict:
        """Get option chain with MCX-specific expiry lookup.

        For MCX underlyings, resolves the nearest futures contract to find the
        security ID, then uses the Dhan optionchain/expirylist endpoint directly.
        For NFO/BFO, delegates to the standard options adapter.
        """
        from brokers.dhan.segments import EXCHANGE_TO_SEGMENT

        mcx_underlyings = {
            "CRUDEOIL",
            "CRUDEOILM",
            "GOLD",
            "SILVER",
            "COPPER",
            "ZINC",
            "NATURALGAS",
            "ALUMINIUM",
            "LEAD",
            "NIKKEI",
        }
        sec_id = None
        seg = None
        if normalize_symbol(underlying) in mcx_underlyings and normalize_exchange(exchange) == "MCX":
            seg = EXCHANGE_TO_SEGMENT.get("MCX", "MCX_COMM")
            futures = [
                i
                for i in self._conn.instruments.all_instruments()
                if i.symbol.upper().startswith(normalize_symbol(underlying) + "-")
                and i.exchange.value == "MCX"
                and i.is_future
            ]
            futures.sort(key=lambda x: x.expiry or "")
            if futures:
                sec_id = int(futures[0].security_id)
        if expiry is None:
            if sec_id and seg:
                response = self._conn.client.post(
                    "/optionchain/expirylist",
                    json={
                        "UnderlyingScrip": sec_id,
                        "UnderlyingSeg": seg,
                    },
                )
                raw = response.get("data", response)
                if isinstance(raw, dict):
                    expiries = raw.get("expiryList") or raw.get("expiries") or []
                elif isinstance(raw, list):
                    expiries = raw
                else:
                    expiries = []
            else:
                expiries = self._conn.options.get_expiries(underlying, exchange)
            if not expiries:
                raise ValueError(f"No expiries found for {underlying}")
            expiry = expiries[0]
        if sec_id and seg:
            return self._conn.options.get_option_chain(
                underlying, exchange, expiry, security_id=sec_id
            )
        return self._conn.options.get_option_chain(underlying, exchange, expiry)

    # ── Futures (broker-specific) ────────────────────────────────────

    def get_futures_contracts(self, underlying: str, exchange: str = "NFO") -> list[dict]:
        """Get futures contracts for an underlying."""
        return self._conn.futures.get_contracts(underlying, exchange)

    def get_futures_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        """Get available futures expiry dates."""
        return self._conn.futures.get_expiries(underlying, exchange)

    def is_commodity(self, symbol: str) -> bool:
        """Check if a symbol is a commodity futures contract."""
        return self._conn.futures.is_commodity(symbol)

    # ── Order Validation ──────────────────────────────────────────────

    def validate_order(self, **kwargs: Any) -> list[str]:
        """Validate an order before placing. Returns list of errors (empty = valid)."""
        return self._conn.orders.validate_order(**kwargs)

    # ── Alerts ────────────────────────────────────────────────────────

    def get_alerts(self) -> list[Any]:
        """Get all alerts."""
        return self._conn.alerts.get_alerts() if hasattr(self._conn.alerts, "get_alerts") else []
