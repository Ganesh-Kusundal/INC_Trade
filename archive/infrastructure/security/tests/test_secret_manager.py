"""Tests for secret manager and encrypted token store."""

import pytest
from cryptography.fernet import Fernet

from infrastructure.security.secret_manager import (
    EncryptedTokenStore,
    EncryptionNotConfiguredError,
    SecretManager,
)


@pytest.fixture
def encryption_key():
    """Generate a test encryption key."""
    return Fernet.generate_key().decode()


@pytest.fixture
def secret_manager(encryption_key):
    """Create a SecretManager instance."""
    SecretManager.reset_instance()
    manager = SecretManager(encryption_key=encryption_key)
    yield manager
    SecretManager.reset_instance()


@pytest.fixture
def temp_token_file(tmp_path):
    """Create a temporary token state file path."""
    return tmp_path / "test-token-state.json"


class TestSecretManager:
    """Test SecretManager class."""

    def test_initialization_with_key(self, encryption_key):
        manager = SecretManager(encryption_key=encryption_key)
        assert manager.is_encryption_enabled is True

    def test_initialization_without_key(self, monkeypatch):
        monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
        SecretManager.reset_instance()
        manager = SecretManager()
        assert manager.is_encryption_enabled is False
        SecretManager.reset_instance()

    def test_initialization_from_env(self, encryption_key, monkeypatch):
        monkeypatch.setenv("SECRET_ENCRYPTION_KEY", encryption_key)
        SecretManager.reset_instance()
        manager = SecretManager()
        assert manager.is_encryption_enabled is True
        SecretManager.reset_instance()

    def test_encrypt_decrypt(self, secret_manager):
        plaintext = "test_secret_value"
        ciphertext = secret_manager.encrypt(plaintext)
        assert ciphertext != plaintext
        decrypted = secret_manager.decrypt(ciphertext)
        assert decrypted == plaintext

    def test_encrypt_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
        SecretManager.reset_instance()
        manager = SecretManager()
        with pytest.raises(EncryptionNotConfiguredError):
            manager.encrypt("test")
        SecretManager.reset_instance()

    def test_decrypt_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
        SecretManager.reset_instance()
        manager = SecretManager()
        with pytest.raises(EncryptionNotConfiguredError):
            manager.decrypt("test")
        SecretManager.reset_instance()

    def test_generate_key(self, secret_manager):
        key = secret_manager.generate_key()
        assert isinstance(key, str)
        assert len(key) > 0
        # Should be valid Fernet key
        Fernet(key.encode())

    def test_singleton_pattern(self, encryption_key):
        SecretManager.reset_instance()
        manager1 = SecretManager.get_instance(encryption_key=encryption_key)
        manager2 = SecretManager.get_instance()
        assert manager1 is manager2
        SecretManager.reset_instance()

    def test_reset_instance(self, encryption_key):
        SecretManager.reset_instance()
        manager1 = SecretManager.get_instance(encryption_key=encryption_key)
        SecretManager.reset_instance()
        manager2 = SecretManager.get_instance()
        assert manager1 is not manager2
        SecretManager.reset_instance()


