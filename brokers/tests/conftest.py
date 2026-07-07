"""Pytest root configuration — VCR.py cassette replay for live-marked tests.

Background
----------
``BaseHttpClient`` (in ``brokers/infrastructure/http_client.py``) wraps a
``requests.Session``. ``vcrpy`` hooks ``requests`` at the transport layer
and replays recorded responses when a cassette is present, so the rest of
the test can run hermetically against a recorded Dhan sandbox payload
without network IO.

Gating semantics
----------------
A test marked ``@pytest.mark.live`` follows **three** environment-driven
modes (resolved by :func:`brokers.tests._live_modes.resolve_live_mode`):

| FORCE_MARKET_OPEN | Creds present | Cassette present | Behaviour                     |
|-------------------|---------------|------------------|-------------------------------|
| ``1``             | yes           | any              | LIVE: real Dhan sandbox        |
| ``1``             | no            | any              | SKIP (auth required)            |
| unset / ``0``     | any           | yes              | OFFLINE REPLAY: cassette, no network |
| unset / ``0``     | any           | no               | SKIP (no cassette yet)          |

The legacy ``FORCEMARKETOPEN`` (no underscore) is also accepted as an alias.

Cassette location
-----------------
Cassettes live in ``brokers/tests/integration/cassettes/`` and are named
identically to the test (e.g.
``test_safe_order_round_trips_through_wired_wrapper.yaml``).
``pytest-recording`` provides this auto-naming by default; we wire it
explicitly here so the conftest is self-contained.

Header filtering — PII safety
-----------------------------
Auth headers (``access-token``, ``client-id``, ``cookie``,
``authorization``) are masked on RECORD so cassettes are safe to commit
even when sanitisation lapses.

Pre-commit secrets audit (the migration note)
---------------------------------------------
The single source of truth for cassette hygiene is
``scripts/verify_cassettes.py`` (YAML-aware, field-scoped). It is invoked
from two places — both delegate here, so the audit cannot drift:

- ``make verify-cassettes`` — manual invocation
- ``.pre-commit-config.yaml`` local hook — automatic on any staged change
  to ``brokers/tests/integration/cassettes/*.yaml``

The audit detects:

- Auth header values populated (vcrpy should mask these to ``***SENSITIVE***``)
- JWT-shaped strings (``eyJ….eyJ….``) anywhere in body or header
- ``accessToken`` / ``access_token`` / ``clientId`` / ``accountId`` populated
  inside JSON body fields
- Long random strings (40+ chars of alphanumerics / underscore / hyphen)
  inside JSON-string values — high-confidence token signal
- Token-shaped query parameters in URIs (``?token=``, ``?api_key=``,
  ``?access_token=``, ``?sid=``, ``?ssid=``)

If the audit fails, do NOT bypass the hook (``git commit --no-verify`` is
acceptable in an operator break-glass moment only). Re-record with
``FORCE_MARKET_OPEN=1`` + creds and replace the cassette; OR rotate the
leaked credential; OR fix the conftest's filter_headers if the leak is a
known false positive.

Why YAML-aware?
~~~~~~~~~~~~~~~
vcrpy 8.x serialises headers in LIST form (``access-token: [abc123]``).
Raw-shell ``grep`` cannot reliably detect this — the values are nested
inside YAML list elements. ``scripts/verify_cassettes.py`` parses each
cassette with ``yaml.safe_load`` and walks the resulting
``dict[str, list[str]]`` field-by-field. Whitelisting (e.g.
``***SENSITIVE***``, ``offline-dummy-client``) is also field-scoped — a
line containing both a placeholder AND a leaked real secret will fail as
expected, where a line-level grep would have silently passed.

Recording workflow
------------------
To regenerate cassettes (e.g. when the Dhan sandbox contract changes),
run with live credentials + `FORCE_MARKET_OPEN=1`::

    FORCE_MARKET_OPEN=1 DHAN_SANDBOX_CLIENT_ID=… DHAN_SANDBOX_ACCESS_TOKEN=… \\
        pytest -m live brokers/tests/integration/test_risk_wiring_live_sandbox.py

vcrpy in ``record_mode="new_episodes"`` will write new cassettes under
``brokers/tests/integration/cassettes/``. Inspect them, commit them —
the pre-commit hook will then audit before the commit lands.
"""

