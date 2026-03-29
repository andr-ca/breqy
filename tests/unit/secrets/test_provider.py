"""Tests for SecretProvider implementations."""
from __future__ import annotations

import pytest

from breqy.secrets.provider import EnvSecretProvider, SecretProvider


def test_secret_provider_is_abstract():
    """SecretProvider cannot be instantiated directly."""
    import inspect
    assert inspect.isabstract(SecretProvider)


def test_env_secret_provider_set_and_get(monkeypatch):
    """EnvSecretProvider round-trips a secret through env vars."""
    provider = EnvSecretProvider()
    provider.set("mykey", "myvalue")
    assert provider.get("mykey") == "myvalue"


def test_env_secret_provider_get_missing(monkeypatch):
    """EnvSecretProvider returns None for unknown key."""
    provider = EnvSecretProvider()
    # ensure the key doesn't exist from a previous test
    monkeypatch.delenv("BREQY_SECRET_NO_SUCH_KEY_XYZ", raising=False)
    assert provider.get("no_such_key_xyz") is None


def test_env_secret_provider_delete(monkeypatch):
    """EnvSecretProvider deletes a key."""
    provider = EnvSecretProvider()
    provider.set("delkey", "delvalue")
    provider.delete("delkey")
    assert provider.get("delkey") is None


def test_env_secret_provider_delete_missing_no_error():
    """EnvSecretProvider.delete() on non-existent key does not raise."""
    provider = EnvSecretProvider()
    provider.delete("key_that_does_not_exist_abc123")  # must not raise


# --- FileSecretProvider tests ---


class TestFileSecretProvider:
    """Tests for file-based secret storage (keyring fallback)."""

    def test_set_and_get(self, tmp_path):
        """FileSecretProvider round-trips a secret through a file."""
        from breqy.secrets.provider import FileSecretProvider
        provider = FileSecretProvider(base_dir=tmp_path)
        provider.set("mykey", "myvalue")
        assert provider.get("mykey") == "myvalue"

    def test_get_missing_returns_none(self, tmp_path):
        """FileSecretProvider returns None for unknown key."""
        from breqy.secrets.provider import FileSecretProvider
        provider = FileSecretProvider(base_dir=tmp_path)
        assert provider.get("no_such_key") is None

    def test_delete_removes_key(self, tmp_path):
        """FileSecretProvider.delete() removes the stored secret."""
        from breqy.secrets.provider import FileSecretProvider
        provider = FileSecretProvider(base_dir=tmp_path)
        provider.set("delkey", "delvalue")
        provider.delete("delkey")
        assert provider.get("delkey") is None

    def test_delete_missing_no_error(self, tmp_path):
        """FileSecretProvider.delete() on non-existent key does not raise."""
        from breqy.secrets.provider import FileSecretProvider
        provider = FileSecretProvider(base_dir=tmp_path)
        provider.delete("key_that_does_not_exist")  # must not raise

    def test_creates_base_dir(self, tmp_path):
        """FileSecretProvider creates base_dir if it doesn't exist."""
        from breqy.secrets.provider import FileSecretProvider
        subdir = tmp_path / "secrets" / "nested"
        provider = FileSecretProvider(base_dir=subdir)
        provider.set("testkey", "testvalue")
        assert provider.get("testkey") == "testvalue"
        assert subdir.exists()

    def test_file_permissions_restrictive(self, tmp_path):
        """Secret files should have restrictive permissions (owner-only)."""
        import stat
        from breqy.secrets.provider import FileSecretProvider
        provider = FileSecretProvider(base_dir=tmp_path)
        provider.set("permkey", "permvalue")
        secret_file = tmp_path / "permkey"
        mode = secret_file.stat().st_mode
        # Only owner should have read/write
        assert not (mode & stat.S_IRGRP), "Group should not have read"
        assert not (mode & stat.S_IWGRP), "Group should not have write"
        assert not (mode & stat.S_IROTH), "Other should not have read"
        assert not (mode & stat.S_IWOTH), "Other should not have write"

    def test_default_base_dir(self):
        """FileSecretProvider uses ~/.breqy/secrets by default."""
        from breqy.secrets.provider import FileSecretProvider
        provider = FileSecretProvider()
        from pathlib import Path
        expected = Path.home() / ".breqy" / "secrets"
        assert provider._base_dir == expected

    def test_overwrite_existing_key(self, tmp_path):
        """FileSecretProvider overwrites existing value on re-set."""
        from breqy.secrets.provider import FileSecretProvider
        provider = FileSecretProvider(base_dir=tmp_path)
        provider.set("key", "value1")
        provider.set("key", "value2")
        assert provider.get("key") == "value2"
