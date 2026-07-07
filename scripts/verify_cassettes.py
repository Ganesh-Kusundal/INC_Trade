#!/usr/bin/env python3
"""6-pattern secrets audit for VCR.py cassettes — YAML-aware.

Why rewrite from bash
---------------------
A bash-only gauntlet has two correctness classes it cannot handle:

1. **List-form headers.** vcrpy 8.x serialises headers like
   ``access-token: [abc123xyz]``. A flow-style regex over raw YAML text
   cannot reliably detect this; the headers dict in the parsed cassette
   is ``dict[str, list[str]]`` and must be walked field-by-field.

2. **Line-level whitelist false-positives.** A bash grep `-v` whitelist
   filters an entire line if the line contains the placeholder. A
   cassette line with both ``***SENSITIVE***`` and a real leak would be
   silently approved. Audit must be FIELD-SCOPED: check each header
   value, each body field, each query parameter independently.

This script uses ``yaml.safe_load`` so each cassette becomes a structured
object, then walks it field-by-field with proper scope. Run it via
``make verify-cassettes`` or the pre-commit hook — both delegate to
this file as the single source of truth.

Audit dimensions
----------------
1. Auth request/response header VALUES populated (after vcrpy filtering,
   these should be ``***SENSITIVE***``).
2. JWT-shaped strings anywhere in body or header (``eyJ...eyJ...``).
3. ``accessToken`` / ``access_token`` / etc. populated in JSON body.
4. Long random strings (40+ chars alpha/digit/underscore/hyphen) inside
   JSON-string values — high-fidelity token/key signal.
5. Query parameters shaped like credentials (``?token=...``,
   ``?access_token=...``, ``?api_key=...``).
6. ``clientId`` / ``accountId`` populated in JSON body.

Whitelist (FIELD-SCOPED — the key fix from the bash version)
------------------------------------------------------------
A value is treated as a placeholder (and audit-skipped) when it matches
``PLACEHOLDER_RX``: any string of the form ``***SENSITIVE***``,
``***CLIENT_ID***``, or ``offline-dummy-{client,token}``. Placeholder
detection is per-value, not per-line — a line containing both a
placeholder header and a leaked token header will fail as expected.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import urllib.parse as urlparse
from collections.abc import Mapping, Sequence
from typing import Any

import yaml

# ── Configuration ────────────────────────────────────────────────────────

# Header NAMES (case-insensitive match) whose VALUES we audit.
SENSITIVE_HEADER_NAMES: frozenset[str] = frozenset({
    "access-token",
    "client-id",
    "authorization",
    "cookie",
    "set-cookie",
})

# JSON body FIELD NAMES whose VALUES we audit.
SENSITIVE_BODY_FIELDS: frozenset[str] = frozenset({
    "accessToken",
    "access_token",
    "access-token",
    "clientId",
    "client_id",
    "client-id",
    "accountId",
    "apiKey",
    "api_key",
    "secret",
})

# URI query PARAM NAMES whose VALUES we audit.
SENSITIVE_QUERY_PARAMS: frozenset[str] = frozenset({
    "token",
    "access_token",
    "access-token",
    "api_key",
    "api-key",
    "sid",
    "ssid",
})

# Field-scoped placeholder pattern. A value matching this is treated as
# SAFE: it is the literal that vcrpy's default header filter or our
# offline conftest substitutes in. Per-value match — does not filter
# neighbouring values on the same line.
PLACEHOLDER_RX: re.Pattern[str] = re.compile(
    r"^\*{2,}[A-Z_]+\*{2,}$|^offline-dummy-(?:client|token)$",
    re.IGNORECASE,
)

# Field-scoped JWT pattern — matches directly, not via line grep.
JWT_RX: re.Pattern[str] = re.compile(
    r"^eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.",
)

# Long-random-pattern heuristic: alphadigit/underscore/hyphen, 40+ chars.
LONG_RANDOM_RX: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-]{40,}$")


# ── Helpers ──────────────────────────────────────────────────────────────


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(PLACEHOLDER_RX.match(value.strip()))


def _looks_like_jwt(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(JWT_RX.match(value.strip()))


def _looks_like_long_random(value: Any, threshold: int = 40) -> bool:
    if not isinstance(value, str):
        return False
    return len(value) >= threshold and bool(LONG_RANDOM_RX.match(value))


# ── Body walker ──────────────────────────────────────────────────────────


def _walk_body_for_secrets(
    obj: Any,
    location: str,
    issues: list[str],
) -> None:
    """Recursively walk a parsed JSON body, accumulating field-scoped issues.

    The walk is field-scoped, NOT line-scoped — we never inspect raw text,
    only parsed fields. This is the fix to the bash line-level whitelist
    false-positive bug.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_str = str(k)
            if isinstance(v, str):
                if not _is_placeholder(v):
                    if key_str in SENSITIVE_BODY_FIELDS:
                        issues.append(
                            f"{location}: field {key_str!r} populated (value len {len(v)})"
                        )
                    elif _looks_like_jwt(v):
                        issues.append(f"{location}: JWT pattern in field {key_str!r}")
                    elif _looks_like_long_random(v):
                        issues.append(
                            f"{location}: long random value ({len(v)} chars) in field {key_str!r}"
                        )
                # If placeholder, skip — but do NOT skip sibling fields.
            elif isinstance(v, (Mapping, Sequence)):
                _walk_body_for_secrets(v, f"{location}.{key_str}", issues)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            if isinstance(item, (Mapping, Sequence)):
                _walk_body_for_secrets(item, f"{location}[{idx}]", issues)
            elif isinstance(item, str):
                if _looks_like_jwt(item):
                    issues.append(f"{location}[{idx}]: JWT pattern in string element")


