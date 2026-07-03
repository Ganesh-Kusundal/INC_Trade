"""Tests for BrokerFacade new endpoints (options and extensions)."""

from __future__ import annotations

from brokers import create_broker
from brokers.ports.capabilities import ForeverOrderProvider, NewsProvider
from brokers.adapters.paper.gateway import PaperGateway
import pytest

def test_broker_facade_options_exposure():
    facade = create_broker("paper")
    
    from brokers.domain.exceptions import NotSupportedError
    import pytest

    # Test getting expiries throws error for paper
    with pytest.raises(NotSupportedError):
        expiries = facade.get_expiries("NIFTY")

    # Test getting option chain throws error for paper
    with pytest.raises(NotSupportedError):
        chain = facade.get_option_chain("NIFTY")


def test_broker_facade_extensions_dhan():
    # Because factory is used, Dhan instantiates extensions
    facade = create_broker("dhan", client_id="test", access_token="test")
    
    # Should resolve correctly based on capabilities
    forever_provider = facade.extensions.resolve(facade.broker_id.value, ForeverOrderProvider)
    assert forever_provider is not None
    assert hasattr(forever_provider, "place_forever_order")


def test_broker_facade_extensions_upstox():
    from brokers.ports.capabilities import GTTProvider

    # Upstox factory
    facade = create_broker("upstox", access_token="test")
    
    # Upstox registers GTTProvider
    gtt_provider = facade.extensions.resolve(facade.broker_id.value, GTTProvider)
    assert gtt_provider is not None
    assert hasattr(gtt_provider, "place_gtt")
    
    # Upstox registers News
    news_provider = facade.extensions.resolve(facade.broker_id.value, NewsProvider)
    assert news_provider is not None
    assert hasattr(news_provider, "get_news")
