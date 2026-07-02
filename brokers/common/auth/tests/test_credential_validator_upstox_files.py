"""Tests for Upstox file-based credential validation."""

from __future__ import annotations

from brokers.common.auth.credential_validator import CredentialValidator


def test_upstox_totp_validates_pin_and_totp_files(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.upstox"
    pin_file = tmp_path / "config" / "upstox-pin.txt"
    totp_file = tmp_path / "config" / "upstox-totp-secret.txt"
    pin_file.parent.mkdir(parents=True)
    pin_file.write_text("123456")
    totp_file.write_text("JBSWY3DPEHPK3PXP")

    env_file.write_text(
        "UPSTOX_CLIENT_ID=test-client\n"
        "UPSTOX_AUTH_MODE=TOTP\n"
        "UPSTOX_MOBILE=9876543210\n"
        f"UPSTOX_PIN_FILE={pin_file}\n"
        f"UPSTOX_TOTP_SECRET_FILE={totp_file}\n"
    )

    monkeypatch.chdir(tmp_path)
    ok, issues = CredentialValidator.validate_broker("upstox", env_file)
    assert ok is True
    assert not any(i.severity == "error" for i in issues)
