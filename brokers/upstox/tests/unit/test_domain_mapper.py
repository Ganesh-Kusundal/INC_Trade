from __future__ import annotations

from decimal import Decimal

from brokers.common.dtos import BrokerOrderPayload
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from domain import (
    FundLimits,
    Holding,
    MarketDepth,
    OptionContract,
    OrderRequest,
    OrderResponse,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Side,
    Trade,
    Validity,
)


def test_status_normalisation():
    cases = {
        "put order req received": OrderStatus.OPEN,
        "open": OrderStatus.OPEN,
        "open pending": OrderStatus.OPEN,
        "complete": OrderStatus.FILLED,
        "filled": OrderStatus.FILLED,
        "cancelled": OrderStatus.CANCELLED,
        "rejected": OrderStatus.REJECTED,
        "partially filled": OrderStatus.PARTIALLY_FILLED,
        "trigger pending": OrderStatus.OPEN,
        "expired": OrderStatus.EXPIRED,
        "after market order req received": OrderStatus.OPEN,
    }
    for raw, expected in cases.items():
        assert UpstoxDomainMapper.normalize_status(raw) is expected, raw


def test_product_wire_round_trip():
    for p in (ProductType.INTRADAY, ProductType.CNC, ProductType.MARGIN, ProductType.MTF):
        wire = UpstoxDomainMapper.product_to_wire(p)
        assert UpstoxDomainMapper.product_from_wire(wire) is p


def test_order_type_wire_round_trip():
    for t in (OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LOSS, OrderType.STOP_LOSS_MARKET):
        wire = UpstoxDomainMapper.order_type_to_wire(t)
        assert UpstoxDomainMapper.order_type_from_wire(wire) is t


def test_validity_wire_round_trip():
    for v in (Validity.DAY, Validity.IOC):
        wire = UpstoxDomainMapper.validity_to_wire(v)
        assert UpstoxDomainMapper.validity_from_wire(wire) is v


def test_txn_wire_round_trip():
    for t in (Side.BUY, Side.SELL):
        assert UpstoxDomainMapper.txn_from_wire(UpstoxDomainMapper.txn_to_wire(t)) is t


def test_to_place_payload_basic():
    from domain import OrderType as EnumsOrderType
    from domain import ProductType as EnumsProductType
    from domain import Side
    from domain import Validity as EnumsValidity

    req = OrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type=Side.BUY,
        quantity=10,
        price=Decimal("2500.50"),
        order_type=EnumsOrderType.LIMIT,
        product_type=EnumsProductType.CNC,
        validity=EnumsValidity.DAY,
        correlation_id="corr-1",
    )
    payload = UpstoxDomainMapper.to_place_payload(req, "NSE_EQ|INE001A01023")
    assert payload["instrument_token"] == "NSE_EQ|INE001A01023"
    assert payload["transaction_type"] == "BUY"
    assert payload["quantity"] == 10
    assert payload["price"] == 2500.5
    assert payload["order_type"] == "LIMIT"
    assert payload["product"] == "D"
    assert payload["validity"] == "DAY"
    assert payload["tag"] == "corr-1"


def test_to_place_payload_with_slice():
    from domain import OrderType as EnumsOrderType
    from domain import ProductType as EnumsProductType
    from domain import Side
    from domain import Validity as EnumsValidity

    req = OrderRequest(
        symbol="TCS",
        transaction_type=Side.SELL,
        quantity=1,
        price=Decimal("3500"),
        order_type=EnumsOrderType.MARKET,
        product_type=EnumsProductType.INTRADAY,
        validity=EnumsValidity.IOC,
        slice=True,
    )
    payload = UpstoxDomainMapper.to_place_payload(req, "NSE_EQ|INE001A01023")
    assert payload["slice"] is True
    assert payload["price"] == 0
    assert payload["validity"] == "IOC"
    assert payload["order_type"] == "MARKET"


def test_to_place_payload_reads_provider_metadata():
    req = BrokerOrderPayload(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type=Side.BUY,
        quantity=10,
        price=Decimal("2500.50"),
        order_type=OrderType.LIMIT,
        product_type=ProductType.CNC,
        validity=Validity.DAY,
        provider_metadata={"is_amo": True, "market_protection": 3},
    )

    payload = UpstoxDomainMapper.to_place_payload(req, "NSE_EQ|INE001A01023")

    assert payload["is_amo"] is True
    assert payload["market_protection"] == 3


def test_to_modify_payload():
    payload = UpstoxDomainMapper.to_modify_payload(
        order_id="ORD1",
        instrument_key="NSE_EQ|INE001A01023",
        quantity=5,
        price=Decimal("2600"),
        order_type=OrderType.LIMIT,
    )
    assert payload["order_id"] == "ORD1"
    assert payload["instrument_token"] == "NSE_EQ|INE001A01023"
    assert payload["quantity"] == 5
    assert payload["price"] == 2600.0
    assert payload["order_type"] == "LIMIT"


def test_to_order_response_success():
    payload = {"status": "success", "data": {"order_id": "ORD123"}}
    resp = UpstoxDomainMapper.to_order_response(payload)
    assert isinstance(resp, OrderResponse)
    assert resp.success is True
    assert resp.order_id == "ORD123"


def test_to_order_response_failure_with_errors():
    payload = {"status": "error", "errors": [{"message": "bad price"}]}
    resp = UpstoxDomainMapper.to_order_response(payload)
    assert resp.success is False
    assert "bad price" in resp.message


