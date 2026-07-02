"""REF-17: production-readiness fail-closed contract tests.

The original production-readiness gate accepted ``RISK_FAIL_OPEN=1``
and *passed*, allowing live trading to start with a phantom
1,000,000 INR capital placeholder. The new contract is:

* ``RISK_FAIL_OPEN=1`` is a developer override and **fails** the
  capital-fn check.
* ``RISK_FAIL_OPEN`` unset or ``0`` **passes** the check.
* :meth:`ProductionReadinessChecker.run_or_raise` raises
  :class:`ProductionReadinessError` when any check failed.
* The exception carries the full :class:`ReadinessReport` so
  operators can inspect every check.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.common.services.production_readiness import (
    ProductionReadinessChecker,
    ProductionReadinessError,
    ReadinessReport,
)


@pytest.fixture
def bare_service() -> MagicMock:
    """A mock broker service that satisfies the minimum
    attributes the readiness checks probe.

    The ``_trading_context`` and ``_gateway`` are also MagicMocks so
    the structural checks (``is None``) report the expected booleans
    without doing real work.
    """
    svc = MagicMock()
    # Make structural lookups return None for unwired fields.
    svc._trading_context = None
    svc._gateway = None
    svc._oms_risk_manager = None
    svc._http_observability = None
    svc.lifecycle = MagicMock()
    svc.lifecycle.health_snapshot.return_value = {"dhan.market_feed": {}}
    return svc


def test_run_or_raise_accepts_custom_error_factory(monkeypatch, bare_service) -> None:
    """``run_or_raise`` uses the caller-supplied factory for the exception
    type. This is the only way to assert on the *behavior* of the gate
    without coupling to ``ProductionReadinessError`` itself.
    """
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)
    monkeypatch.setenv("DHAN_CLIENT_ID", "TEST")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "tok")
    checker = ProductionReadinessChecker(bare_service)

    class _MyError(RuntimeError):
        def __init__(self, r):
            self.report = r
            super().__init__("custom")

    # With a bare mock, several structural checks will fail; we are
    # only verifying the factory override path.
    with pytest.raises(_MyError) as exc_info:
        checker.run_or_raise(error_factory=_MyError)
    assert isinstance(exc_info.value.report, ReadinessReport)
    assert not exc_info.value.report.passed


def test_run_or_raise_raises_on_failure(monkeypatch, bare_service) -> None:
    """When any check fails, run_or_raise must raise."""
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)
    monkeypatch.setenv("DHAN_CLIENT_ID", "")  # forces credentials check to fail
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "")
    monkeypatch.delenv("DHAN_PIN", raising=False)
    monkeypatch.delenv("DHAN_TOTP_SECRET", raising=False)

    checker = ProductionReadinessChecker(bare_service)
    with pytest.raises(ProductionReadinessError) as exc_info:
        checker.run_or_raise()
    assert exc_info.value.report is not None
    assert not exc_info.value.report.passed


def test_capital_fn_check_fails_when_risk_fail_open_set(monkeypatch, bare_service) -> None:
    """RISK_FAIL_OPEN=1 must FAIL the capital check (REF-17)."""
    monkeypatch.setenv("RISK_FAIL_OPEN", "1")
    monkeypatch.setenv("DHAN_CLIENT_ID", "TEST")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "tok")
    # Force all other checks to be irrelevant by passing them with a
    # bare mock. We only assert on the capital check.
    checker = ProductionReadinessChecker(bare_service)
    passed, message = checker._check_capital_fn()
    assert passed is False, message
    assert "REJECTED in production" in message


def test_capital_fn_check_passes_when_unset(monkeypatch, bare_service) -> None:
    """RISK_FAIL_OPEN unset must pass the capital check."""
    monkeypatch.delenv("RISK_FAIL_OPEN", raising=False)
    checker = ProductionReadinessChecker(bare_service)
    passed, message = checker._check_capital_fn()
    assert passed is True, message


def test_capital_fn_check_passes_when_zero(monkeypatch, bare_service) -> None:
    """RISK_FAIL_OPEN=0 must pass (the documented safe state)."""
    monkeypatch.setenv("RISK_FAIL_OPEN", "0")
    checker = ProductionReadinessChecker(bare_service)
    passed, message = checker._check_capital_fn()
    assert passed is True, message


def test_capital_fn_check_treats_whitespace_strictly(monkeypatch, bare_service) -> None:
    """Whitespace-only RISK_FAIL_OPEN must NOT be treated as 1."""
    monkeypatch.setenv("RISK_FAIL_OPEN", "  ")
    checker = ProductionReadinessChecker(bare_service)
    passed, message = checker._check_capital_fn()
    assert passed is True, message
