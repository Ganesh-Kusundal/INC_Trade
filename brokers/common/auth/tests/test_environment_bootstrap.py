"""Regression tests for centralized environment bootstrap."""

from __future__ import annotations

import os

from brokers.common.auth.environment_bootstrap import bootstrap_environment


class TestBootstrapEnvironment:
    def test_loads_dhan_and_upstox_env_files(self, tmp_path, monkeypatch):
        dhan_env = tmp_path / ".env.local"
        upstox_env = tmp_path / ".env.upstox"
        dhan_env.write_text("DHAN_CLIENT_ID=dhan-cid\nDHAN_ACCESS_TOKEN=dhan-tok\n")
        upstox_env.write_text("UPSTOX_CLIENT_ID=up-cid\nUPSTOX_ACCESS_TOKEN=up-tok\n")

        monkeypatch.chdir(tmp_path)
        loaded = bootstrap_environment(project_root=tmp_path)

        assert loaded["dhan"] == dhan_env
        assert loaded["upstox"] == upstox_env
        assert os.environ["DHAN_CLIENT_ID"] == "dhan-cid"
        assert os.environ["UPSTOX_CLIENT_ID"] == "up-cid"

    def test_skips_missing_and_empty_files(self, tmp_path, monkeypatch):
        empty = tmp_path / ".env.local"
        empty.write_text("")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)

        loaded = bootstrap_environment(project_root=tmp_path)

        assert loaded["dhan"] is None
        assert loaded["upstox"] is None
        assert "DHAN_CLIENT_ID" not in os.environ

    def test_idempotent_second_call(self, tmp_path, monkeypatch):
        env = tmp_path / ".env.local"
        env.write_text("DHAN_CLIENT_ID=cid\n")
        monkeypatch.chdir(tmp_path)

        first = bootstrap_environment(project_root=tmp_path)
        env.write_text("DHAN_CLIENT_ID=updated\n")
        second = bootstrap_environment(project_root=tmp_path)

        assert first["dhan"] == env
        assert second["dhan"] == env
        # Second load re-reads the file and overwrites os.environ.
        assert os.environ["DHAN_CLIENT_ID"] == "updated"

    def test_paper_broker_ignored(self, tmp_path):
        loaded = bootstrap_environment(project_root=tmp_path, brokers=("paper", "dhan"))
        assert "paper" not in loaded
        assert "dhan" in loaded
