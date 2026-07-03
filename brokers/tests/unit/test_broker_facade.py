"""Tests for BrokerFacade new endpoints (options and extensions)."""

from __future__ import annotations

from brokers import create_broker
from brokers.ports.capabilities import ForeverOrderProvider, NewsProvider
from brokers.adapters.paper.gateway import PaperGateway
import pytest

def test_broker_facade_options_exposure():
    facade = create_broker("paper")
    
    # Test getting expiries
    expiries = facade.get_expiries("NIFTY")
    assert isinstance(expiries, list)
    
    # Test getting option chain
    chain = facade.get_option_chain("NIFTY")
    assert chain.underlying == "NIFTY"


@pytest.mark.xfail(reason="DhanForeverOrders does not conform to ForeverOrderProvider protocol yet")
def test_broker_facade_extensions_dhan():
    # Because factory is used, Dhan instantiates extensions
    facade = create_broker("dhan", client_id="test", access_token="test")
    
    # Should resolve correctly based on capabilities
    forever_provider = facade.extensions.resolve(facade.broker_id.value, ForeverOrderProvider)
    assert forever_provider is not None
    assert hasattr(forever_provider, "place_forever_order")


@pytest.mark.xfail(reason="UpstoxGtt does not conform to ForeverOrderProvider protocol yet")
def test_broker_facade_extensions_upstox():
    # Upstox factory
    facade = create_broker("upstox", access_token="test")
    
    # Upstox registers GTT as ForeverOrderProvider
    forever_provider = facade.extensions.resolve(facade.broker_id.value, ForeverOrderProvider)
    assert forever_provider is not None
    assert hasattr(forever_provider, "place_forever_order")
    
    # Upstox registers News
    news_provider = facade.extensions.resolve(facade.broker_id.value, NewsProvider)
    assert news_provider is not None
    assert hasattr(news_provider, "get_news")
