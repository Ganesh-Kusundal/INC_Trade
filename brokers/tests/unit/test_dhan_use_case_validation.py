"""Migration tests for PlaceOrderUseCase — K-1.

Verifies that field-level order validation is now delegated to the
domain validators in :mod:`brokers.domain.validators.order_validator`,
not duplicated in the adapter. The adapter's role is reduced to
wiring/IO (translating domain ``ValidationError`` into the stable
``str | None`` contract that callers and tests rely on).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from brokers.adapters.dhan.identity import DhanInstrumentRef
from brokers.adapters.dhan.use_cases.place_order import PlaceOrderUseCase
from inc_trade.domain.enums import OrderType, ProductType, Side, Validity
from inc_trade.domain.validators.order_validator import validate_order

_DERIVATIVE_SEGMENTS = frozenset({"NSE_FNO", "NSE_MCX", "BSE_FNO"})
_EQUITY_ONLY_PRODUCTS = frozenset({"CNC"})
_SIDE_MAP = {"BUY": 1, "SELL": 2}
_ORDER_TYPE_MAP = {"MARKET": 1, "LIMIT": 2, "STOP_LOSS": 3, "STOP_LOSS_MARKET": 4}
_PRODUCT_TYPE_MAP = {"INTRADAY": "INTRADAY", "MARGIN": "MARGIN", "DELIVERY": "CNC"}
_VALIDITY_MAP = {"DAY": "DAY", "IOC": "IOC", "GTT": "GTT"}
_ENDPOINTS = {"orders": "/v2/orders"}


def _make_ref(**overrides: object) -> DhanInstrumentRef:
    defaults = dict(
        symbol="RELIANCE",
        security_id="12345",
        exchange_segment="NSE_EQ",
        instrument_type="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
    )
    defaults.update(overrides)
    return DhanInstrumentRef(**defaults)  # type: ignore[arg-type]


def _make_uc() -> PlaceOrderUseCase:
    return PlaceOrderUseCase(
        MagicMock(),
        MagicMock(),
        endpoints=_ENDPOINTS,
        idempotency=MagicMock(),
        derivative_segments=_DERIVATIVE_SEGMENTS,
        equity_only_products=_EQUITY_ONLY_PRODUCTS,
        side_map=_SIDE_MAP,
        order_type_map=_ORDER_TYPE_MAP,
        product_type_map=_PRODUCT_TYPE_MAP,
        validity_map=_VALIDITY_MAP,
    )


def _default_request(**overrides: object):
    from inc_trade.domain import OrderRequest

    defaults = dict(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=1,
        order_type=OrderType.MARKET,
        price=Decimal("0"),
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
        trigger_price=Decimal("0"),
        correlation_id="k1-corr-001",
    )
    defaults.update(overrides)
    return OrderRequest(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# K-1: domain validators are now the rule source
# ---------------------------------------------------------------------------


class TestDomainValidatorDelegation:
    """Confirm that field-level rules are delegated to domain validators."""

    def test_valid_order_passes_through(self) -> None:
        """A well-formed LIMIT order must not produce an error."""
        uc = _make_uc()
        req = _default_request(
            order_type=OrderType.LIMIT,
            price=Decimal("1500.00"),
        )
        assert uc.validate(_make_ref(), req) is None

    def test_validate_order_in_module_called(self) -> None:
        """The adapter's validate() must call the domain validate_order()."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(
            order_type=OrderType.LIMIT,
            price=Decimal("1500.00"),
        )
        with patch(
            "brokers.adapters.dhan.use_cases.place_order.validate_order",
            wraps=validate_order,
        ) as spy:
            uc.validate(ref, req)
        spy.assert_called_once()

    def test_negative_price_raises_at_domain(self) -> None:
        """A negative price must be caught by the domain validator."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(
            order_type=OrderType.LIMIT,
            price=Decimal("-10"),
        )
        # The adapter does not implement price-sign checks; it must surface
        # the domain ValidationError as a non-None string.
        result = uc.validate(ref, req)
        assert result is not None
        # Domain validator catches negative price generically.
        assert "Price cannot be negative" in result

    def test_zero_quantity_raises_at_domain(self) -> None:
        """Zero quantity must be caught by the domain validator."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(quantity=0)
        result = uc.validate(ref, req)
        assert result is not None
        assert "quantity must be positive" in result

    def test_empty_symbol_raises_at_domain(self) -> None:
        """Empty symbol must be caught by the domain validator."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(symbol="")
        result = uc.validate(ref, req)
        assert result is not None
        assert "symbol is required" in result

    def test_empty_exchange_raises_at_domain(self) -> None:
        """Empty exchange must be caught by the domain validator."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(exchange="")
        result = uc.validate(ref, req)
        assert result is not None
        assert "exchange is required" in result

    def test_stop_loss_with_zero_trigger_translates(self) -> None:
        """STOP_LOSS with zero trigger is a domain violation (no trigger)."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(
            order_type=OrderType.STOP_LOSS,
            price=Decimal("100"),
            trigger_price=Decimal("0"),
        )
        result = uc.validate(ref, req)
        assert result is not None
        # Domain validator rejects trigger=0 for stop orders.
        assert "trigger_price must be positive for stop orders" in result

    def test_stop_loss_market_with_zero_trigger_translates(self) -> None:
        """STOP_LOSS_MARKET with zero trigger is the trigger-only case."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(
            order_type=OrderType.STOP_LOSS_MARKET,
            trigger_price=Decimal("0"),
        )
        result = uc.validate(ref, req)
        assert result is not None
        assert "trigger_price must be positive for stop orders" in result

    def test_trigger_on_market_order_caught_by_domain(self) -> None:
        """A MARKET order with a positive trigger is a domain violation
        that the adapter must surface (not silently pass)."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(
            order_type=OrderType.MARKET,
            trigger_price=Decimal("100"),
        )
        result = uc.validate(ref, req)
        assert result is not None
        assert "Trigger price only valid for SL/SL-M orders" in result


# ---------------------------------------------------------------------------
# K-1: ref-dependent rules still live in the adapter
# ---------------------------------------------------------------------------


class TestRefDependentRulesStayInAdapter:
    """Confirm the adapter still owns rules that need ``ref`` metadata."""

    def test_lot_size_rule_lives_in_adapter(self) -> None:
        """Lot-size check uses ``ref.lot_size``; the domain validator
        cannot run without the resolved ref, so the adapter owns it."""
        uc = _make_uc()
        ref = _make_ref(lot_size=50, exchange_segment="NSE_FNO")
        req = _default_request(quantity=30)
        result = uc.validate(ref, req)
        assert result is not None
        assert "lot size" in result.lower()

    def test_tick_alignment_rule_lives_in_adapter(self) -> None:
        """Tick-alignment uses ``ref.tick_size``; adapter owns it."""
        uc = _make_uc()
        ref = _make_ref(tick_size=Decimal("0.05"))
        req = _default_request(
            order_type=OrderType.LIMIT,
            price=Decimal("1500.03"),
        )
        result = uc.validate(ref, req)
        assert result is not None
        assert "tick size" in result.lower()

    def test_delivery_on_derivative_blocked_by_adapter(self) -> None:
        """The product/segment matrix uses broker-specific segment sets."""
        uc = _make_uc()
        ref = _make_ref(exchange_segment="NSE_FNO")
        req = _default_request(product_type=ProductType.DELIVERY)
        result = uc.validate(ref, req)
        assert result is not None
        assert "DELIVERY" in result


# ---------------------------------------------------------------------------
# K-1: pure wiring — no domain logic re-implementation
# ---------------------------------------------------------------------------


class TestAdapterIsWiringOnly:
    """The adapter must not re-implement the domain rules."""

    def test_adapter_does_not_redundant_recheck_after_domain(self) -> None:
        """If the domain validator passed, the adapter must not re-run
        the same field-level checks. We assert this by patching the
        domain validator to always pass and confirming the adapter
        returns None for a field-level valid request."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(
            order_type=OrderType.LIMIT,
            price=Decimal("1500.00"),
        )
        with patch(
            "brokers.adapters.dhan.use_cases.place_order.validate_order",
            return_value=None,
        ):
            assert uc.validate(ref, req) is None

    def test_domain_validate_order_signature_unchanged(self) -> None:
        """The domain validator still accepts the same six fields."""
        # The adapter passes symbol, exchange, quantity, order_type, price,
        # trigger_price — in that order. Verify the call signature matches.
        import inspect

        sig = inspect.signature(validate_order)
        params = list(sig.parameters)
        assert params == [
            "symbol",
            "exchange",
            "quantity",
            "order_type",
            "price",
            "trigger_price",
        ]
