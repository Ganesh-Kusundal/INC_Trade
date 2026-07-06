"""Strangler bridge — alias legacy import path to brokers_core gateway."""
import sys

from brokers_core.adapters.upstox import gateway as _gateway

sys.modules[__name__] = _gateway
