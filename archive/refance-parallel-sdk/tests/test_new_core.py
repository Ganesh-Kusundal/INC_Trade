"""Tests for new core modules: Repository, Container, TokenStore, SessionSnapshot, TOTP."""

import asyncio
import os
import sys
import time

import pytest
from tradex.broker.auth import TokenInfo
from tradex.core.di import Container
from tradex.core.errors import ConfigurationError
from tradex.core.mfa import TOTPConfig, TOTPGenerator
from tradex.core.repository import (
    CompositeRepository,
    InMemoryRepository,
)
from tradex.core.storage import SessionSnapshot, TokenStore

# ---------------------------------------------------------------------------
# InMemoryRepository tests
# ---------------------------------------------------------------------------


class TestInMemoryRepository:
    @pytest.mark.asyncio
    async def test_put_and_get(self):
        repo = InMemoryRepository[str, str](max_size=100, default_ttl=60.0)
        await repo.put("key1", "value1")
        result = await repo.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self):
        repo = InMemoryRepository[str, str]()
        result = await repo.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_existing(self):
        repo = InMemoryRepository[str, str]()
        await repo.put("k", "v")
        removed = await repo.remove("k")
        assert removed is True
        assert await repo.get("k") is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self):
        repo = InMemoryRepository[str, str]()
        removed = await repo.remove("ghost")
        assert removed is False

    @pytest.mark.asyncio
    async def test_exists(self):
        repo = InMemoryRepository[str, str]()
        await repo.put("k", "v")
        assert await repo.exists("k") is True
        assert await repo.exists("missing") is False

    @pytest.mark.asyncio
    async def test_clear(self):
        repo = InMemoryRepository[str, str]()
        await repo.put("a", "1")
        await repo.put("b", "2")
        await repo.clear()
        assert await repo.size() == 0
        assert await repo.get("a") is None

    @pytest.mark.asyncio
    async def test_size(self):
        repo = InMemoryRepository[str, str]()
        assert await repo.size() == 0
        await repo.put("a", "1")
        assert await repo.size() == 1
        await repo.put("b", "2")
        assert await repo.size() == 2

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        repo = InMemoryRepository[str, str](default_ttl=0.01)
        await repo.put("k", "v")
        # Before expiry
        assert await repo.get("k") == "v"
        # Wait for expiry
        await asyncio.sleep(0.05)
        assert await repo.get("k") is None
        # exists should also return False after expiry
        assert await repo.exists("k") is False


# ---------------------------------------------------------------------------
# CompositeRepository tests
# ---------------------------------------------------------------------------


