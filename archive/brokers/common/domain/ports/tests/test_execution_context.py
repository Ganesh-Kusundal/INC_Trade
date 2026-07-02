"""Tests for domain.ports.execution_context — OMS-managed submit context."""
from __future__ import annotations

from domain.ports.execution_context import is_oms_managed_submit, oms_managed


def test_default_is_not_oms_managed():
    assert is_oms_managed_submit() is False


def test_oms_managed_sets_flag():
    with oms_managed():
        assert is_oms_managed_submit() is True
    assert is_oms_managed_submit() is False


def test_oms_managed_resets_on_exception():
    try:
        with oms_managed():
            assert is_oms_managed_submit() is True
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert is_oms_managed_submit() is False


def test_nested_oms_managed_restores_outer():
    assert is_oms_managed_submit() is False
    with oms_managed():
        assert is_oms_managed_submit() is True
        with oms_managed():
            assert is_oms_managed_submit() is True
        assert is_oms_managed_submit() is True
    assert is_oms_managed_submit() is False