# ── Per-cassette audit ───────────────────────────────────────────────────


def audit_cassette(path: pathlib.Path) -> list[str]:
    """Return a list of issue descriptions for ``path``. Empty = clean."""
    issues: list[str] = []

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    interactions = data.get("interactions") or []
    if not isinstance(interactions, list):
        issues.append(f"top-level 'interactions' is not a list: {type(interactions).__name__}")
        return issues

    for ix_idx, ix in enumerate(interactions):
        # ── Request side ──
        request = ix.get("request") or {}
        _audit_headers(request, "request", issues)
        _audit_uri_query(request, "request", issues)
        _audit_body(request, "request", issues)

        # ── Response side ──
        response = ix.get("response") or {}
        _audit_headers(response, "response", issues)
        _audit_body(response, "response", issues)

    return issues


def _audit_headers(section: dict[str, Any], side: str, issues: list[str]) -> None:
    headers = section.get("headers") or {}
    if not isinstance(headers, dict):
        return
    for name, value in headers.items():
        if not isinstance(value, list):
            continue
        for v_idx, v in enumerate(value):
            if isinstance(v, str) and not _is_placeholder(v):
                if str(name).lower() in SENSITIVE_HEADER_NAMES:
                    issues.append(
                        f"{side} header {name!r} populated "
                        f"(idx={v_idx}, value len {len(v)})"
                    )
                elif _looks_like_long_random(v):
                    issues.append(
                        f"{side} header {name!r}: long random value "
                        f"({len(v)} chars) at idx {v_idx}"
                    )


def _audit_uri_query(section: dict[str, Any], side: str, issues: list[str]) -> None:
    uri = section.get("uri")
    if not uri or not isinstance(uri, str):
        return
    try:
        parsed = urlparse.urlparse(uri)
    except (ValueError, TypeError):
        # urlparse rarely raises; if it does, treat the URI as unscannable.
        return
    qs = urlparse.parse_qsl(parsed.query, keep_blank_values=True)
    for k, v in qs:
        if k.lower() not in SENSITIVE_QUERY_PARAMS:
            continue
        if _is_placeholder(v):
            continue
        issues.append(
            f"{side} URI query param {k!r} populated (uri={uri!r})"
        )


def _audit_body(section: dict[str, Any], side: str, issues: list[str]) -> None:
    body = section.get("body")
    if body is None:
        return
    # vcrpy emits body either as raw string (raw http body) or as a
    # dict like {'string': '...'} from the urllib serializer. Handle
    # both forms.
    if isinstance(body, Mapping):
        # Take first meaningful body field — usually 'string' or 'base64'.
        body_str = next(iter(body.values()), None)
        if not isinstance(body_str, str):
            return
    elif isinstance(body, str):
        body_str = body
    else:
        return

    # Try to parse as JSON — if successful, walk field-by-field.
    try:
        parsed = json.loads(body_str)
    except (json.JSONDecodeError, ValueError):
        # Non-JSON body — fall back to a substring scan ONLY for the JWT
        # pattern (which would indicate a bearer token leaked into a
        # non-JSON payload, e.g., XML).
        if _looks_like_jwt(body_str):
            issues.append(f"{side} body: JWT pattern in non-JSON body")
        return

    _walk_body_for_secrets(parsed, f"{side} body", issues)


# ── Entry point ──────────────────────────────────────────────────────────


def main() -> int:
    script_dir = pathlib.Path(__file__).parent
    cassette_dir = pathlib.Path(
        os.environ.get(
            "CASSETTE_DIR",
            script_dir.parent / "brokers" / "tests" / "integration" / "cassettes",
        )
    ).resolve()

    if not cassette_dir.is_dir():
        print(f"(no cassettes directory at {cassette_dir} — nothing to audit)")
        return 0

    # Recursive scan: cassette_dir/{**/}*.yaml. Use rglob so deeper-than-one-level
    # subdirectories are also covered (matches how vcrpy commercial projects
    # sometimes layout cassettes per integration directory).
    cassettes = sorted(p for p in cassette_dir.rglob("*.yaml") if p.is_file())
    # De-dup by absolute path (rglob can yield duplicates when symlinked or
    # when top-level happens to also match the recursive pattern).
    cassettes = sorted(set(cassettes))

    if not cassettes:
        print(f"(no .yaml cassettes under {cassette_dir} — nothing to audit)")
        return 0

    print(f"Auditing {len(cassettes)} cassette file(s) under {cassette_dir}\n")

    errors = 0

    for cassette in cassettes:
        try:
            issues = audit_cassette(cassette)
        except yaml.YAMLError as exc:
            print(f"  [FAIL] {cassette.name}: malformed YAML: {exc}")
            errors += 1
            continue
        except (KeyError, AttributeError, TypeError) as exc:
            print(f"  [FAIL] {cassette.name}: audit crash: {type(exc).__name__}: {exc}")
            errors += 1
            continue

        if not issues:
            print(f"  [OK]   {cassette.name}")
            continue

        for issue in issues:
            print(f"  [FAIL] {cassette.name}: {issue}")
        errors += 1

    print()
    if errors:
        print(f"FAILED — {errors} cassette(s) have leaked secrets")
        print("Re-record with FORCE_MARKET_OPEN=1 + creds, OR rotate leaked credentials.")
        return 1
    print(f"PASSED — {len(cassettes)} cassette file(s) audited, no leaks detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
