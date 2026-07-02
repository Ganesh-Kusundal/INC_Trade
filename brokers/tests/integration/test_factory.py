"""Integration tests for broker factory."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers import create_broker
from brokers.adapters.dhan.gateway import DhanGateway
from brokers.adapters.paper.gateway import PaperGateway
from brokers.adapters.upstox.gateway import UpstoxGateway
from brokers.ports import BrokerGateway


class TestCreateBroker:
    def test_create_paper(self):
        gw = create_broker("paper")
        assert isinstance(gw, PaperGateway)
        assert isinstance(gw, BrokerGateway)
        gw.close()

    def test_create_paper_with_cash(self):
        gw = create_broker("paper", initial_cash=500000)
        assert isinstance(gw, PaperGateway)
        bal = gw.portfolio.funds()
        assert bal.available_cash == Decimal("500000")
        gw.close()

    def test_create_dhan(self):
        gw = create_broker("dhan", access_token="tok", client_id="cid")
        assert isinstance(gw, DhanGateway)
        assert isinstance(gw, BrokerGateway)
        gw.close()

    def test_create_upstox(self):
        gw = create_broker("upstox", access_token="tok")
        assert isinstance(gw, UpstoxGateway)
        assert isinstance(gw, BrokerGateway)
        gw.close()

    def test_unknown_broker_raises(self):
        with pytest.raises(ValueError, match="Unknown broker"):
            create_broker("zerodha")

    def test_case_insensitive(self):
        gw = create_broker("Paper")
        assert isinstance(gw, PaperGateway)
        gw.close()

    def test_whitespace_stripped(self):
        gw = create_broker("  paper  ")
        assert isinstance(gw, PaperGateway)
        gw.close()