class TestEncryptedTokenStore:
    """Test EncryptedTokenStore class."""

    def test_save_and_load_unencrypted(self, temp_token_file, monkeypatch):
        monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
        SecretManager.reset_instance()

        store = EncryptedTokenStore(temp_token_file)
        state = {"access_token": "test_token", "source": "STATIC"}
        store.save(state)

        loaded = store.load()
        assert loaded is not None
        assert loaded["access_token"] == "test_token"
        assert loaded["source"] == "STATIC"
        SecretManager.reset_instance()

    def test_save_and_load_encrypted(self, temp_token_file, encryption_key, monkeypatch):
        monkeypatch.setenv("SECRET_ENCRYPTION_KEY", encryption_key)
        SecretManager.reset_instance()

        store = EncryptedTokenStore(temp_token_file)
        state = {"access_token": "test_token", "source": "STATIC"}
        store.save(state)

        loaded = store.load()
        assert loaded is not None
        assert loaded["access_token"] == "test_token"
        assert loaded["source"] == "STATIC"

        # File should contain encrypted content
        raw_content = temp_token_file.read_text()
        assert raw_content.startswith("gAAAAA") or raw_content.startswith("Zg==")
        SecretManager.reset_instance()

    def test_load_nonexistent_file(self, temp_token_file):
        store = EncryptedTokenStore(temp_token_file)
        loaded = store.load()
        assert loaded is None

    def test_rotate_token(self, temp_token_file, encryption_key, monkeypatch):
        monkeypatch.setenv("SECRET_ENCRYPTION_KEY", encryption_key)
        SecretManager.reset_instance()

        store = EncryptedTokenStore(temp_token_file)
        old_state = {"access_token": "old_token", "source": "STATIC"}
        store.save(old_state)

        new_state = {"access_token": "new_token", "source": "TOTP"}
        store.rotate_token(new_state)

        loaded = store.load()
        assert loaded is not None
        assert loaded["access_token"] == "new_token"
        assert loaded["source"] == "TOTP"
        SecretManager.reset_instance()

    def test_delete_token(self, temp_token_file, encryption_key, monkeypatch):
        monkeypatch.setenv("SECRET_ENCRYPTION_KEY", encryption_key)
        SecretManager.reset_instance()

        store = EncryptedTokenStore(temp_token_file)
        state = {"access_token": "test_token"}
        store.save(state)
        assert temp_token_file.exists()

        store.delete()
        assert not temp_token_file.exists()
        SecretManager.reset_instance()

    def test_creates_parent_directory(self, tmp_path):
        nested_path = tmp_path / "nested" / "dir" / "token.json"
        EncryptedTokenStore(nested_path)
        assert nested_path.parent.exists()

    def test_secure_permissions(self, temp_token_file, monkeypatch):
        monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
        SecretManager.reset_instance()

        store = EncryptedTokenStore(temp_token_file)
        state = {"access_token": "test_token"}
        store.save(state)

        # Check file permissions (should be 0o600)
        stat = temp_token_file.stat()
        assert stat.st_mode & 0o777 == 0o600
        SecretManager.reset_instance()


class TestBackwardCompatibility:
    """Test backward compatibility with unencrypted tokens."""

    def test_load_unencrypted_when_encryption_enabled(self, temp_token_file, encryption_key, monkeypatch):
        """Should load unencrypted file with warning when encryption is enabled."""
        # First save unencrypted
        monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
        SecretManager.reset_instance()

        store_unencrypted = EncryptedTokenStore(temp_token_file)
        state = {"access_token": "unencrypted_token"}
        store_unencrypted.save(state)

        # Now enable encryption and load
        monkeypatch.setenv("SECRET_ENCRYPTION_KEY", encryption_key)
        SecretManager.reset_instance()

        store_encrypted = EncryptedTokenStore(temp_token_file)
        loaded = store_encrypted.load()
        assert loaded is not None
        assert loaded["access_token"] == "unencrypted_token"
        SecretManager.reset_instance()

    def test_detect_encrypted_format(self, temp_token_file, encryption_key, monkeypatch):
        """Should detect and decrypt encrypted files."""
        monkeypatch.setenv("SECRET_ENCRYPTION_KEY", encryption_key)
        SecretManager.reset_instance()

        store = EncryptedTokenStore(temp_token_file)
        state = {"access_token": "encrypted_token"}
        store.save(state)

        # Verify it's detected as encrypted
        raw_content = temp_token_file.read_text()
        assert store._is_encrypted_format(raw_content) is True
        SecretManager.reset_instance()


class TestSecretManagerThreadSafety:
    """Fix #7: SecretManager singleton must be thread-safe (DCLP)."""

    def test_concurrent_get_instance_returns_same(self):
        """100 threads calling get_instance() all get the same instance."""
        import concurrent.futures

        SecretManager.reset_instance()
        instances = []

        def get_it():
            inst = SecretManager.get_instance()
            instances.append(id(inst))

        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as pool:
            futures = [pool.submit(get_it) for _ in range(100)]
            for f in futures:
                f.result()

        # All instances must be the same object
        assert len(set(instances)) == 1
        SecretManager.reset_instance()
