"""Tests for PaperProvider."""
from __future__ import annotations
from decimal import Decimal
import pytest
from brokers.domain.enums import Exchange, OrderType, ProductType, Side
from brokers.domain.instrument import Instrument
from brokers.domain.requests import OrderRequest
from brokers.paper.paper_provider import PaperProvider

def _make_instrument(symbol="RELIANCE", exchange=Exchange.NSE, provider=None):
    return Instrument(symbol=symbol, exchange=exchange, provider=provider)

def _make_order_request(instrument, quantity=10, side=Side.BUY):
    return OrderRequest(
        symbol=instrument.symbol, exchange=instrument.exchange,
        side=side, quantity=quantity, order_type=OrderType.MARKET,
        product_type=ProductType.CNC, instrument=instrument,
    )

class TestPaperLifecycle:
    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        p = PaperProvider()
        assert p.is_connected is False
        await p.connect()
        assert p.is_connected is True
        await p.disconnect()
        assert p.is_connected is False

    def test_broker_id(self):
        assert PaperProvider().broker_id == "paper"

class TestPaperMarketData:
    @pytest.mark.asyncio
    async def test_get_quote_default(self):
        p = PaperProvider()
        inst = _make_instrument("RELIANCE", provider=p)
        q = await p.get_quote(inst)
        assert q.ltp == Decimal("2550.00")

    @pytest.mark.asyncio
    async def test_get_ltp_default(self):
        p = PaperProvider()
        inst = _make_instrument("INFY", provider=p)
        assert await p.get_ltp(inst) == Decimal("1500.00")

    @pytest.mark.asyncio
    async def test_set_price(self):
        p = PaperProvider()
        inst = _make_instrument("RELIANCE", provider=p)
        p.set_price("RELIANCE", Exchange.NSE, Decimal("3000"))
        assert await p.get_ltp(inst) == Decimal("3000")

    @pytest.mark.asyncio
    async def test_unknown_raises(self):
        p = PaperProvider()
        inst = _make_instrument("UNKNOWN", provider=p)
        with pytest.raises(ValueError, match="No price"):
            await p.get_quote(inst)

    @pytest.mark.asyncio
    async def test_depth(self):
        p = PaperProvider()
        inst = _make_instrument("RELIANCE", provider=p)
        depth = await p.get_depth(inst)
        assert len(depth.bids) == 5
        assert len(depth.asks) == 5

class TestPaperExecution:
    @pytest.mark.asyncio
    async def test_place_buy(self):
        p = PaperProvider()
        inst = _make_instrument("RELIANCE", provider=p)
        req = _make_order_request(inst, 10, Side.BUY)
        resp = await p.place_order(req)
        assert resp.order_id is not None

    @pytest.mark.asyncio
    async def test_place_sell(self):
        p = PaperProvider()
        inst = _make_instrument("RELIANCE", provider=p)
        req = _make_order_request(inst, 5, Side.SELL)
        resp = await p.place_order(req)
        assert resp.order_id is not None

    @pytest.mark.asyncio
    async def test_cancel(self):
        p = PaperProvider()
        inst = _make_instrument("RELIANCE", provider=p)
        req = _make_order_request(inst)
        resp = await p.place_order(req)
        cancel = await p.cancel_order(resp.order_id)
        assert cancel is not None

    @pytest.mark.asyncio
    async def test_get_orders(self):
        p = PaperProvider()
        inst = _make_instrument("RELIANCE", provider=p)
        await p.place_order(_make_order_request(inst))
        orders = await p.get_orders()
        assert len(orders) >= 1

class TestPaperPortfolio:
    @pytest.mark.asyncio
    async def test_initial_balance(self):
        p = PaperProvider(initial_balance=Decimal("500000"))
        b = await p.get_balance()
        assert b.available_balance == Decimal("500000")

    @pytest.mark.asyncio
    async def test_default_balance(self):
        p = PaperProvider()
        b = await p.get_balance()
        assert b.available_balance == Decimal("100000")

    @pytest.mark.asyncio
    async def test_empty_positions(self):
        assert await PaperProvider().get_positions() == []

    @pytest.mark.asyncio
    async def test_empty_holdings(self):
        assert await PaperProvider().get_holdings() == []

    @pytest.mark.asyncio
    async def test_empty_trades(self):
        assert await PaperProvider().get_trades() == []
