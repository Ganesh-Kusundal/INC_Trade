"""Tests for BrokerFacade new endpoints (options and extensions)."""

from __future__ import annotations

import pytest
from inc_trade.ports.capabilities import ForeverOrderProvider, NewsProvider

import brokers


def test_broker_session_options_exposure():
    broker = brokers.connect("paper")

    from inc_trade.domain.exceptions import NotSupportedError

    # Test getting expiries throws error for paper
    with pytest.raises(NotSupportedError):
        broker.market.expiries("NIFTY")

    # Test getting option chain throws error for paper
    with pytest.raises(NotSupportedError):
        broker.market.option_chain("NIFTY")

    broker.close()


def test_broker_session_extensions_dhan():
    broker = brokers.connect("dhan", client_id="test", access_token="test")

    # Should resolve correctly based on capabilities
    forever_provider = broker.extensions.resolve(broker.broker_id, ForeverOrderProvider)
    assert forever_provider is not None
    assert hasattr(forever_provider, "place_forever_order")
    broker.close()


def test_broker_session_extensions_upstox():
    from inc_trade.ports.capabilities import GTTProvider

    broker = brokers.connect("upstox", access_token="test")

    # Upstox registers GTTProvider
    gtt_provider = broker.extensions.resolve(broker.broker_id, GTTProvider)
    assert gtt_provider is not None
    assert hasattr(gtt_provider, "place_gtt")

    # Upstox registers News
    news_provider = broker.extensions.resolve(broker.broker_id, NewsProvider)
    assert news_provider is not None
    assert hasattr(news_provider, "get_news")
    broker.close()
