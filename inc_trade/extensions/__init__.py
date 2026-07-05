"""Shared extension protocols — broker-agnostic capability interfaces.

Broker adapters implement these protocols to expose features beyond
the common port interfaces. Clients discover extensions through the
``ExtensionRegistryPort``.

Architecture:
    - Extensions live ``brokers/extensions/`` (shared) or
      ``adapters/<broker>/extensions/`` (broker-specific).
    - Shared extensions are broker-agnostic (e.g., ``DepthExtension``).
    - Broker-specific extensions stay in the adapter layer.
    - No extension may import from ``brokers/adapters/``.
"""

from inc_trade.extensions.base import Extension as Extension
from inc_trade.extensions.depth import DepthExtension as DepthExtension

__all__ = [
    "DepthExtension",
    "Extension",
]
