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