class TestCompositeRepository:
    @pytest.mark.asyncio
    async def test_primary_hit_returns_value(self):
        primary = InMemoryRepository[str, str]()
        fallback = InMemoryRepository[str, str]()
        composite = CompositeRepository(primary=primary, fallback=fallback)

        await primary.put("k", "primary_val")
        result = await composite.get("k")
        assert result == "primary_val"

    @pytest.mark.asyncio
    async def test_primary_miss_falls_back_to_fallback(self):
        primary = InMemoryRepository[str, str]()
        fallback = InMemoryRepository[str, str]()
        composite = CompositeRepository(primary=primary, fallback=fallback)

        await fallback.put("k", "fallback_val")
        result = await composite.get("k")
        assert result == "fallback_val"
        # Should be promoted to primary
        assert await primary.get("k") == "fallback_val"

    @pytest.mark.asyncio
    async def test_both_miss_returns_none(self):
        primary = InMemoryRepository[str, str]()
        fallback = InMemoryRepository[str, str]()
        composite = CompositeRepository(primary=primary, fallback=fallback)

        assert await composite.get("missing") is None

    @pytest.mark.asyncio
    async def test_write_goes_to_both_tiers(self):
        primary = InMemoryRepository[str, str]()
        fallback = InMemoryRepository[str, str]()
        composite = CompositeRepository(primary=primary, fallback=fallback)

        await composite.put("k", "v")
        assert await primary.get("k") == "v"
        assert await fallback.get("k") == "v"

    @pytest.mark.asyncio
    async def test_remove_goes_to_both_tiers(self):
        primary = InMemoryRepository[str, str]()
        fallback = InMemoryRepository[str, str]()
        composite = CompositeRepository(primary=primary, fallback=fallback)

        await composite.put("k", "v")
        removed = await composite.remove("k")
        assert removed is True
        assert await primary.get("k") is None
        assert await fallback.get("k") is None

    @pytest.mark.asyncio
    async def test_exists_checks_both_tiers(self):
        primary = InMemoryRepository[str, str]()
        fallback = InMemoryRepository[str, str]()
        composite = CompositeRepository(primary=primary, fallback=fallback)

        assert await composite.exists("k") is False
        await fallback.put("k", "v")
        assert await composite.exists("k") is True

    @pytest.mark.asyncio
    async def test_clear_clears_both_tiers(self):
        primary = InMemoryRepository[str, str]()
        fallback = InMemoryRepository[str, str]()
        composite = CompositeRepository(primary=primary, fallback=fallback)

        await composite.put("a", "1")
        await composite.put("b", "2")
        await composite.clear()
        assert await composite.size() == 0
        assert await primary.size() == 0
        assert await fallback.size() == 0

    @pytest.mark.asyncio
    async def test_size_returns_primary_size(self):
        primary = InMemoryRepository[str, str]()
        fallback = InMemoryRepository[str, str]()
        composite = CompositeRepository(primary=primary, fallback=fallback)

        await composite.put("a", "1")
        assert await composite.size() == 1

    @pytest.mark.asyncio
    async def test_no_fallback_works_alone(self):
        primary = InMemoryRepository[str, str]()
        composite = CompositeRepository(primary=primary)

        await composite.put("k", "v")
        assert await composite.get("k") == "v"
        assert await composite.exists("k") is True
        assert await composite.size() == 1


# ---------------------------------------------------------------------------
# Container (DI) tests
# ---------------------------------------------------------------------------


class TestContainer:
    def test_register_instance_and_resolve(self):
        container = Container()
        obj = {"key": "value"}
        container.register_instance(obj)
        resolved = container.resolve(dict)
        assert resolved is obj

    def test_register_instance_with_interface(self):
        container = Container()
        obj = "hello"
        container.register_instance(obj, interface=str)
        resolved = container.resolve(str)
        assert resolved == "hello"

    def test_register_factory_and_resolve(self):
        container = Container()
        call_count = [0]

        def factory():
            call_count[0] += 1
            return {"created": call_count[0]}

        container.register_factory(factory, dict)
        result1 = container.resolve(dict)
        result2 = container.resolve(dict)
        # Factory is called once, result is cached as singleton
        assert result1 is result2
        assert call_count[0] == 1

    def test_register_class_and_resolve(self):
        container = Container()

        class MyService:
            def __init__(self):
                self.value = 42

        container.register_class(MyService)
        resolved = container.resolve(MyService)
        assert resolved.value == 42

    def test_register_class_with_interface(self):
        container = Container()

        class MyService:
            def __init__(self):
                self.value = 99

        class MyInterface:
            pass

        container.register_class(MyService, interface=MyInterface)
        resolved = container.resolve(MyInterface)
        assert resolved.value == 99
        assert isinstance(resolved, MyService)

    def test_resolve_unregistered_raises(self):
        container = Container()
        with pytest.raises(ConfigurationError):
            container.resolve(str)

    def test_has_returns_true_for_registered(self):
        container = Container()
        container.register_instance(42, int)
        assert container.has(int) is True
        assert container.has(str) is False

    def test_has_checks_factories(self):
        container = Container()
        container.register_factory(lambda: "x", str)
        assert container.has(str) is True

    def test_create_child_inherits_parent(self):
        parent = Container()
        parent.register_instance("parent_val", str)

        child = parent.create_child()
        assert child.resolve(str) == "parent_val"

    def test_create_child_can_override(self):
        parent = Container()
        parent.register_instance("parent_val", str)

        child = parent.create_child()
        child.register_instance("child_val", str)
        assert child.resolve(str) == "child_val"
        # Parent still has its own value
        assert parent.resolve(str) == "parent_val"

    def test_create_child_has_inherits(self):
        parent = Container()
        parent.register_instance(42, int)

        child = parent.create_child()
        assert child.has(int) is True

    def test_clear_resets_registrations(self):
        container = Container()
        container.register_instance("val", str)
        container.register_class(int)
        container.clear()
        with pytest.raises(ConfigurationError):
            container.resolve(str)

    def test_registered_types(self):
        container = Container()
        container.register_instance("a", str)
        container.register_instance(1, int)
        types = container.registered_types
        assert str in types
        assert int in types

    def test_registered_types_includes_parent(self):
        parent = Container()
        parent.register_instance("a", str)
        child = parent.create_child()
        child.register_instance(1, int)
        types = child.registered_types
        assert str in types
        assert int in types


