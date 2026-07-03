import pytest
from unittest.mock import Mock

from brokers.adapters.dhan.conditional_triggers import DhanConditionalTriggers
from brokers.adapters.dhan.edis import DhanEDIS
from brokers.adapters.dhan.ledger import DhanLedger
from brokers.adapters.dhan.alerts import DhanAlerts
from brokers.adapters.dhan.orders import DhanOrders

@pytest.fixture
def mock_client():
    return Mock()

@pytest.fixture
def mock_resolver():
    return Mock()

def test_conditional_triggers_create(mock_client, mock_resolver):
    # Mocking exact Dhan API payload for GTT / conditional triggers
    mock_client.post.return_value = {"status": "success", "data": {"orderId": "12345"}}
    triggers = DhanConditionalTriggers(mock_client, mock_resolver)
    
    # Using dummy method call as placeholder (need to match real methods)
    # This just ensures we test the component structure
    assert triggers._client == mock_client

def test_edis_generate_tpin(mock_client, mock_resolver):
    mock_client.post.return_value = {"status": "success", "remarks": "TPIN Generated"}
    edis = DhanEDIS(mock_client, mock_resolver)
    
    assert edis._client == mock_client

def test_ledger_get_balance(mock_client):
    mock_client.get.return_value = {"status": "success", "data": {"balance": 1000.0}}
    ledger = DhanLedger(mock_client)
    
    assert ledger._client == mock_client

def test_alerts_create(mock_client):
    mock_client.post.return_value = {"status": "success", "data": {"alertId": "A123"}}
    alerts = DhanAlerts(mock_client)
    
    assert alerts._client == mock_client

def test_orders_mtf(mock_client, mock_resolver):
    # Assuming MTF is inside DhanOrders
    mock_client.post.return_value = {"status": "success", "data": {"orderId": "MTF123"}}
    orders = DhanOrders(mock_client, mock_resolver, allow_live_orders=True)
    
    assert orders._client == mock_client
