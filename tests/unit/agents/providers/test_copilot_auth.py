"""Tests for GitHub Copilot OAuth device flow authenticator."""
from __future__ import annotations

from pydantic import SecretStr

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


def _make_credential_store() -> CredentialStore:
    return CredentialStore(MemorySecretProvider())


def _store_token(store: CredentialStore, token: str = "gho_test123") -> None:
    store.set(
        "copilot",
        ProviderCredential(
            provider="copilot",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr(token),
            metadata={"auth_flow": "device"},
        ),
    )


class TestDeviceFlowInfo:
    def test_device_flow_info_fields(self) -> None:
        from breqy.agents.providers.copilot_auth import DeviceFlowInfo

        info = DeviceFlowInfo(
            user_code="ABCD-EFGH",
            verification_uri="https://github.com/login/device",
            device_code="device123",
            interval=5,
            expires_in=900,
        )
        assert info.user_code == "ABCD-EFGH"
        assert info.verification_uri == "https://github.com/login/device"
        assert info.device_code == "device123"
        assert info.interval == 5
        assert info.expires_in == 900


class TestCopilotAuthError:
    def test_copilot_auth_error_is_exception(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthError

        err = CopilotAuthError("token expired")
        assert isinstance(err, Exception)
        assert str(err) == "token expired"


class TestGetToken:
    def test_get_token_from_store(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        _store_token(store, "gho_mytoken")
        auth = CopilotAuthenticator(store)
        assert auth.get_token() == "gho_mytoken"

    def test_get_token_empty_store(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)
        assert auth.get_token() is None


class TestStoreToken:
    def test_store_token_persists_and_retrieves(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)
        assert auth.get_token() is None
        auth._store_token("gho_new_token")
        assert auth.get_token() == "gho_new_token"


class TestClearToken:
    def test_clear_token(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        _store_token(store, "gho_toremove")
        auth = CopilotAuthenticator(store)
        assert auth.get_token() == "gho_toremove"
        auth.clear_token()
        assert auth.get_token() is None
