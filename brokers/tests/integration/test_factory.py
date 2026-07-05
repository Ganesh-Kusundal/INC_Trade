"""Integration tests for broker factory."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers import create_broker
from inc_trade.services.broker_facade import BrokerFacade


class TestCreateBroker:
    def test_create_paper(self):
        facade = create_broker("paper")
        assert isinstance(facade, BrokerFacade)
        facade.close()

    def test_create_paper_with_cash(self):
        facade = create_broker("paper", initial_cash=500000)
        assert isinstance(facade, BrokerFacade)
        bal = facade.get_balance()
        assert bal.available_cash == Decimal("500000")
        facade.close()

    def test_create_dhan(self):
        facade = create_broker("dhan", access_token="tok", client_id="cid")
        assert isinstance(facade, BrokerFacade)
        facade.close()

    def test_create_upstox(self):
        facade = create_broker("upstox", access_token="tok")
        assert isinstance(facade, BrokerFacade)
        facade.close()

    def test_unknown_broker_raises(self):
        with pytest.raises(ValueError, match="Unknown broker"):
            create_broker("zerodha")

    def test_case_insensitive(self):
        facade = create_broker("Paper")
        assert isinstance(facade, BrokerFacade)
        facade.close()

    def test_whitespace_stripped(self):
        facade = create_broker("  paper  ")
        assert isinstance(facade, BrokerFacade)
        facade.close()