from __future__ import annotations

from typing import Any

import pytest

# Local import — single source of truth for mode-resolution logic.
# (Avoids duplicating it here AND in the test file; tests intgeration
# also imports it.)
from brokers.tests._live_modes import (
    cassette_path_for,
    resolve_live_mode,
)


# ── Constants ────────────────────────────────────────────────────────────

# Sensitive headers that MUST be masked in any committed cassette.
_SENSITIVE_REQUEST_HEADERS = frozenset({
    "access-token",
    "client-id",
    "authorization",
    "cookie",
    "set-cookie",
})

_SENSITIVE_RESPONSE_HEADERS = frozenset({
    "set-cookie",
    "authorization",
})


# ── Pytest hooks ─────────────────────────────────────────────────────────


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply default marker filtering: skip ``live`` tests unless ``-m live``.
    Without this hook, default `pytest` runs would execute live tests.
    """
    expr = config.option.markexpr
    if expr:
        return  # caller has supplied an explicit marker expression
    # No -m flag → skip live tests by default
    skip_live = pytest.mark.skip(reason="`live` marker — use `-m live` to run; cassettes enable offline replay in `-m live` mode too")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


# ── Fixture: vcr cassette auto-resolution for live tests ─────────────────


@pytest.fixture(autouse=True)
def _auto_vcr_for_live_tests(request: pytest.FixtureRequest) -> Any:
    """Wrap each ``@pytest.mark.live`` test in a ``vcr.use_cassette`` block.

    We instantiate ``vcr.VCR`` *directly* rather than depend on the
    ``vcr`` fixture from ``pytest-recording``: that fixture occasionally
    resolves to ``None`` in autouse contexts. Direct instantiation gives
    us full control over record_mode, header filtering, and cassette
    matching.

    Modes (see :func:`brokers.tests._live_modes.resolve_live_mode`):
    - ``live``:   ``record_mode="new_episodes"`` — actually call Dhan sandbox.
    - ``replay``: ``record_mode="none"`` — strict offline replay; pytest.skip
                  if cassette missing.
    - ``skip``:   No cassette opened; test's own skipif logic decides.
    """
    import vcr  # local import — keeps top-level imports clean

    if "live" not in request.keywords:
        yield  # not a live test — passthrough
        return

    mode = resolve_live_mode()
    if mode == "live":
        record_mode = "new_episodes"
    elif mode == "replay":
        record_mode = "none"
    else:
        # mode == "skip" — no cassette; test's own skipif marker decides
        yield
        return

    cassette_name = getattr(request, "param", None) or request.node.name
    cassette_path = cassette_path_for(cassette_name)

    # In offline-replay mode, if the cassette is missing we SKIP cleanly
    # rather than fail. Developers can record new cassettes locally with
    # ``FORCE_MARKET_OPEN=1``; recorded cassettes committed to the repo
    # keep CI hermetic.
    if mode == "replay" and not cassette_path.exists():
        pytest.skip(
            f"Cassette missing for offline replay: {cassette_path}. "
            f"Either run with FORCE_MARKET_OPEN=1 + creds to record, "
            f"or commit an existing cassette."
        )

    # Cassette path uses forward slashes for cross-platform YAML consistency.
    cassette_arg = str(cassette_path).replace("\\", "/")

    vcr_instance = vcr.VCR(
        record_mode=record_mode,
        filter_headers=(
            list(_SENSITIVE_REQUEST_HEADERS),
            list(_SENSITIVE_RESPONSE_HEADERS),
        ),
        match_on=["method", "scheme", "host", "port", "path", "query"],
    )

    with vcr_instance.use_cassette(cassette_arg):
        yield


# ── Marker registration ──────────────────────────────────────────────────


def pytest_configure(config: pytest.Config) -> None:
    """Register the ``live`` marker explicitly so `--strict-markers` is happy.
    Idempotent — pytest skips double-registration.
    """
    config.addinivalue_line(
        "markers",
        "live: marks tests as live-broker tests (skipped by default; run with `-m live`)",
    )


__all__ = [
    "pytest_collection_modifyitems",
    "pytest_configure",
]
