"""Tests for provider credential storage."""
from __future__ import annotations

from datetime import UTC, datetime

from breqy.agents.credentials import CredentialStore
from breqy.agents.models import ProviderCredential
from breqy.domain.enums import CredentialKind
from breqy.secrets.provider import SecretProvider


class MemorySecretProvider(SecretProvider):
    """In-memory secret provider for unit tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def test_credential_store_round_trips_structured_payloads_per_provider() -> None:
    provider = MemorySecretProvider()
    store = CredentialStore(provider)

    claude_credential = ProviderCredential(
        provider="claude",
        credential_kind=CredentialKind.ACCESS_TOKEN,
        secret_value="access-token",
        refresh_token="refresh-token",
        expires_at=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        metadata={"account": "default"},
    )
    gemini_credential = ProviderCredential(
        provider="gemini",
        credential_kind=CredentialKind.API_KEY,
        secret_value="api-key",
        metadata={"project": "sandbox"},
    )

    store.set("claude", claude_credential)
    store.set("gemini", gemini_credential)

    restored_claude = store.get("claude")
    restored_gemini = store.get("gemini")

    assert set(provider.values) == {
        "claude",
        "gemini",
    }
    assert restored_claude is not None
    assert restored_claude.provider == "claude"
    assert restored_claude.credential_kind == CredentialKind.ACCESS_TOKEN
    assert restored_claude.secret_value.get_secret_value() == "access-token"
    assert restored_claude.refresh_token is not None
    assert restored_claude.refresh_token.get_secret_value() == "refresh-token"
    assert restored_claude.expires_at == datetime(2026, 3, 23, 12, 0, tzinfo=UTC)
    assert restored_claude.metadata == {"account": "default"}
    assert restored_gemini is not None
    assert restored_gemini.provider == "gemini"
    assert restored_gemini.credential_kind == CredentialKind.API_KEY
    assert restored_gemini.secret_value.get_secret_value() == "api-key"
    assert restored_gemini.refresh_token is None
    assert restored_gemini.metadata == {"project": "sandbox"}


def test_credential_store_uses_only_secret_provider_without_env_fallback(monkeypatch) -> None:
    monkeypatch.setenv("BREQY_SECRET_CLAUDE", "plain-env-secret")

    store = CredentialStore(MemorySecretProvider())

    assert store.get("claude") is None


def test_credential_store_rejects_provider_mismatch() -> None:
    store = CredentialStore(MemorySecretProvider())
    credential = ProviderCredential(
        provider="gemini",
        credential_kind=CredentialKind.API_KEY,
        secret_value="api-key",
    )

    try:
        store.set("claude", credential)
    except ValueError as exc:
        assert "provider" in str(exc)
    else:
        raise AssertionError("expected provider mismatch to raise ValueError")


def test_credential_store_delete_removes_provider_secret() -> None:
    provider = MemorySecretProvider()
    store = CredentialStore(provider)
    credential = ProviderCredential(
        provider="qwen",
        credential_kind=CredentialKind.API_KEY,
        secret_value="secret",
    )

    store.set("qwen", credential)
    store.delete("qwen")

    assert store.get("qwen") is None
    assert provider.values == {}


def test_credential_store_returns_none_for_empty_string_payload() -> None:
    """KeyringSecretProvider may return '' instead of None on some backends."""
    provider = MemorySecretProvider()
    provider.values["copilot"] = ""  # Simulate empty keyring entry
    store = CredentialStore(provider)

    assert store.get("copilot") is None


def test_credential_store_returns_none_for_whitespace_only_payload() -> None:
    """Whitespace-only keyring entries should be treated as absent."""
    provider = MemorySecretProvider()
    provider.values["copilot"] = "   "  # Simulate whitespace-only keyring entry
    store = CredentialStore(provider)

    assert store.get("copilot") is None
