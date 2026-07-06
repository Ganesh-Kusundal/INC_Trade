"""Unit tests for ``build_dhan_order_payload`` — the shared Dhan payload builder.

Covers the contract of the single source of truth for Dhan wire-format
order construction. Both ``PlaceOrderUseCase.execute()`` and
``DhanOrders.place_slice_order()`` must route through this builder so the
two call sites cannot drift (A-3).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from inc_trade.domain import OrderRequest
from inc_trade.domain.enums import OrderType, ProductType, Side, Validity

from brokers.adapters.dhan.config import (
    ENDPOINTS,
    ORDER_TYPE_MAP,
    PRODUCT_TYPE_MAP,
    SIDE_MAP,
    VALIDITY_MAP,
)
from brokers.adapters.dhan.identity import DhanInstrumentRef
from brokers.adapters.dhan.orders import DhanOrders
from brokers.adapters.dhan.payload import build_dhan_order_payload
from brokers.adapters.dhan.use_cases.place_order import PlaceOrderUseCase

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DERIVATIVE_SEGMENTS = frozenset({"NSE_FNO", "NSE_MCX", "BSE_FNO"})
_EQUITY_ONLY_PRODUCTS = frozenset({"CNC"})


def _ref(**overrides: object) -> DhanInstrumentRef:
    defaults = dict(
        symbol="RELIANCE",
        security_id="2885",
        exchange_segment="NSE_EQ",
        instrument_type="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
    )
    defaults.update(overrides)
    return DhanInstrumentRef(**defaults)  # type: ignore[arg-type]


def _request(**overrides: object) -> OrderRequest:
    defaults = dict(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        order_type=OrderType.LIMIT,
        price=Decimal("1500.50"),
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
        trigger_price=Decimal("0"),
        correlation_id="payload-corr-001",
    )
    defaults.update(overrides)
    return OrderRequest(**defaults)  # type: ignore[arg-type]


# ===========================================================================
# Shape and field coverage
# ===========================================================================


class TestBuildDhanOrderPayloadShape:
    """The wire dict must contain the Dhan contract keys, no more, no less."""

    EXPECTED_KEYS: frozenset[str] = frozenset(
        {
            "dhanClientId",
            "transactionType",
            "exchangeSegment",
            "securityId",
            "quantity",
            "orderType",
            "productType",
            "validity",
            "price",
            "triggerPrice",
            "correlationId",
        }
    )

    def test_emits_exact_wire_keys(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID-001",
            request=_request(),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert set(payload.keys()) == self.EXPECTED_KEYS

    def test_client_id_is_passed_through(self) -> None:
        payload = build_dhan_order_payload(
            client_id="MY-CLIENT",
            request=_request(),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["dhanClientId"] == "MY-CLIENT"

    def test_complete_request_maps_all_fields(self) -> None:
        ref = _ref(security_id="99999", exchange_segment="BSE_EQ")
        req = _request(
            side=Side.SELL,
            quantity=25,
            order_type=OrderType.STOP_LOSS,
            price=Decimal("250.75"),
            product_type=ProductType.MARGIN,
            validity=Validity.IOC,
            trigger_price=Decimal("248.00"),
            correlation_id="my-corr",
        )
        payload = build_dhan_order_payload(
            client_id="CID",
            request=req,
            ref=ref,
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload == {
            "dhanClientId": "CID",
            "transactionType": 2,  # SELL
            "exchangeSegment": "BSE_EQ",
            "securityId": "99999",
            "quantity": 25,
            "orderType": 3,  # STOP_LOSS
            "productType": "MARGIN",
            "validity": "IOC",
            "price": 250.75,
            "triggerPrice": 248.0,
            "correlationId": "my-corr",
        }

    def test_ref_security_id_str_and_segment_read(self) -> None:
        """Both ``security_id_str()`` and ``exchange_segment`` are read from the ref."""
        ref = _ref(security_id="12345", exchange_segment="NSE_FNO")
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(),
            ref=ref,
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["securityId"] == ref.security_id_str()
        assert payload["securityId"] == "12345"
        assert payload["exchangeSegment"] == ref.exchange_segment
        assert payload["exchangeSegment"] == "NSE_FNO"


# ===========================================================================
# Price/trigger semantics
# ===========================================================================


class TestPriceSemantics:
    def test_price_zero_produces_zero_float(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(price=Decimal("0")),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["price"] == 0.0
        assert isinstance(payload["price"], float)

    def test_price_positive_uses_to_wire_float(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(price=Decimal("1500.50")),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["price"] == 1500.5
        assert isinstance(payload["price"], float)

    def test_trigger_price_zero_produces_zero_float(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(trigger_price=Decimal("0")),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["triggerPrice"] == 0.0
        assert isinstance(payload["triggerPrice"], float)

    def test_trigger_price_positive_uses_to_wire_float(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(trigger_price=Decimal("249.99")),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["triggerPrice"] == 249.99

    def test_price_is_never_negative_or_none(self) -> None:
        """A zero price must not become ``None`` or a negative number."""
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(price=Decimal("0"), trigger_price=Decimal("0")),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["price"] is not None
        assert payload["price"] >= 0
        assert payload["triggerPrice"] is not None
        assert payload["triggerPrice"] >= 0


# ===========================================================================
# Map fallback behaviour
# ===========================================================================


class TestMapFallbacks:
    def test_side_map_falls_back_to_buy(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(side=Side.BUY),
            ref=_ref(),
            side_map={},  # empty — must not KeyError
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["transactionType"] == 1  # BUY fallback

    def test_order_type_map_falls_back_to_market(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(order_type=OrderType.LIMIT),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map={},  # empty — must not KeyError
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["orderType"] == 1  # MARKET fallback

    def test_product_type_map_falls_back_to_intraday(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(product_type=ProductType.MARGIN),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map={},  # empty — must not KeyError
            validity_map=VALIDITY_MAP,
        )
        assert payload["productType"] == "INTRADAY"

    def test_validity_map_falls_back_to_day(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(validity=Validity.IOC),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map={},  # empty — must not KeyError
        )
        assert payload["validity"] == "DAY"

    def test_known_maps_produce_normal_values(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(
                side=Side.SELL,
                order_type=OrderType.STOP_LOSS_MARKET,
                product_type=ProductType.DELIVERY,
                validity=Validity.GTT,
            ),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["transactionType"] == 2  # SELL
        assert payload["orderType"] == 4  # STOP_LOSS_MARKET
        assert payload["productType"] == "MARGIN"  # Dhan maps DELIVERY -> MARGIN
        assert payload["validity"] == "GTT"


# ===========================================================================
# correlation_id behaviour
# ===========================================================================


class TestCorrelationId:
    def test_explicit_correlation_id_is_used(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(correlation_id="explicit-id-123"),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload["correlationId"] == "explicit-id-123"

    def test_missing_correlation_id_generates_uuid(self) -> None:
        payload = build_dhan_order_payload(
            client_id="CID",
            request=_request(correlation_id=""),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        cid = payload["correlationId"]
        assert isinstance(cid, str)
        assert len(cid) > 0
        # Each call with an empty correlation_id produces a fresh UUID
        payload2 = build_dhan_order_payload(
            client_id="CID",
            request=_request(correlation_id=""),
            ref=_ref(),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        assert payload2["correlationId"] != cid


# ===========================================================================
# Determinism
# ===========================================================================


class TestDeterminism:
    def test_same_request_same_correlation_id_yields_identical_payload(self) -> None:
        """Two calls with the same explicit correlation_id must be byte-identical."""
        kwargs = dict(
            client_id="CID",
            request=_request(correlation_id="deterministic-cid"),
            ref=_ref(security_id="2885", exchange_segment="NSE_EQ"),
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        p1 = build_dhan_order_payload(**kwargs)
        p2 = build_dhan_order_payload(**kwargs)
        assert p1 == p2


# ===========================================================================
# Both call sites route through the builder
# ===========================================================================


class TestCallSitesUseBuilder:
    """Both call sites — use case and slice — must use the same builder."""

    def test_place_order_use_case_calls_builder(self) -> None:
        client = MagicMock()
        client.client_id = "CID"
        client.post.return_value = {"orderId": "OID", "orderStatus": "OPEN"}
        resolver = MagicMock()
        resolver.resolve.return_value = _ref(security_id="42", exchange_segment="NSE_EQ")

        idempotency = MagicMock()
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        uc = PlaceOrderUseCase(
            client,
            resolver,
            endpoints={"orders": "/v2/orders"},
            idempotency=idempotency,
            derivative_segments=_DERIVATIVE_SEGMENTS,
            equity_only_products=_EQUITY_ONLY_PRODUCTS,
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )

        with patch(
            "brokers.adapters.dhan.use_cases.place_order.build_dhan_order_payload",
            wraps=build_dhan_order_payload,
        ) as spy:
            uc.execute(_request(correlation_id="uc-corr"))

        spy.assert_called_once()
        client.post.assert_called_once()
        posted = client.post.call_args.kwargs["json"]
        assert posted["dhanClientId"] == "CID"
        assert posted["exchangeSegment"] == "NSE_EQ"
        assert posted["securityId"] == "42"
        assert posted["correlationId"] == "uc-corr"

    def test_place_slice_order_calls_builder(self) -> None:
        client = MagicMock()
        client.client_id = "CID"
        client.post.return_value = {"orderId": "SOID", "orderStatus": "OPEN"}
        resolver = MagicMock()
        resolver.resolve.return_value = _ref(security_id="77", exchange_segment="BSE_EQ")

        orders = DhanOrders(client, resolver)

        with patch(
            "brokers.adapters.dhan.orders.build_dhan_order_payload",
            wraps=build_dhan_order_payload,
        ) as spy:
            resp = orders.place_slice_order(
                "RELIANCE",
                "BSE",
                Side.BUY,
                10,
                order_type=OrderType.MARKET,
                correlation_id="slice-corr",
            )

        spy.assert_called_once()
        assert resp.success
        client.post.assert_called_once()
        endpoint = client.post.call_args.args[0]
        assert endpoint == ENDPOINTS["slice_order"]
        posted = client.post.call_args.kwargs["json"]
        assert posted["dhanClientId"] == "CID"
        assert posted["exchangeSegment"] == "BSE_EQ"
        assert posted["securityId"] == "77"
        assert posted["correlationId"] == "slice-corr"

    def test_both_call_sites_produce_same_payload_shape(self) -> None:
        """The two call sites must emit byte-identical dict shapes for the
        same OrderRequest + ref."""
        client = MagicMock()
        client.client_id = "CID"
        client.post.return_value = {"orderId": "X", "orderStatus": "OPEN"}
        resolver = MagicMock()
        resolver.resolve.return_value = _ref(security_id="99", exchange_segment="NSE_EQ")

        idempotency = MagicMock()
        idempotency.get.return_value = None
        idempotency.lock.return_value.__enter__ = MagicMock()
        idempotency.lock.return_value.__exit__ = MagicMock(return_value=False)

        uc = PlaceOrderUseCase(
            client,
            resolver,
            endpoints={"orders": "/v2/orders"},
            idempotency=idempotency,
            derivative_segments=_DERIVATIVE_SEGMENTS,
            equity_only_products=_EQUITY_ONLY_PRODUCTS,
            side_map=SIDE_MAP,
            order_type_map=ORDER_TYPE_MAP,
            product_type_map=PRODUCT_TYPE_MAP,
            validity_map=VALIDITY_MAP,
        )
        orders = DhanOrders(client, resolver)

        # Build a market-order request that both call sites will accept
        # (LIMIT requires price > 0, but here we just want parity).
        shared_req = _request(
            correlation_id="shared",
            order_type=OrderType.MARKET,
            price=Decimal("0"),
            trigger_price=Decimal("0"),
        )
        uc.execute(shared_req)
        uc_payload = client.post.call_args.kwargs["json"]

        orders.place_slice_order(
            "RELIANCE",
            "NSE",
            Side.BUY,
            10,
            order_type=OrderType.MARKET,
            price=Decimal("0"),
            trigger_price=Decimal("0"),
            correlation_id="shared",
        )
        slice_payload = client.post.call_args.kwargs["json"]

        # Both sites build the same dict for the same (request, ref).
        assert uc_payload == slice_payload