# ---------------------------------------------------------------------------
# TokenStore tests
# ---------------------------------------------------------------------------


class TestTokenStore:
    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        snapshot = SessionSnapshot(
            broker="test_broker",
            client_id="client_123",
            access_token="at_abc",
            refresh_token="rt_xyz",
            expires_at=time.time() + 3600,
            issued_at=time.time(),
        )
        await store.save(snapshot)
        loaded = await store.load("test_broker", "client_123")
        assert loaded is not None
        assert loaded.broker == "test_broker"
        assert loaded.client_id == "client_123"
        assert loaded.access_token == "at_abc"
        assert loaded.refresh_token == "rt_xyz"

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        loaded = await store.load("no_broker", "no_client")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        snapshot = SessionSnapshot(broker="b", client_id="c", access_token="a")
        await store.save(snapshot)
        deleted = await store.delete("b", "c")
        assert deleted is True
        loaded = await store.load("b", "c")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        deleted = await store.delete("x", "y")
        assert deleted is False

    def test_is_valid_non_expired(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        snapshot = SessionSnapshot(
            broker="b",
            client_id="c",
            expires_at=time.time() + 3600,
        )
        assert store.is_valid(snapshot) is True

    def test_is_valid_expired(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        snapshot = SessionSnapshot(
            broker="b",
            client_id="c",
            expires_at=time.time() - 1,  # expired
        )
        assert store.is_valid(snapshot) is False

    def test_is_valid_no_expiry(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        snapshot = SessionSnapshot(broker="b", client_id="c", expires_at=0.0)
        assert store.is_valid(snapshot) is True

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix file permissions not applicable")
    @pytest.mark.asyncio
    async def test_file_permissions_0600(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        snapshot = SessionSnapshot(broker="b", client_id="c", access_token="t")
        await store.save(snapshot)
        path = tmp_path / "b_c.json"
        assert path.exists()
        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600

    @pytest.mark.asyncio
    async def test_list_sessions(self, tmp_path):
        store = TokenStore(storage_dir=str(tmp_path))
        for i in range(3):
            await store.save(
                SessionSnapshot(
                    broker=f"b{i}",
                    client_id=f"c{i}",
                    access_token=f"t{i}",
                )
            )
        sessions = await store.list_sessions()
        assert len(sessions) == 3


# ---------------------------------------------------------------------------
# SessionSnapshot tests
# ---------------------------------------------------------------------------


class TestSessionSnapshot:
    def test_from_token_info_roundtrip(self):
        token = TokenInfo(
            access_token="at_test",
            refresh_token="rt_test",
            expires_at=1700000000.0,
            issued_at=1699996400.0,
        )
        snapshot = SessionSnapshot.from_token_info(
            broker="dhan",
            client_id="12345",
            token=token,
            extra_field="extra_val",
        )
        assert snapshot.broker == "dhan"
        assert snapshot.client_id == "12345"
        assert snapshot.access_token == "at_test"
        assert snapshot.refresh_token == "rt_test"
        assert snapshot.expires_at == 1700000000.0
        assert snapshot.issued_at == 1699996400.0
        assert snapshot.metadata == {"extra_field": "extra_val"}

    def test_to_token_info_roundtrip(self):
        snapshot = SessionSnapshot(
            broker="dhan",
            client_id="12345",
            access_token="at_xyz",
            refresh_token="rt_pqr",
            expires_at=1700000000.0,
            issued_at=1699996400.0,
        )
        token = snapshot.to_token_info()
        assert token.access_token == "at_xyz"
        assert token.refresh_token == "rt_pqr"
        assert token.expires_at == 1700000000.0
        assert token.issued_at == 1699996400.0

    def test_full_roundtrip(self):
        original_token = TokenInfo(
            access_token="at_full",
            refresh_token="rt_full",
            expires_at=1700000000.0,
            issued_at=1699996400.0,
        )
        snapshot = SessionSnapshot.from_token_info(
            broker="dhan",
            client_id="99",
            token=original_token,
        )
        restored_token = snapshot.to_token_info()
        assert restored_token.access_token == original_token.access_token
        assert restored_token.refresh_token == original_token.refresh_token
        assert restored_token.expires_at == original_token.expires_at
        assert restored_token.issued_at == original_token.issued_at

    def test_default_metadata_initialised(self):
        snapshot = SessionSnapshot()
        assert snapshot.metadata == {}


# ---------------------------------------------------------------------------
# TOTPGenerator tests
# ---------------------------------------------------------------------------


class TestTOTPGenerator:
    def _make_generator(self, secret="JBSWY3DPEHPK3PXP", digits=6, interval=30):
        config = TOTPConfig(secret=secret, digits=digits, interval=interval)
        return TOTPGenerator(config)

    def test_generate_returns_correct_length(self):
        gen = self._make_generator(digits=6)
        code = gen.generate()
        assert len(code) == 6
        assert code.isdigit()

    def test_generate_8_digits(self):
        gen = self._make_generator(digits=8)
        code = gen.generate()
        assert len(code) == 8

    def test_verify_with_correct_code(self):
        gen = self._make_generator()
        # Generate at a fixed timestamp, then verify at the same timestamp
        fixed_ts = 1700000000.0
        code = gen.generate(timestamp=fixed_ts)
        # We need to verify at that same time window
        # Since verify() uses time.time(), we patch it
        import unittest.mock as mock

        with mock.patch("tradex.core.mfa.time") as mock_time:
            mock_time.time.return_value = fixed_ts
            mock_time.monotonic = time.monotonic
            assert gen.verify(code, window=0) is True

    def test_verify_with_wrong_code_returns_false(self):
        gen = self._make_generator()
        import unittest.mock as mock

        with mock.patch("tradex.core.mfa.time") as mock_time:
            mock_time.time.return_value = 1700000000.0
            mock_time.monotonic = time.monotonic
            assert gen.verify("000000", window=0) is False

    def test_verify_with_window_tolerance(self):
        gen = self._make_generator()
        fixed_ts = 1700000000.0
        # Generate code for the PREVIOUS interval
        previous_ts = fixed_ts - 30  # one interval before
        code = gen.generate(timestamp=previous_ts)

        # Verify at current time with window=1 should accept the previous code
        import unittest.mock as mock

        with mock.patch("tradex.core.mfa.time") as mock_time:
            mock_time.time.return_value = fixed_ts
            mock_time.monotonic = time.monotonic
            assert gen.verify(code, window=1) is True

    def test_verify_with_window_0_rejects_stale(self):
        gen = self._make_generator()
        fixed_ts = 1700000000.0
        previous_ts = fixed_ts - 30
        code = gen.generate(timestamp=previous_ts)

        import unittest.mock as mock

        with mock.patch("tradex.core.mfa.time") as mock_time:
            mock_time.time.return_value = fixed_ts
            mock_time.monotonic = time.monotonic
            assert gen.verify(code, window=0) is False

    def test_time_remaining_positive(self):
        gen = self._make_generator(interval=30)
        remaining = gen.time_remaining()
        assert isinstance(remaining, int)
        assert 1 <= remaining <= 30

    def test_from_secret_classmethod(self):
        gen = TOTPGenerator.from_secret("JBSWY3DPEHPK3PXP", digits=6, interval=30)
        code = gen.generate()
        assert len(code) == 6

    def test_generate_deterministic(self):
        """Same timestamp + same secret = same code."""
        gen = self._make_generator()
        ts = 1700000015.0
        code1 = gen.generate(timestamp=ts)
        code2 = gen.generate(timestamp=ts)
        assert code1 == code2
