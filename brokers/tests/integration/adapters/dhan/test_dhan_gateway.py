import gc
import pytest
from unittest.mock import patch

from brokers.adapters.dhan.gateway import DhanGateway

@pytest.fixture
def mock_dhan_gateway_deps():
    with patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="token123"), \
         patch("brokers.adapters.dhan.auth.DhanAuth.generate_token", return_value="token123"), \
         patch("brokers.adapters.dhan.gateway.JsonTokenStateStore"):
        yield

def test_gateway_assembles_components(mock_dhan_gateway_deps):
    gateway = DhanGateway(
        access_token="test_token",
        client_id="test_client",
        auto_refresh=False
    )
    
    # Assert all 15 components are instantiated
    assert gateway.orders is not None
    assert gateway.super_orders is not None
    assert gateway.forever_orders is not None
    assert gateway.margin is not None
    assert gateway.options is not None
    assert gateway.futures is not None
    assert gateway.order_stream is not None
    assert gateway.conditional_triggers is not None
    assert gateway.exit_all is not None
    assert gateway.edis is not None
    assert gateway.depth20_stream is not None
    assert gateway.depth200_stream is not None
    assert gateway.ledger is not None
    assert gateway.alerts is not None
    assert gateway.ip_management is not None
    assert gateway.user_profile is not None
    assert gateway.reconciliation is not None
    assert gateway.symbol_validator is not None
    assert gateway.market_data is not None
    assert gateway.portfolio is not None
    assert gateway.instruments is not None
    assert gateway.historical is not None
    assert gateway.streaming is not None
    
    gateway.close()

def test_gateway_no_memory_leaks(mock_dhan_gateway_deps):
    """
    Test that creating and closing the gateway doesn't leave dangling references,
    which is critical when assembling 15+ components with cross-references.
    """
    gc.collect()
    initial_objects = len(gc.get_objects())
    
    # Create and close gateway in a scope
    def create_and_destroy():
        gw = DhanGateway(
            access_token="test_token",
            client_id="test_client",
            auto_refresh=False
        )
        gw.close()
    
    create_and_destroy()
    
    gc.collect()
    final_objects = len(gc.get_objects())
    
    # Depending on Python version and other factors, exact object count might fluctuate slightly,
    # but a massive leak (e.g. cycles from 15 components) would show up as thousands of objects.
    assert abs(final_objects - initial_objects) < 100, f"Potential memory leak detected. Object count grew by {final_objects - initial_objects}"
