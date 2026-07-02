"""Unit tests for BrokerFactory helper functions."""

import os

from brokers.common.auth.env_token import update_env_token as _update_env_token
from brokers.common.env_loader import load_env_file


def test_load_dotenv(tmp_path):
    """load_env_file should parse key=value pairs and set os.environ."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DHAN_CLIENT_ID=MYCLIENT\n"
        'DHAN_ACCESS_TOKEN="mytoken123"\n'
        "# This is a comment\n"
        "SIMPLE_VAR=hello\n"
        "\n"
        "QUOTED_VAR='single_quoted'\n"
    )

    load_env_file(env_file)

    assert os.environ.get("DHAN_CLIENT_ID") == "MYCLIENT"
    assert os.environ.get("DHAN_ACCESS_TOKEN") == "mytoken123"
    assert os.environ.get("SIMPLE_VAR") == "hello"
    assert os.environ.get("QUOTED_VAR") == "single_quoted"

    # Clean up
    for key in ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN", "SIMPLE_VAR", "QUOTED_VAR"):
        os.environ.pop(key, None)


def test_load_dotenv_ignores_comments_and_blanks(tmp_path):
    """Comments and blank lines should be skipped."""
    env_file = tmp_path / ".env"
    env_file.write_text("# full comment\n\n   \nVALID_KEY=valid_value\n")

    load_env_file(env_file)

    assert os.environ.get("VALID_KEY") == "valid_value"

    # Clean up
    os.environ.pop("VALID_KEY", None)


def test_update_env_token(tmp_path):
    """_update_env_token should replace the DHAN_ACCESS_TOKEN value in the file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DHAN_CLIENT_ID=MYCLIENT\nDHAN_ACCESS_TOKEN=old_token_value\nOTHER_VAR=untouched\n"
    )

    _update_env_token(env_file, "new_token_value")

    content = env_file.read_text()
    assert "DHAN_ACCESS_TOKEN=new_token_value" in content
    assert "old_token_value" not in content
    # Other lines should be untouched
    assert "DHAN_CLIENT_ID=MYCLIENT" in content
    assert "OTHER_VAR=untouched" in content


def test_update_env_token_no_file(tmp_path):
    """_update_env_token should silently do nothing if the file does not exist."""
    missing = tmp_path / "nonexistent.env"
    # Should not raise
    _update_env_token(missing, "some_token")
