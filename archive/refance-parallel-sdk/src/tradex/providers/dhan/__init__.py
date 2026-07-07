"""Dhan broker provider — reference implementation.

All Dhan-specific logic lives here.
Nothing Dhan-specific leaks into the core framework.
"""

from tradex.providers.dhan.provider import DhanProvider

__all__ = ["DhanProvider"]
