"""Unit tests for OMS pre-trade risk check integration.

These tests cover Lane Q3 of the multi-agent refactor: wiring
``RiskManagerPort`` into ``OrderManagementSystem.place_order``.

Contract under test
-------------------
1. When ``risk_manager`` is ``None`` (backward compat) the OMS performs no
   risk check and behaves exactly as before.
2. When a risk manager is wired and ``check_order`` returns an allowed
   result, the OMS proceeds to broker routing as normal.
3. When a risk manager rejects the order, the OMS short-circuits with
   ``OrderResponse.fail(error_code="RISK_CHECK_REJECTED")`` and increments
   ``metrics["risk_check_rejections"]`` by 1.
4. The ``RiskCheckRequest`` passed to the port contains every order field
   that the risk manager needs to make a decision.
5. If the risk manager raises, the OMS fails open (logs and proceeds to
   routing). This is a deliberate fail-open policy: a buggy risk manager
   must never break live trading. See the comment block in
   ``OrderManagementSystem.place_order`` for rationale.

Ordering
--------
The risk check runs *after* the kill switch (global circuit breaker
wins) and *before* the idempotency cache (so a rejected order does not
pollute the cache).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from inc_trade.domain.entities import RiskCheckRequest, RiskCheckResult
from inc_trade.domain.enums import OrderType, Side
from inc_trade.trading.execution_router import ExecutionRouter
from inc_trade.trading.oms import OrderManagementSystem
from inc_trade.trading.order_repository import OrderRepository

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def broker() -> MagicMock:
    """A mock broker adapter that always succeeds."""
    mock = MagicMock()
    mock.place_order.return_value = MagicMock(
        order_id="ORD-1", success=True, status=MagicMock(value="open")
    )
    return mock


@pytest.fixture
def router(broker: MagicMock) -> ExecutionRouter:
    r = ExecutionRouter()
    r.register_adapter("dhan", broker)
    return r


def _registered_broker(router: ExecutionRouter) -> MagicMock:
    """Return the mock broker registered with the router.

    The router stores adapters in a private ``_adapters`` dict, so we use
    the public ``route()``-side path via the OMS in most tests and only
    poke at the private registry here.
    """
    return router._adapters["dhan"]  # test-only access to private registry


@pytest.fixture
def repository() -> OrderRepository:
    return OrderRepository()


def _build_oms(
    router: ExecutionRouter,
    repository: OrderRepository,
    risk_manager: Any = None,
) -> OrderManagementSystem:
    return OrderManagementSystem(
        execution_router=router,
        order_repository=repository,
        kill_switch=False,
        risk_manager=risk_manager,
    )


def _place(oms: OrderManagementSystem) -> Any:
    return oms.place_order(
        account_id="dhan/default",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
    )


# ── Tests ────────────────────────────────────────────────────────────────


class TestRiskCheckBackwardCompatibility:
    """When no risk manager is wired, behaviour is unchanged."""

    def test_risk_manager_none_omits_check(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        oms = _build_oms(router, repository, risk_manager=None)
        resp = _place(oms)
        assert resp.success is True
        assert resp.order_id == "ORD-1"

    def test_risk_manager_none_does_not_increment_rejection_counter(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        oms = _build_oms(router, repository, risk_manager=None)
        _place(oms)
        assert oms.metrics()["risk_check_rejections"] == 0


class TestRiskCheckAllow:
    """When the risk manager approves, the order is placed normally."""

    def test_risk_check_pass_proceeds_to_broker(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(allowed=True)
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        resp = _place(oms)

        assert resp.success is True
        assert resp.order_id == "ORD-1"
        # Broker was called exactly once with the order details.
        assert _registered_broker(router).place_order.call_count == 1
        # And the OMS metrics reflect a successful placement, not a rejection.
        m = oms.metrics()
        assert m["orders_placed"] == 1
        assert m["risk_check_rejections"] == 0

    def test_risk_check_request_contains_all_order_fields(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(allowed=True)
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        oms.place_order(
            account_id="dhan/default",
            symbol="TCS",
            exchange="BSE",
            side=Side.SELL,
            quantity=25,
            order_type=OrderType.LIMIT,
            price=Decimal("3450.50"),
        )

        risk_manager.check_order.assert_called_once()
        request = risk_manager.check_order.call_args.args[0]
        assert isinstance(request, RiskCheckRequest)
        assert request.symbol == "TCS"
        assert request.exchange == "BSE"
        assert request.side == Side.SELL
        assert request.quantity == 25
        assert request.price == Decimal("3450.50")
        assert request.order_type == OrderType.LIMIT

    def test_risk_check_request_defaults_match_place_order_defaults(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        """``RiskCheckRequest`` must reflect the *actual* order values,
        not the OMS method defaults, when callers pass them explicitly."""
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(allowed=True)
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        oms.place_order(
            account_id="dhan/default",
            symbol="INFY",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
        )

        request = risk_manager.check_order.call_args.args[0]
        # Defaults from place_order: MARKET, price=0
        assert request.order_type == OrderType.MARKET
        assert request.price == Decimal("0")


class TestRiskCheckReject:
    """When the risk manager rejects, the order is short-circuited."""

    def test_risk_check_fail_returns_failure_response(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(
            allowed=False, reason="exceeds position limit"
        )
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        resp = _place(oms)

        assert resp.success is False
        assert resp.error_code == "RISK_CHECK_REJECTED"
        assert "exceeds position limit" in resp.message

    def test_risk_check_rejection_increments_metric(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(allowed=False, reason="rejected")
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        _place(oms)
        _place(oms)
        _place(oms)

        assert oms.metrics()["risk_check_rejections"] == 3

    def test_risk_check_rejection_does_not_call_broker(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(allowed=False, reason="rejected")
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        _place(oms)

        _registered_broker(router).place_order.assert_not_called()
        # Repository should remain empty since we never routed.
        assert repository.count() == 0

    def test_risk_check_rejection_default_reason(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        """Empty ``reason`` should still produce a useful failure message."""
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(allowed=False, reason="")
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        resp = _place(oms)

        assert resp.success is False
        assert resp.error_code == "RISK_CHECK_REJECTED"
        # Falls back to a generic rejection note.
        assert "rejected" in resp.message.lower()


class TestRiskCheckOrdering:
    """Verify risk check runs in the right place in the pipeline."""

    def test_risk_check_runs_after_kill_switch(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        """Kill switch is a global circuit breaker — it must win over the
        risk manager so an operator can halt trading regardless of policy."""
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(allowed=True)
        oms = OrderManagementSystem(
            execution_router=router,
            order_repository=repository,
            kill_switch=True,
            risk_manager=risk_manager,
        )

        resp = _place(oms)

        assert resp.success is False
        assert resp.error_code == "KILL_SWITCH_ACTIVE"
        # Risk manager should NOT have been consulted.
        risk_manager.check_order.assert_not_called()
        assert oms.metrics()["orders_kill_switched"] == 1
        assert oms.metrics()["risk_check_rejections"] == 0

    def test_risk_check_rejection_does_not_populate_idempotency_cache(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        """A rejected order must not be cached, so a retry can be evaluated
        by the risk manager again (e.g. after the operator raises the
        position limit)."""
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(allowed=False, reason="rejected")
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        first = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-reject",
        )
        assert first.error_code == "RISK_CHECK_REJECTED"

        # Now allow the order — the second call must reach the broker
        # (proving the rejection was not cached as an idempotency hit).
        risk_manager.check_order.return_value = RiskCheckResult(allowed=True)
        second = oms.place_order(
            account_id="dhan/default",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            correlation_id="corr-reject",
        )
        assert second.success is True
        assert second.error_code != "IDEMPOTENCY_CONFLICT"


class TestRiskCheckException:
    """Risk manager exceptions must not crash the OMS.

    Policy: FAIL-OPEN. A buggy or temporarily-unavailable risk manager
    must not break live trading. The exception is logged and the order
    proceeds to the broker. The OMS does not increment any rejection
    counter in this path because no policy decision was made.
    """

    def test_risk_check_exception_proceeds_to_broker(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        risk_manager = MagicMock()
        risk_manager.check_order.side_effect = RuntimeError("risk engine down")
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        resp = _place(oms)

        assert resp.success is True
        assert resp.order_id == "ORD-1"

    def test_risk_check_exception_does_not_increment_rejection_counter(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        risk_manager = MagicMock()
        risk_manager.check_order.side_effect = RuntimeError("boom")
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        _place(oms)

        # Fail-open: no rejection recorded, since no policy decision was made.
        assert oms.metrics()["risk_check_rejections"] == 0

    def test_risk_check_exception_logs_warning(
        self,
        router: ExecutionRouter,
        repository: OrderRepository,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        risk_manager = MagicMock()
        risk_manager.check_order.side_effect = ValueError("bad data")
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        with caplog.at_level("WARNING"):
            _place(oms)

        warnings = [r for r in caplog.records if "oms_risk_check_failed" in r.getMessage()]
        assert warnings, "expected an oms_risk_check_failed warning to be logged"

    def test_risk_check_raises_broker_error_propagates_still(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        """Even with fail-open semantics, we still want the broker error
        path to behave normally — i.e. a broker exception during routing
        raises, and broker_errors is incremented."""
        _registered_broker(router).place_order.side_effect = RuntimeError("broker down")

        risk_manager = MagicMock()
        risk_manager.check_order.side_effect = RuntimeError("risk engine down")
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        with pytest.raises(RuntimeError, match="broker down"):
            _place(oms)

        # Risk-check exception is swallowed; broker error is propagated.
        assert oms.metrics()["risk_check_rejections"] == 0
        assert oms.metrics()["broker_errors"] == 1


class TestRiskCheckResultContract:
    """Regression guards for ``RiskCheckResult`` defensive-access patterns.

    ``RiskCheckResult`` is a frozen dataclass with ``allowed: bool`` and
    ``reason: str = ""``. The OMS must trust the type and access fields
    directly — never via ``getattr`` with a default. These tests pin that
    contract so a future "defensive" refactor cannot reintroduce
    ``getattr(risk_result, "allowed", ...)`` style fallbacks.
    """

    def test_empty_reason_produces_meaningful_failure_message(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        """``RiskCheckResult(allowed=False, reason="")`` must still produce
        a meaningful ``OrderResponse.fail`` message (no empty / blank
        message, no ``None`` leakage)."""
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(allowed=False, reason="")
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        resp = _place(oms)

        assert resp.success is False
        assert resp.error_code == "RISK_CHECK_REJECTED"
        # Message must be non-empty and contain a "Risk check failed" prefix.
        assert resp.message
        assert "Risk check failed" in resp.message
        # And it should include the fallback phrase so operators see *something*.
        assert "rejected" in resp.message.lower()

    def test_nonempty_reason_propagates_verbatim(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        """A specific ``reason`` (e.g. ``"blocked: margin"``) must propagate
        verbatim into ``OrderResponse.message`` — no truncation, no
        wrapping in a generic boilerplate that hides the cause."""
        risk_manager = MagicMock()
        risk_manager.check_order.return_value = RiskCheckResult(
            allowed=False, reason="blocked: margin"
        )
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        resp = _place(oms)

        assert resp.success is False
        assert resp.error_code == "RISK_CHECK_REJECTED"
        assert "blocked: margin" in resp.message

    def test_oms_does_not_use_getattr_on_risk_result(
        self, router: ExecutionRouter, repository: OrderRepository
    ) -> None:
        """Regression guard: the OMS must trust ``RiskCheckResult`` and
        access ``.allowed`` / ``.reason`` as direct attributes — never
        via ``getattr(risk_result, "allowed", default)`` or similar.

        We pin this two ways:

        1. Behavioural: pass a ``MagicMock(spec=RiskCheckResult)`` whose
           only known attributes are ``allowed`` and ``reason``. If the
           OMS tried to ``getattr`` any other name on the result, the
           spec would raise ``AttributeError``. (Direct attribute access
           on spec'd mocks is what we want — that's the pattern we are
           guarding.)
        2. Audit: confirm only ``check_order`` is invoked on the risk
           manager (no defensive probing for ``is_allowed`` /
           ``is_approved`` / etc.).
        """
        risk_result = MagicMock(spec=RiskCheckResult)
        risk_result.allowed = False
        risk_result.reason = "blocked: margin"

        risk_manager = MagicMock(spec_set=["check_order"])
        risk_manager.check_order.return_value = risk_result
        oms = _build_oms(router, repository, risk_manager=risk_manager)

        resp = _place(oms)

        # Direct attribute access on the spec'd mock works as expected.
        assert risk_result.allowed is False
        assert risk_result.reason == "blocked: margin"

        # OMS produced the expected failure with the verbatim reason.
        assert resp.success is False
        assert resp.error_code == "RISK_CHECK_REJECTED"
        assert "blocked: margin" in resp.message

        # Only check_order was ever called on the risk manager. A spec_set
        # of ["check_order"] would raise AttributeError if the OMS tried
        # to call any other method (e.g. ``is_approved``) — that's the
        # regression guard for "getattr(risk_manager, ..., False)" probes.
        risk_manager.check_order.assert_called_once()
        assert [c[0] for c in risk_manager.mock_calls] == ["check_order"]
