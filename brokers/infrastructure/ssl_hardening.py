"""SSL/TLS hardening for outbound HTTP connections.

Enforces TLS 1.2+, disables compression, and uses Mozilla Intermediate
cipher suite to prevent downgrade attacks and weak cipher exploitation.
"""

from __future__ import annotations

import ssl

import requests
from requests.adapters import HTTPAdapter

_MOZILLA_INTERMEDIATE_CIPHERS = (
    "ECDHE-ECDSA-AES128-GCM-SHA256:"
    "ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:"
    "ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-CHACHA20-POLY1305:"
    "ECDHE-RSA-CHACHA20-POLY1305:"
    "DHE-RSA-AES128-GCM-SHA256:"
    "DHE-RSA-AES256-GCM-SHA384"
)


def hardened_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers(_MOZILLA_INTERMEDIATE_CIPHERS)
    ctx.options |= ssl.OP_NO_COMPRESSION
    ctx.options |= ssl.OP_NO_RENEGOTIATION
    return ctx


class HardenedHTTPSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = hardened_ssl_context()
        super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs["ssl_context"] = hardened_ssl_context()
        return super().proxy_manager_for(proxy, **proxy_kwargs)


def create_pinned_session() -> requests.Session:
    session = requests.Session()
    adapter = HardenedHTTPSAdapter(pool_connections=10, pool_maxsize=20)
    session.mount("https://", adapter)
    return session