def test_to_quote():
    payload = {
        "data": {
            "symbol": "RELIANCE",
            "exchange_segment": "NSE_EQ",
            "last_price": 2500.5,
            "ohlc": {"open": 2490, "high": 2510, "low": 2480, "close": 2495},
            "volume": 12345,
            "depth": {
                "buy": [{"price": 2500, "quantity": 100}],
                "sell": [{"price": 2501, "quantity": 200}],
            },
        }
    }
    q = UpstoxDomainMapper.to_quote(payload)
    assert isinstance(q, Quote)
    assert q.symbol == "RELIANCE"
    assert q.ltp == Decimal("2500.5")
    assert q.bid == Decimal("2500")
    assert q.ask == Decimal("2501")
    assert q.volume == 12345


def test_to_position():
    payload = {
        "trading_symbol": "RELIANCE",
        "exchange_segment": "NSE_EQ",
        "net_quantity": 10,
        "buy_quantity": 10,
        "sell_quantity": 0,
        "buy_average_price": 2500.0,
        "sell_average_price": 0,
        "last_price": 2510,
        "unrealised": 100.0,
        "realised": 0,
        "product": "D",
    }
    p = UpstoxDomainMapper.to_position(payload)
    assert isinstance(p, Position)
    assert p.symbol == "RELIANCE"
    assert p.quantity == 10
    assert p.avg_price == Decimal("2500")
    assert p.unrealized_pnl == Decimal("100")
    assert p.ltp == Decimal("2510")


def test_to_holding():
    payload = {
        "trading_symbol": "RELIANCE",
        "exchange_segment": "NSE_EQ",
        "quantity": 100,
        "average_price": 2400.0,
        "last_price": 2500.0,
        "pnl": 10000,
    }
    h = UpstoxDomainMapper.to_holding(payload)
    assert isinstance(h, Holding)
    assert h.quantity == 100
    assert h.avg_price == Decimal("2400")
    assert h.pnl == Decimal("10000")


def test_to_trade():
    payload = {
        "trade_id": "TRD1",
        "order_id": "ORD1",
        "trading_symbol": "RELIANCE",
        "exchange_segment": "NSE_EQ",
        "transaction_type": "BUY",
        "quantity": 5,
        "price": 2500.0,
        "product": "D",
    }
    t = UpstoxDomainMapper.to_trade(payload)
    assert isinstance(t, Trade)
    assert t.trade_id == "TRD1"
    assert t.quantity == 5
    assert t.price == Decimal("2500")
    assert t.side is Side.BUY


def test_to_fund_limits():
    payload = {
        "data": {
            "equity": {
                "available_margin": 50000.0,
                "used_margin": 10000.0,
                "net_margin": 60000.0,
            },
            "m2m_realised": 100.0,
            "m2m_unrealised": 50.0,
        }
    }
    f = UpstoxDomainMapper.to_fund_limits(payload)
    assert isinstance(f, FundLimits)
    assert f.available_balance == Decimal("50000")
    assert f.used_margin == Decimal("10000")
    assert f.total_margin == Decimal("60000")


def test_to_historical_candles_from_array():
    payload = {
        "data": {
            "candles": [
                ["2026-06-01T00:00:00+00:00", 2490, 2510, 2480, 2505, 100000],
                ["2026-06-02T00:00:00+00:00", 2505, 2520, 2490, 2515, 120000],
            ]
        }
    }
    cs = UpstoxDomainMapper.to_historical_candles(payload)
    assert len(cs) == 2
    assert cs[0].open == Decimal("2490")
    assert cs[0].close == Decimal("2505")
    assert cs[0].volume == 100000
    assert cs[1].volume == 120000


def test_to_historical_candles_from_dicts():
    payload = {
        "candles": [
            {
                "timestamp": "2026-06-01T00:00:00+00:00",
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "volume": 100,
            },
        ]
    }
    cs = UpstoxDomainMapper.to_historical_candles(payload)
    assert len(cs) == 1
    assert cs[0].open == Decimal("1")


def test_to_market_depth():
    payload = {
        "data": {
            "symbol": "RELIANCE",
            "exchange_segment": "NSE_EQ",
            "depth": {
                "buy": [{"price": 2500, "quantity": 100, "orders": 5}],
                "sell": [{"price": 2501, "quantity": 200, "orders": 7}],
            },
        }
    }
    d = UpstoxDomainMapper.to_market_depth(payload)
    assert isinstance(d, MarketDepth)
    assert len(d.bids) == 1
    assert d.bids[0].price == Decimal("2500")
    assert d.bids[0].orders == 5
    assert d.asks[0].price == Decimal("2501")


def test_to_order():
    payload = {
        "order_id": "ORD1",
        "tag": "corr-1",
        "trading_symbol": "RELIANCE",
        "exchange_segment": "NSE_EQ",
        "transaction_type": "BUY",
        "quantity": 10,
        "price": 2500.0,
        "order_type": "LIMIT",
        "product": "D",
        "validity": "DAY",
        "status": "open",
        "filled_quantity": 0,
        "average_price": 0,
    }
    o = UpstoxDomainMapper.to_order(payload)
    assert o.order_id == "ORD1"
    assert o.correlation_id == "corr-1"
    assert o.status is OrderStatus.OPEN
    assert o.filled_quantity == 0


def test_to_option_contract_minimal():
    payload = {
        "trading_symbol": "RELIANCE26JUN2500CE",
        "strike_price": 2500,
        "expiry": "2026-06-26",
        "exchange_segment": "NSE_FO",
        "lot_size": 250,
    }
    oc = UpstoxDomainMapper.to_option_contract(payload)
    assert isinstance(oc, OptionContract)
    assert oc.strike == Decimal("2500")
    assert oc.expiry == "2026-06-26"
    assert oc.lot_size == 250
