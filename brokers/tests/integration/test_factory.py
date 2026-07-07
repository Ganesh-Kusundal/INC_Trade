"""Integration tests for broker factory.

Uses ``brokers.connect()`` — the primary public API returning ``BrokerSession``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from brokers.services.broker_session import BrokerSession

from brokers import connect


class TestConnect:
    def test_connect_paper(self):
        broker = connect("paper")
        assert isinstance(broker, BrokerSession)
        broker.close()

    def test_connect_paper_with_cash(self):
        broker = connect("paper", initial_cash=500000)
        assert isinstance(broker, BrokerSession)
        bal = broker.portfolio.funds()
        assert bal.available_cash == Decimal("500000")
        broker.close()

    def test_connect_dhan(self):
        broker = connect("dhan", access_token="tok", client_id="cid")
        assert isinstance(broker, BrokerSession)
        broker.close()

    def test_connect_upstox(self):
        broker = connect("upstox", access_token="tok")
        assert isinstance(broker, BrokerSession)
        broker.close()

    def test_unknown_broker_raises(self):
        with pytest.raises(ValueError, match="Unknown broker"):
            connect("zerodha")

    def test_case_insensitive(self):
        broker = connect("Paper")
        assert isinstance(broker, BrokerSession)
        broker.close()

    def test_whitespace_stripped(self):
        broker = connect("  paper  ")
        assert isinstance(broker, BrokerSession)
        broker.close()
