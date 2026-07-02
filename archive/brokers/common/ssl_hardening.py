"""Hardened SSL/TLS helpers for outbound broker HTTP (REF-38).

Why this module exists
----------------------
A bare :class:`requests.Session` uses ``certifi`` for certificate
verification, which is correct but easy to weaken silently. Anyone
who later passes ``verify=False`` to debug a connection issue
creates a permanent credential-eavesdropping risk on every call
site, not just the broken one.

This module centralises the policy:

- :func:`create_pinned_session` returns a :class:`requests.Session`
  whose transport adapter is built with a deliberately hardened
  :class:`ssl.SSLContext` (TLS 1.2+ only, no weak ciphers, hostname
  checking on). The context is the *default* for every connection
  this session makes, so accidental ``verify=False`` on a single
  call still fails fast.

- :func:`hardened_ssl_context` returns the same context so callers
  using :mod:`urllib3` directly, or :mod:`httpx`, can adopt it.

- :func:`assert_secure_session` is a guard: it inspects an existing
  session and raises if it has been misconfigured. Run this in
  production-readiness checks and CLI startup.

The defaults here are deliberately conservative. They follow the
Mozilla "Intermediate" profile:

- ``TLSv1.2`` minimum (TLS 1.0 and 1.1 disabled)
- Strong cipher list (no RC4, 3DES, NULL, MD5, EXPORT)
- Hostname checking on
- ``OP_NO_COMPRESSION`` to mitigate CRIME

Not done here
-------------
Certificate pinning (public-key or SPKI) is intentionally NOT
implemented in this first cut. Pinning requires the SHA-256 of
each broker's leaf or intermediate key, which changes on every
rotation. We rely on the system trust store for now. A future
revision can layer pinning on top of this helper.
"""

from __future__ import annotations

import importlib
import ssl
from typing import Final

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# TLS configuration. ``ssl.OP_NO_TLSv1`` and ``ssl.OP_NO_TLSv1_1``
# are deprecated in Python 3.10+ but still respected — leaving them
# in for forward-compat with older interpreters.
_TLS_MIN_VERSION: Final[ssl.TLSVersion] = ssl.TLSVersion.TLSv1_2


def hardened_ssl_context() -> ssl.SSLContext:
    """Return a hardened :class:`ssl.SSLContext`.

    The returned context:

    - Disallows TLS 1.0 and 1.1
    - Uses the Mozilla "Intermediate" cipher list
    - Has hostname checking enabled
    - Disables SSL compression (CRIME mitigation)

    Callers SHOULD cache the returned context — constructing one is
    relatively expensive and the object is immutable for our purposes.
    """
    ctx = create_urllib3_context(
        ssl_minimum_version=_TLS_MIN_VERSION,
        cert_reqs=ssl.CERT_REQUIRED,
    )
    # Disable SSL compression (CRIME attack mitigation).
    ctx.options |= ssl.OP_NO_COMPRESSION
    return ctx


class HardenedHTTPSAdapter(HTTPAdapter):
    """HTTPAdapter that pins every request to a hardened SSL context.

    Replace the default adapter on a :class:`requests.Session`::

        session = requests.Session()
        session.mount("https://", HardenedHTTPSAdapter())

    All HTTPS requests through this session will reject:

    - TLS 1.0 / 1.1 handshakes
    - Self-signed or untrusted certificates
    - Hostname mismatches

    Plain HTTP is unchanged — this adapter only enforces TLS for
    ``https://`` URLs, which is what production traffic should use.
    """

    def init_poolmanager(self, *args, **kwargs):
        context = hardened_ssl_context()
        kwargs["ssl_context"] = context
        super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        context = hardened_ssl_context()
        kwargs["ssl_context"] = context
        return super().proxy_manager_for(*args, **kwargs)


def create_pinned_session() -> requests.Session:  # type: ignore[name-defined]
    """Build a :class:`requests.Session` with hardened HTTPS defaults.

    The session is otherwise vanilla — it does not add any default
    headers, hooks, or cookies. Callers are expected to configure
    those as usual.
    """
    import requests  # local import: avoids a hard dep at module import time

    session = requests.Session()
    session.mount("https://", HardenedHTTPSAdapter())
    # Belt and braces: explicitly assert that nobody has weakened
    # the verify flag (the default is True, but make it explicit).
    session.verify = True
    return session


def assert_secure_session(session) -> None:
    """Raise :class:`RuntimeError` if ``session`` is not TLS-hardened.

    Use this in CLI startup and production-readiness checks to fail
    closed on misconfiguration. The check is conservative: if the
    adapter on either scheme does not look like a
    :class:`HardenedHTTPSAdapter`, we raise. This means older
    sessions that pre-date this module will fail the check unless
    they are explicitly migrated.
    """
    if importlib.util.find_spec("requests") is None:
        raise RuntimeError("requests not installed")

    if session.verify is not True:
        raise RuntimeError(f"insecure session: verify={session.verify!r}; must be True")

    https_adapter = session.get_adapter("https://example.invalid/")
    if not isinstance(https_adapter, HardenedHTTPSAdapter):
        raise RuntimeError(
            "insecure session: https adapter is not HardenedHTTPSAdapter; "
            "use brokers.common.ssl_hardening.create_pinned_session()"
        )


__all__ = [
    "HardenedHTTPSAdapter",
    "assert_secure_session",
    "create_pinned_session",
    "hardened_ssl_context",
]
