"""Unit tests for UpstoxExtended."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.adapters.upstox.extended import UpstoxExtended


class TestUpstoxExtended:
    def test_get_user_profile(self):
        client = MagicMock()
        client.get.return_value = {"data": {"name": "test"}}
        ext = UpstoxExtended(client)
        profile = ext.get_user_profile()
        assert profile.name == "test"

    def test_get_ipos(self):
        client = MagicMock()
        client.get.return_value = {"data": [{"name": "IPO1"}]}
        ext = UpstoxExtended(client)
        ipos = ext.get_ipos()
        assert len(ipos) == 1
