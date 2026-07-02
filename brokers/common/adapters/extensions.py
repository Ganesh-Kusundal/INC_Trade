"""Broker extension bundle factories for CommonBrokerGateway infrastructure."""

from __future__ import annotations

from brokers.common.extensions import ExtensionBundle, get_extension_factory
from brokers.common.gateway import MarketDataGateway


def build_extension_bundle(broker_id: str, gateway: MarketDataGateway) -> ExtensionBundle:
    """Build the extension bundle for a registered legacy gateway.

    Uses the factory registry populated by broker modules at import time.
    No broker-specific imports here — the registry decouples common from
    broker-specific code.
    """
    factory = get_extension_factory(broker_id)
    if factory is not None:
        return factory(gateway)
    return ExtensionBundle(broker_id)
