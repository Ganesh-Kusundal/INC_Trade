"""Tests for the Dependency Injection Container.

Tests cover:
- Singleton scope (same instance)
- Transient scope (different instance)
- Request scope (same within request, different across requests)
- register_instance
- reset
- Thread safety
- Circular dependency detection
"""

import threading

import pytest

from infrastructure.di import CircularDependencyError, ServiceNotFoundError, container
from infrastructure.di_scopes import NoActiveRequestScope, request_scope


class TestContainerSingleton:
    """Test singleton scope behavior."""

    def setup_method(self):
        """Reset container before each test."""
        container.reset()

    def test_singleton_returns_same_instance(self):
        """Singleton factory is called once, same instance returned."""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return {"id": call_count}

        container.register("singleton_svc", factory, scope="singleton")

        result1 = container.resolve("singleton_svc")
        result2 = container.resolve("singleton_svc")

        assert result1 is result2
        assert call_count == 1

    def test_singleton_with_class(self):
        """Singleton works with class constructor."""
        container.register("list", list, scope="singleton")

        result1 = container.resolve("list")
        result2 = container.resolve("list")

        assert result1 is result2
        assert isinstance(result1, list)

    def test_singleton_caches_instance(self):
        """Singleton caches the created instance."""
        instances = []

        def factory():
            obj = object()
            instances.append(obj)
            return obj

        container.register("cached", factory, scope="singleton")

        for _ in range(5):
            container.resolve("cached")

        assert len(instances) == 1


class TestContainerTransient:
    """Test transient scope behavior."""

    def setup_method(self):
        """Reset container before each test."""
        container.reset()

    def test_transient_returns_different_instances(self):
        """Transient factory creates new instance each time."""
        container.register("transient_svc", object, scope="transient")

        result1 = container.resolve("transient_svc")
        result2 = container.resolve("transient_svc")

        assert result1 is not result2

    def test_transient_factory_called_each_time(self):
        """Transient factory is called on each resolve."""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return call_count

        container.register("counter", factory, scope="transient")

        results = [container.resolve("counter") for _ in range(5)]

        assert results == [1, 2, 3, 4, 5]


class TestContainerRequestScope:
    """Test request scope behavior."""

    def setup_method(self):
        """Reset container before each test."""
        container.reset()

    def test_request_scope_same_within_request(self):
        """Request-scoped service returns same instance within a request."""
        container.register("request_svc", object, scope="request")

        with request_scope():
            result1 = container.resolve("request_svc")
            result2 = container.resolve("request_svc")

            assert result1 is result2

    def test_request_scope_different_across_requests(self):
        """Request-scoped service returns different instances across requests."""
        container.register("request_svc", object, scope="request")

        with request_scope():
            result1 = container.resolve("request_svc")

        with request_scope():
            result2 = container.resolve("request_svc")

        assert result1 is not result2

    def test_request_scope_outside_context_raises(self):
        """Request-scoped service raises error outside request_scope()."""
        container.register("request_svc", object, scope="request")

        with pytest.raises(NoActiveRequestScope):
            container.resolve("request_svc")

    def test_request_scope_nested(self):
        """Nested request scopes each get their own instances."""
        container.request_scoped_svc = None
        container.register("nested_svc", object, scope="request")

        with request_scope():
            outer_result = container.resolve("nested_svc")

            with request_scope():
                inner_result = container.resolve("nested_svc")

                # Inner scope has its own instance
                assert inner_result is not outer_result

            # After inner scope exits, outer still has its instance
            outer_again = container.resolve("nested_svc")
            assert outer_again is outer_result


class TestContainerRegisterInstance:
    """Test register_instance behavior."""

    def setup_method(self):
        """Reset container before each test."""
        container.reset()

    def test_register_instance(self):
        """Pre-created instance is returned on resolve."""
        my_instance = {"key": "value"}
        container.register_instance("config", my_instance)

        result = container.resolve("config")
        assert result is my_instance

    def test_register_instance_overwrites_factory(self):
        """register_instance takes precedence over factory."""
        container.register("svc", lambda: "from_factory", scope="singleton")
        container.register_instance("svc", "from_instance")

        result = container.resolve("svc")
        assert result == "from_instance"

    def test_register_instance_is_singleton(self):
        """Registered instance always returns same object."""
        my_instance = object()
        container.register_instance("singleton", my_instance)

        result1 = container.resolve("singleton")
        result2 = container.resolve("singleton")

        assert result1 is my_instance
        assert result2 is my_instance


class TestContainerReset:
    """Test container reset behavior."""

    def test_reset_clears_registrations(self):
        """Reset clears all registered services."""
        container.register("svc1", lambda: 1)
        container.register("svc2", lambda: 2)
        container.register_instance("svc3", 3)

        container.reset()

        assert not container.has("svc1")
        assert not container.has("svc2")
        assert not container.has("svc3")

    def test_reset_clears_singletons(self):
        """Reset clears cached singleton instances."""
        container.register("svc", lambda: object(), scope="singleton")
        instance1 = container.resolve("svc")

        container.reset()

        container.register("svc", lambda: object(), scope="singleton")
        instance2 = container.resolve("svc")

        assert instance1 is not instance2

    def test_reset_allows_reregistration(self):
        """After reset, services can be re-registered."""
        container.register("svc", lambda: "old")
        container.reset()
        container.register("svc", lambda: "new")

        assert container.resolve("svc") == "new"


