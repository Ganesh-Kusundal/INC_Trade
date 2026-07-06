"""Broker Adapters — provider protocol implementations.

Adapters implement provider protocols (``InstrumentDataProvider``,
``DepthProvider``, ``OrderProvider``, etc.) and can be injected directly
into ``Instrument`` objects for quotes, depth, historical data, streaming,
and orders.

Usage::

    from brokers_core.adapters.broker_adapter import BrokerAdapter
"""

from brokers_core.adapters.broker_adapter import BrokerAdapter as BrokerAdapter

__all__ = [
    "BrokerAdapter",
]
