"""Unit tests for PlaceOrderUseCase — validate, resolve, idempotency, risk, POST."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.identity import DhanInstrumentRef
from brokers.adapters.dhan.use_cases.place_order import PlaceOrderUseCase
from brokers.domain import OrderRequest, OrderResponse
from brokers.domain.enums import OrderType, ProductType, Side, Validity
from brokers.domain.exceptions import InstrumentNotFoundError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DERIVATIVE_SEGMENTS = frozenset({"NSE_FNO", "NSE_MCX", "BSE_FNO"})
_EQUITY_ONLY_PRODUCTS = frozenset({"CNC"})
_SIDE_MAP = {"BUY": 1, "SELL": 2}
_ORDER_TYPE_MAP = {"MARKET": 1, "LIMIT": 2, "STOP_LOSS": 3, "STOP_LOSS_MARKET": 4}
_PRODUCT_TYPE_MAP = {"INTRADAY": "INTRADAY", "MARGIN": "MARGIN", "DELIVERY": "CNC"}
_VALIDITY_MAP = {"DAY": "DAY", "IOC": "IOC", "GTT": "GTT"}


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


def _make_uc(
    *,
    risk_manager: object | None = None,
) -> tuple[PlaceOrderUseCase, MagicMock, MagicMock, MagicMock]:
    client = MagicMock()
    client.client_id = "TEST_123"
    resolver = MagicMock()
    idempotency = MagicMock()
    uc = PlaceOrderUseCase(
        client,
        resolver,
        idempotency=idempotency,
        risk_manager=risk_manager,
        derivative_segments=_DERIVATIVE_SEGMENTS,
        equity_only_products=_EQUITY_ONLY_PRODUCTS,
        side_map=_SIDE_MAP,
        order_type_map=_ORDER_TYPE_MAP,
        product_type_map=_PRODUCT_TYPE_MAP,
        validity_map=_VALIDITY_MAP,
    )
    return uc, client, resolver, idempotency


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
        correlation_id="test-corr-001",
    )
    defaults.update(overrides)
    return OrderRequest(**defaults)  # type: ignore[arg-type]


# ===========================================================================
# OrderRequest tests
# ===========================================================================


class TestOrderRequest:
    def test_frozen_dataclass(self) -> None:
        req = _default_request()
        with pytest.raises(FrozenInstanceError):
            req.symbol = "TCS"  # type: ignore[misc]

    def test_default_values(self) -> None:
        req = OrderRequest(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=1,
        )
        assert req.order_type == OrderType.MARKET
        assert req.price == Decimal("0")
        assert req.product_type == ProductType.INTRADAY
        assert req.validity == Validity.DAY
        assert req.trigger_price == Decimal("0")
        assert req.correlation_id == ""


# ===========================================================================
# PlaceOrderUseCase.execute tests
# ===========================================================================


class TestExecute:
    def test_successful_order(self) -> None:
        uc, client, resolver, idempotency = _make_uc()
        ref = _make_ref()
        resolver.resolve.return_value = ref
        client.post.return_value = {
            "orderId": "99999",
            "orderStatus": "PENDING",
        }
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        result, placed = uc.execute(_default_request())

        assert result.success
        assert result.order_id == "99999"
        assert placed is not None
        assert placed.order_id == "99999"
        assert placed.symbol == "RELIANCE"
        resolver.resolve.assert_called_once()
        client.post.assert_called_once()

    def test_idempotency_cache_hit(self) -> None:
        uc, _, resolver, idempotency = _make_uc()
        cached = OrderResponse.ok("11111")
        idempotency.get.return_value = cached
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        result, placed = uc.execute(_default_request())

        assert result is cached
        assert placed is None
        resolver.resolve.assert_not_called()

    def test_instrument_not_found(self) -> None:
        uc, _, resolver, idempotency = _make_uc()
        resolver.resolve.side_effect = InstrumentNotFoundError("RELIANCE not found")
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        result, placed = uc.execute(_default_request())

        assert not result.success
        assert result.error_code == "INSTRUMENT_NOT_FOUND"
        assert "RELIANCE not found" in result.message
        assert placed is None

    def test_validation_failure_limit_no_price(self) -> None:
        uc, _, resolver, idempotency = _make_uc()
        resolver.resolve.return_value = _make_ref()
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        req = _default_request(order_type=OrderType.LIMIT, price=Decimal("0"))
        result, placed = uc.execute(req)

        assert not result.success
        assert result.error_code == "VALIDATION_FAILED"
        assert "Limit order requires price" in result.message
        assert placed is None

    def test_validation_failure_sl_requires_trigger(self) -> None:
        uc, _, resolver, idempotency = _make_uc()
        resolver.resolve.return_value = _make_ref()
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        req = _default_request(
            order_type=OrderType.STOP_LOSS_MARKET,
            trigger_price=Decimal("0"),
        )
        result, placed = uc.execute(req)

        assert not result.success
        assert result.error_code == "VALIDATION_FAILED"
        assert "Stop-Loss Market order requires trigger_price" in result.message

    def test_risk_check_rejection(self) -> None:
        risk_manager = MagicMock()
        risk_result = MagicMock()
        risk_result.allowed = False
        risk_result.reason = "Exposure limit"
        risk_manager.check_order.return_value = risk_result

        uc, _, resolver, idempotency = _make_uc(risk_manager=risk_manager)
        resolver.resolve.return_value = _make_ref()
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        result, placed = uc.execute(_default_request())

        assert not result.success
        assert "Risk check failed" in result.message
        assert "Exposure limit" in result.message
        assert placed is None

    def test_http_failure(self) -> None:
        uc, client, resolver, idempotency = _make_uc()
        resolver.resolve.return_value = _make_ref()
        client.post.side_effect = ConnectionError("timeout")
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ConnectionError):
            uc.execute(_default_request())

    def test_response_mapping_success(self) -> None:
        uc, client, resolver, idempotency = _make_uc()
        resolver.resolve.return_value = _make_ref()
        client.post.return_value = {
            "orderId": "ABC123",
            "orderStatus": "OPEN",
        }
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        result, placed = uc.execute(_default_request())

        assert result.success
        assert result.order_id == "ABC123"
        assert placed is not None

    def test_response_mapping_rejected(self) -> None:
        uc, client, resolver, idempotency = _make_uc()
        resolver.resolve.return_value = _make_ref()
        client.post.return_value = {
            "orderId": "",
            "orderStatus": "REJECTED",
            "rejectReason": "Margin insufficient",
            "errorCode": "MARGIN_ERR",
        }
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        result, placed = uc.execute(_default_request())

        assert not result.success
        assert result.order_id == ""
        assert placed is None

    def test_idempotency_put_on_success(self) -> None:
        uc, client, resolver, idempotency = _make_uc()
        resolver.resolve.return_value = _make_ref()
        client.post.return_value = {"orderId": "55555", "orderStatus": "PENDING"}
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        result, _ = uc.execute(_default_request())

        assert result.success
        idempotency.put.assert_called_once()


# ===========================================================================
# PlaceOrderUseCase.validate tests
# ===========================================================================


class TestValidate:
    def _uc(self) -> PlaceOrderUseCase:
        uc, _, _, _ = _make_uc()
        return uc

    def _ref(self, **kw: object) -> DhanInstrumentRef:
        return _make_ref(**kw)

    def test_valid_payload(self) -> None:
        uc = self._uc()
        req = _default_request(
            order_type=OrderType.LIMIT,
            price=Decimal("1500.00"),
        )
        assert uc.validate(self._ref(), req) is None

    def test_invariant_invalid_security_id(self) -> None:
        from brokers.adapters.dhan.config import DHAN_SEGMENTS

        uc, client, resolver, idempotency = _make_uc()
        ref = DhanInstrumentRef(
            symbol="RELIANCE",
            security_id="12345",
            exchange_segment="NSE_EQ",
        )
        object.__setattr__(ref, "security_id", "abc")
        resolver.resolve.return_value = ref
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="securityId"):
            uc.execute(_default_request())

    def test_invariant_invalid_exchange_segment(self) -> None:
        from brokers.adapters.dhan.config import DHAN_SEGMENTS

        uc, client, resolver, idempotency = _make_uc()
        ref = DhanInstrumentRef(
            symbol="RELIANCE",
            security_id="12345",
            exchange_segment="NSE_EQ",
        )
        object.__setattr__(ref, "exchange_segment", "INVALID_SEG")
        resolver.resolve.return_value = ref
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="exchangeSegment"):
            uc.execute(_default_request())

    def test_invalid_quantity_not_multiple_of_lot(self) -> None:
        uc = self._uc()
        ref = self._ref(lot_size=50, exchange_segment="NSE_FNO")
        req = _default_request(quantity=30)
        error = uc.validate(ref, req)
        assert error is not None
        assert "lot size" in error.lower()

    def test_delivery_not_valid_for_derivatives(self) -> None:
        uc = self._uc()
        ref = self._ref(exchange_segment="NSE_FNO")
        req = _default_request(product_type=ProductType.DELIVERY)
        error = uc.validate(ref, req)
        assert error is not None
        assert "DELIVERY" in error

    def test_limit_order_requires_price(self) -> None:
        uc = self._uc()
        ref = self._ref()
        req = _default_request(order_type=OrderType.LIMIT, price=Decimal("0"))
        error = uc.validate(ref, req)
        assert error is not None
        assert "price > 0" in error

    def test_sl_requires_price_and_trigger(self) -> None:
        uc = self._uc()
        ref = self._ref()
        req = _default_request(
            order_type=OrderType.STOP_LOSS,
            price=Decimal("0"),
            trigger_price=Decimal("0"),
        )
        error = uc.validate(ref, req)
        assert error is not None
        assert "price > 0" in error

    def test_sl_market_requires_trigger(self) -> None:
        uc = self._uc()
        ref = self._ref()
        req = _default_request(
            order_type=OrderType.STOP_LOSS_MARKET,
            trigger_price=Decimal("0"),
        )
        error = uc.validate(ref, req)
        assert error is not None
        assert "trigger_price > 0" in error

    def test_tick_alignment_failure(self) -> None:
        uc = self._uc()
        ref = self._ref(tick_size=Decimal("0.05"))
        req = _default_request(
            order_type=OrderType.LIMIT,
            price=Decimal("1500.03"),
        )
        error = uc.validate(ref, req)
        assert error is not None
        assert "tick size" in error.lower()
