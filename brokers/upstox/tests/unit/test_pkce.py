from __future__ import annotations

import base64
import hashlib

from brokers.upstox.auth.pkce import UpstoxPkceUtil


def test_pkce_pair_has_verifier_and_challenge():
    pair = UpstoxPkceUtil.generate()
    assert 43 <= len(pair.code_verifier) <= 128
    assert 43 <= len(pair.code_challenge) <= 128


def test_pkce_challenge_is_sha256_of_verifier():
    pair = UpstoxPkceUtil.generate()
    expected = UpstoxPkceUtil.compute_challenge(pair.code_verifier)
    assert pair.code_challenge == expected


def test_pkce_challenge_is_url_safe_base64_no_padding():
    pair = UpstoxPkceUtil.generate()
    decoded = base64.urlsafe_b64decode(pair.code_challenge + "==")
    assert len(decoded) == 32
    assert hashlib.sha256(pair.code_verifier.encode("ascii")).digest() == decoded


def test_pkce_two_pairs_are_distinct():
    a = UpstoxPkceUtil.generate()
    b = UpstoxPkceUtil.generate()
    assert a.code_verifier != b.code_verifier
    assert a.code_challenge != b.code_challenge
