"""Strangler bridge."""
from brokers_core.extensions.registry import *  # noqa: F403
from brokers_core.market.extension_registry import (  # noqa: F401
    get_default_extension_registry as get_default_registry,
    reset_default_extension_registry as reset_default_registry,
)
