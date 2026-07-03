"""Broker extension mechanism — isolated broker-specific functionality.

This module provides the extension registry pattern for accessing broker-specific
features without polluting the common gateway interface.

Usage:
    if gateway.supports_extensions(DhanMargin):
        margin = gateway.extension(DhanMargin)
        result = margin.calculate_margin(...)
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class BrokerExtension(Protocol):
    """Base protocol for broker-specific extensions.

    Each broker can expose extensions that are not part of the common gateway
    contract. Extensions are isolated and do not leak into the common interface.
    """

    @property
    def broker_id(self) -> str: ...


def supports_extension(gateway: object, extension_type: type[T]) -> bool:
    """Check if a gateway supports a specific extension type.

    Args:
        gateway: The broker gateway to check.
        extension_type: The extension protocol type to check for.

    Returns:
        True if the gateway has the requested extension.
    """
    return hasattr(gateway, extension_type.__name__.lower())


def get_extension(gateway: object, extension_type: type[T]) -> T | None:
    """Get a broker-specific extension from the gateway.

    Args:
        gateway: The broker gateway to get the extension from.
        extension_type: The extension protocol type.

    Returns:
        The extension instance, or None if not available.
    """
    attr_name = extension_type.__name__.lower()
    return getattr(gateway, attr_name, None)
