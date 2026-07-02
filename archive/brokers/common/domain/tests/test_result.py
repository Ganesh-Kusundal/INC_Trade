"""Tests for domain.result — GatewayResult monadic result type."""

from __future__ import annotations

from domain.result import GatewayResult, ResultMetadata


class TestResultMetadata:
    def test_defaults(self):
        m = ResultMetadata()
        assert m.source == ""
        assert m.latency_ms == 0.0

    def test_custom_values(self):
        m = ResultMetadata(source="dhan", latency_ms=42.5)
        assert m.source == "dhan"
        assert m.latency_ms == 42.5


class TestGatewayResultSuccess:
    def test_success_factory(self):
        r = GatewayResult.success(42)
        assert r.is_success
        assert not r.is_failure
        assert r.value == 42
        assert r.error is None

    def test_success_with_metadata(self):
        meta = ResultMetadata(source="cache", latency_ms=1.0)
        r = GatewayResult.success("data", metadata=meta)
        assert r.is_success
        assert r.metadata.source == "cache"

    def test_bool_true_for_success(self):
        assert bool(GatewayResult.success(1))

    def test_str_success(self):
        r = GatewayResult.success(42)
        assert "Success" in str(r)


class TestGatewayResultFailure:
    def test_failure_factory(self):
        r = GatewayResult.failure("oops")
        assert r.is_failure
        assert not r.is_success
        assert r.error == "oops"
        assert r.value is None

    def test_failure_with_metadata(self):
        meta = ResultMetadata(source="broker", latency_ms=100.0)
        r = GatewayResult.failure("timeout", metadata=meta)
        assert r.metadata.latency_ms == 100.0

    def test_bool_false_for_failure(self):
        assert not bool(GatewayResult.failure("err"))

    def test_str_failure(self):
        r = GatewayResult.failure("err")
        assert "Failure" in str(r)


class TestGatewayResultMap:
    def test_map_on_success(self):
        r = GatewayResult.success(10).map(lambda x: x * 2)
        assert r.is_success
        assert r.value == 20

    def test_map_on_failure_propagates_error(self):
        r = GatewayResult.failure("err").map(lambda x: x * 2)
        assert r.is_failure
        assert r.error == "err"

    def test_map_exception_becomes_failure(self):
        r = GatewayResult.success(10).map(lambda x: 1 / 0)
        assert r.is_failure

    def test_map_preserves_metadata(self):
        meta = ResultMetadata(source="test")
        r = GatewayResult.success(5, metadata=meta).map(lambda x: x + 1)
        assert r.metadata.source == "test"


class TestGatewayResultFlatMap:
    def test_flat_map_success_chain(self):
        r = GatewayResult.success(10).flat_map(lambda x: GatewayResult.success(x + 5))
        assert r.is_success
        assert r.value == 15

    def test_flat_map_to_failure(self):
        r = GatewayResult.success(10).flat_map(lambda x: GatewayResult.failure("nope"))
        assert r.is_failure

    def test_flat_map_on_failure(self):
        r = GatewayResult.failure("err").flat_map(lambda x: GatewayResult.success(x))
        assert r.is_failure

    def test_flat_map_exception_becomes_failure(self):
        def boom(x):
            raise ValueError("boom")

        r = GatewayResult.success(10).flat_map(boom)
        assert r.is_failure


class TestGatewayResultRecover:
    def test_recover_from_failure(self):
        r = GatewayResult.failure("err").recover(lambda e: "fallback")
        assert r.is_success
        assert r.value == "fallback"

    def test_recover_on_success_is_noop(self):
        r = GatewayResult.success(42).recover(lambda e: "fallback")
        assert r.is_success
        assert r.value == 42

    def test_recover_exception_becomes_failure(self):
        r = GatewayResult.failure("err").recover(lambda e: 1 / 0)
        assert r.is_failure


class TestGatewayResultGetOrElse:
    def test_returns_value_on_success(self):
        assert GatewayResult.success(42).get_or_else(0) == 42

    def test_returns_default_on_failure(self):
        assert GatewayResult.failure("err").get_or_else(0) == 0
