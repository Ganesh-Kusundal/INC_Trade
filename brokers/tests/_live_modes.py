"""Shared helper for live test mode resolution (LIVE / REPLAY / SKIP).

Single source of truth imported by both ``brokers/tests/conftest.py`` (which
uses it for the autouse VCR fixture) and ``brokers/tests/integration/test_risk_wiring_live_sandbox.py``
(which uses it for inline ``pytest.skip`` decisions per test).

Three-mode semantics
--------------------
See :func:`resolve_live_mode` for the full mapping. The legacy alias
``FORCEMARKETOPEN`` (no underscore) is also recognised for backwards
compatibility but ``FORCE_MARKET_OPEN`` is preferred.
"""

from __future__ import annotations

import os
from pathlib import Path

# Re-exported from here so callers import a single symbol.
# (Avoids accidentally duplicating the mode-decision logic in either file.)

# Cassette root — flat layout, one YAML per test, named identically to the
# test function. Imported here so both conftest.py and tests/intgeration
# resolve cassettes the same way.
CASSETTE_DIR: Path = Path(__file__).parent / "integration" / "cassettes"


def resolve_live_mode() -> str:
    """Return ``"live"`` | ``"replay"`` | ``"skip"``.

    Modes are env-driven at FIXTURE-RESOLUTION time (per test), so any
    process state that mutates FORCE_MARKET_OPEN within a test does NOT
    flip behaviour. That's intentional — mid-test mode flips would mask
    real bugs.
    """
    raw = (
        os.environ.get("FORCE_MARKET_OPEN")
        or os.environ.get("FORCEMARKETOPEN")  # legacy alias
        or ""
    ).strip().lower()
    is_live = raw in ("1", "true", "yes", "on")

    has_creds = bool(
        os.environ.get("DHAN_SANDBOX_CLIENT_ID")
        and os.environ.get("DHAN_SANDBOX_ACCESS_TOKEN")
    )

    if is_live and has_creds:
        return "live"
    if is_live and not has_creds:
        return "skip"  # LIVE requested but auth missing — never fail CI
    # Off (or absent): try cassette replay if marker present
    return "replay"


def cassette_path_for(test_name: str) -> Path:
    """Locate the cassette YAML for a given test function.

    Convention: cassette root ``brokers/tests/integration/cassettes/``
    with one YAML per test, named identically to the test function name.
    Subdirectories per test file are intentionally NOT used — keeping
    cassettes flat makes them easy to grep across the suite and avoids
    extra filesystem nesting.
    """
    return CASSETTE_DIR / f"{test_name}.yaml"


def cassette_exists(test_name: str) -> bool:
    """True when a recorded cassette is present for ``test_name``."""
    return cassette_path_for(test_name).exists()


def should_skip_live_test(test_name: str) -> bool:
    """Return True when NEITHER live mode NOR cassette replay is available.

    Tests that gate auto-skip on this function can be safely inserted
    into a hermetic CI run — they'll skip cleanly without breaking the
    build.
    """
    mode = resolve_live_mode()
    if mode == "live":
        return False
    if mode == "replay" and cassette_exists(test_name):
        return False
    return True


__all__ = [
    "CASSETTE_DIR",
    "resolve_live_mode",
    "cassette_path_for",
    "cassette_exists",
    "should_skip_live_test",
]
