"""Broker Adapters — primary interface to broker capabilities.

The adapters layer replaces the old ``BrokerGateway`` pattern with a
clean ``BrokerAdapter`` protocol that implements provider interfaces
directly. Adapters can be injected into ``Instrument`` objects as
providers for quotes, depth, historical data, streaming, and orders.

Usage::

    from inc_trade.adapters.broker_adapter import BrokerAdapter

    adapter: BrokerAdapter
    adapter.connect()
    inst = adapter.instrument("RELIANCE", "NSE")
    inst.quote()
    inst.buy(qty=10)
"""

from inc_trade.adapters.broker_adapter import BrokerAdapter as BrokerAdapter

__all__ = [
    "BrokerAdapter",
]
