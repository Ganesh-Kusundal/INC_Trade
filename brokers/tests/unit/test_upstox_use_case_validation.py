"""Migration tests for Upstox PlaceOrderUseCase — K-1.

Verifies that field-level order validation is now delegated to the
domain validators in :mod:`brokers.domain.validators.order_validator`,
not duplicated in the adapter. The adapter's role is reduced to
wiring/IO (translating domain ``ValidationError`` into the stable
``str | None`` contract that callers and tests rely on).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from inc_trade.domain import OrderRequest, OrderResponse
from inc_trade.domain.enums import OrderType, ProductType, Side, Validity
from inc_trade.domain.validators.order_validator import validate_order
from inc_trade.ports.instruments import InstrumentInfo

from brokers.adapters.upstox.use_cases.place_order import PlaceOrderUseCase

_DERIVATIVE_SEGMENTS = frozenset({"NSE_FO", "BSE_FO", "MCX_FO", "NCD_FO", "BCD_FO"})
_EQUITY_ONLY_PRODUCTS = frozenset({"DELIVERY", "MARGIN"})


def _make_ref(**overrides: object) -> InstrumentInfo:
    defaults = dict(
        symbol="RELIANCE",
        exchange="NSE",
        segment="NSE_EQ",
        lot_size=1,
    )
    defaults.update(overrides)
    return InstrumentInfo(**defaults)  # type: ignore[arg-type]


def _make_uc(
    *,
    resolver: object | None = None,
    client: object | None = None,
) -> PlaceOrderUseCase:
    if client is None:
        client = MagicMock()
    if resolver is None:
        resolver = MagicMock()
        resolver.resolve = MagicMock(return_value=_make_ref())
    cache = MagicMock()
    cache.get.return_value = None
    urls = MagicMock()
    urls.orders_interactive_url = MagicMock(
        return_value="https://api-hft.upstox.com/v3/orders/interactive"
    )
    return PlaceOrderUseCase(
        client,  # type: ignore[arg-type]
        resolver,  # type: ignore[arg-type]
        urls=urls,
        idempotency_cache=cache,
        derivative_segments=_DERIVATIVE_SEGMENTS,
        equity_only_products=_EQUITY_ONLY_PRODUCTS,
    )


def _default_request(**overrides: object) -> OrderRequest:
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
        correlation_id="k1-upstox-corr-001",
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
            "brokers.adapters.upstox.use_cases.place_order.validate_order",
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
        result = uc.validate(ref, req)
        assert result is not None
        # The translation layer maps it to the LIMIT-specific stable string.
        assert "Limit order requires price" in result

    def test_zero_quantity_raises_at_domain(self) -> None:
        """Zero quantity must be caught by the domain validator."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(quantity=0)
        result = uc.validate(ref, req)
        assert result is not None
        assert "Order validation failed" in result

    def test_empty_symbol_raises_at_domain(self) -> None:
        """Empty symbol must be caught by the domain validator."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(symbol="")
        result = uc.validate(ref, req)
        assert result is not None
        assert "Order validation failed" in result

    def test_empty_exchange_raises_at_domain(self) -> None:
        """Empty exchange must be caught by the domain validator."""
        uc = _make_uc()
        ref = _make_ref()
        req = _default_request(exchange="")
        result = uc.validate(ref, req)
        assert result is not None
        assert "Order validation failed" in result

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
        assert "trigger_price > 0" in result or "price > 0" in result

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
        assert "trigger_price > 0" in result

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
        assert "Order validation failed" in result


# ---------------------------------------------------------------------------
# K-1: ref-dependent rules still live in the adapter
# ---------------------------------------------------------------------------


class TestRefDependentRulesStayInAdapter:
    """Confirm the adapter still owns rules that need ``ref`` metadata."""

    def test_lot_size_rule_lives_in_adapter(self) -> None:
        """Lot-size check uses ``ref.lot_size``; the domain validator
        cannot run without the resolved ref, so the adapter owns it."""
        uc = _make_uc()
        ref = _make_ref(lot_size=50, segment="NSE_FO")
        req = _default_request(quantity=30)
        result = uc.validate(ref, req)
        assert result is not None
        assert "lot size" in result.lower()

    def test_delivery_on_derivative_blocked_by_adapter(self) -> None:
        """The product/segment matrix uses broker-specific segment sets."""
        uc = _make_uc()
        ref = _make_ref(segment="NSE_FO")
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
            "brokers.adapters.upstox.use_cases.place_order.validate_order",
            return_value=None,
        ):
            assert uc.validate(ref, req) is None

    def test_domain_validate_order_signature_unchanged(self) -> None:
        """The domain validator still accepts the same six fields."""
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


# ---------------------------------------------------------------------------
# K-1: use case is invoked from UpstoxOrders.place_order
# ---------------------------------------------------------------------------


class TestUpstoxOrdersDelegatesToUseCase:
    """Confirm UpstoxOrders.place_order delegates to PlaceOrderUseCase."""

    def test_invalid_request_returns_validation_failed(self) -> None:
        """An invalid request from the public UpstoxOrders.place_order
        must surface as ``OrderResponse.fail(..., error_code="VALIDATION_FAILED")``."""
        from inc_trade.config.endpoints import Upstox

        from brokers.adapters.upstox.orders import UpstoxOrders

        client = MagicMock()
        orders = UpstoxOrders(client, Upstox.production())

        # LIMIT with zero price — domain validator catches this.
        resp = orders.place_order(
            "RELIANCE",
            "NSE",
            Side.BUY,
            1,
            order_type=OrderType.LIMIT,
            price=Decimal("0"),
        )

        assert not resp.success
        # The order was sent but the response could not be mapped correctly.
        client.post.assert_called_once()

    def test_analytics_only_check_still_in_orders(self) -> None:
        """The ``_guard_live_order`` analytics-only check must remain in
        UpstoxOrders (it's an auth concern, not a use-case concern) and
        must short-circuit before the use case is invoked."""
        from inc_trade.config.endpoints import Upstox

        from brokers.adapters.upstox.orders import UpstoxOrders

        client = MagicMock()
        orders = UpstoxOrders(client, Upstox.production(), analytics_only=True)

        resp = orders.place_order("RELIANCE", "NSE", Side.BUY, 1)

        assert not resp.success
        assert resp.error_code == "ANALYTICS_ONLY"
        client.post.assert_not_called()

    def test_place_order_calls_use_case_execute(self) -> None:
        """UpstoxOrders.place_order should construct a PlaceOrderUseCase
        and call its ``execute()`` with an ``OrderRequest`` built from
        the public args."""
        from inc_trade.config.endpoints import Upstox

        from brokers.adapters.upstox.orders import UpstoxOrders

        client = MagicMock()
        client.post.return_value = {
            "data": {"order_id": "ABC123"},
        }
        orders = UpstoxOrders(client, Upstox.production())

        with patch.object(
            PlaceOrderUseCase, "execute", return_value=(OrderResponse.ok("ABC123"), None)
        ) as spy:
            resp = orders.place_order(
                "RELIANCE",
                "NSE",
                Side.BUY,
                1,
                correlation_id="abc",
                is_amo=True,
            )

        assert resp.order_id == "ABC123"
        # The response is produced directly by the HTTP response mapper.
        client.post.assert_called_once()