class TestContainerHas:
    """Test has() method."""

    def test_has_returns_true_for_registered(self):
        """has() returns True for registered services."""
        container.register("svc", lambda: 1)
        container.register_instance("inst", 2)

        assert container.has("svc")
        assert container.has("inst")

    def test_has_returns_false_for_unregistered(self):
        """has() returns False for unregistered services."""
        assert not container.has("nonexistent")


class TestContainerRegistrations:
    """Test registrations() method."""

    def test_registrations_returns_all(self):
        """registrations() returns all registered services."""
        container.register("svc1", lambda: 1, scope="singleton")
        container.register("svc2", lambda: 2, scope="transient")
        container.register("svc3", lambda: 3, scope="request")
        container.register_instance("svc4", 4)

        regs = container.registrations()

        assert regs["svc1"] == "singleton"
        assert regs["svc2"] == "transient"
        assert regs["svc3"] == "request"
        assert regs["svc4"] == "instance"


class TestContainerErrorHandling:
    """Test error handling."""

    def test_resolve_unregistered_raises(self):
        """Resolving unregistered service raises ServiceNotFoundError."""
        with pytest.raises(ServiceNotFoundError, match="not registered"):
            container.resolve("nonexistent")

    def test_invalid_scope_raises(self):
        """Registering with invalid scope raises ValueError."""
        with pytest.raises(ValueError, match="Invalid scope"):
            container.register("svc", lambda: 1, scope="invalid")

    def test_reraise_error(self):
        """Factory exceptions propagate."""
        def failing_factory():
            raise RuntimeError("Factory failed")

        container.register("failing", failing_factory)

        with pytest.raises(RuntimeError, match="Factory failed"):
            container.resolve("failing")


class TestCircularDependency:
    """Test circular dependency detection."""

    def setup_method(self):
        """Reset container before each test."""
        container.reset()

    def test_self_referencing_singleton(self):
        """Self-referencing singleton detected."""
        container.register("self_ref", lambda: container.resolve("self_ref"), scope="singleton")

        with pytest.raises(CircularDependencyError, match="self_ref"):
            container.resolve("self_ref")

    def test_mutual_dependency_detected(self):
        """Mutual dependency detected."""
        def factory_a():
            return container.resolve("svc_b")

        def factory_b():
            return container.resolve("svc_a")

        container.register("svc_a", factory_a, scope="singleton")
        container.register("svc_b", factory_b, scope="singleton")

        with pytest.raises(CircularDependencyError):
            container.resolve("svc_a")

    def test_three_way_cycle_detected(self):
        """Three-way circular dependency detected."""
        def factory_a():
            return container.resolve("svc_b")

        def factory_b():
            return container.resolve("svc_c")

        def factory_c():
            return container.resolve("svc_a")

        container.register("svc_a", factory_a, scope="singleton")
        container.register("svc_b", factory_b, scope="singleton")
        container.register("svc_c", factory_c, scope="singleton")

        with pytest.raises(CircularDependencyError):
            container.resolve("svc_a")


class TestContainerThreadSafety:
    """Test thread safety."""

    def setup_method(self):
        """Reset container before each test."""
        container.reset()

    def test_concurrent_singleton_resolution(self):
        """Concurrent resolution of singleton returns same instance."""
        container.register("thread_singleton", object, scope="singleton")
        results = []
        errors = []

        def resolve_service():
            try:
                result = container.resolve("thread_singleton")
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=resolve_service) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 50
        # All should be the same instance
        assert all(r is results[0] for r in results)

    def test_concurrent_transient_resolution(self):
        """Concurrent resolution of transient returns different instances."""
        container.register("thread_transient", object, scope="transient")
        results = []
        errors = []

        def resolve_service():
            try:
                result = container.resolve("thread_transient")
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=resolve_service) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 50
        # All should be different instances
        assert len({id(r) for r in results}) == 50

    def test_concurrent_registration_and_resolution(self):
        """Concurrent registration and resolution is safe."""
        errors = []

        def register_and_resolve(name):
            try:
                container.register(name, lambda n=name: n, scope="singleton")
                result = container.resolve(name)
                if result != name:
                    errors.append(f"Expected {name}, got {result}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=register_and_resolve, args=(f"svc_{i}",))
            for i in range(50)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        for i in range(50):
            assert container.has(f"svc_{i}")

    def test_concurrent_reset_safety(self):
        """Concurrent reset is safe."""
        container.register("svc", lambda: 1)
        errors = []

        def reset_container():
            try:
                container.reset()
            except Exception as e:
                errors.append(e)

        def resolve_service():
            try:
                # May raise ServiceNotFoundError after reset, that's OK
                container.resolve("svc")
            except ServiceNotFoundError:
                pass
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(10):
            threads.append(threading.Thread(target=reset_container))
            threads.append(threading.Thread(target=resolve_service))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No unexpected errors (ServiceNotFoundError is expected during reset)
        assert all(not isinstance(e, (RuntimeError, TypeError)) for e in errors)


class TestModuleLevelContainer:
    """Test the module-level container singleton."""

    def test_container_is_singleton(self):
        """Module-level container is a single instance."""
        from infrastructure.di import container as c1
        from infrastructure.di import container as c2

        assert c1 is c2

    def test_container_basic_functionality(self):
        """Module-level container works for basic operations."""
        container.reset()
        container.register("test_svc", lambda: 42)
        assert container.resolve("test_svc") == 42
        container.reset()
