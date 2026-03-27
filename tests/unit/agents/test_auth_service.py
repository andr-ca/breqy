"""Tests for the Breqy auth service contract."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import SecretStr

from breqy.agents.auth.adapters import _PkceCodeAuthAdapter, build_provider_auth_backends
from breqy.agents.auth.models import AuthBackend, AuthResult
from breqy.agents.auth.service import AuthService
from breqy.agents.credentials import CredentialStore
from breqy.agents.models import AuthSession, AuthStatus, ProviderCredential
from breqy.domain.enums import AuthFlowKind, AuthSessionStatus, CredentialKind
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


class FakeAuthBackend(AuthBackend):
    """Simple auth backend double for service tests."""

    def __init__(
        self,
        *,
        start_session: AuthSession,
        status: AuthStatus,
        code_result: AuthResult | None = None,
        secret_result: AuthResult | None = None,
    ) -> None:
        self.start_session = start_session
        self.status = status
        self.code_result = code_result
        self.secret_result = secret_result
        self.started = 0
        self.status_checks = 0
        self.codes: list[str] = []
        self.secrets: list[str] = []
        self.revoked = 0

    def start(self, provider: str) -> AuthSession:
        self.started += 1
        assert provider == self.start_session.provider
        return self.start_session

    def get_status(self, provider: str) -> AuthStatus:
        self.status_checks += 1
        assert provider == self.status.provider
        return self.status

    def submit_code(self, provider: str, code: str) -> AuthResult:
        self.codes.append(code)
        assert provider == self.start_session.provider
        assert self.code_result is not None
        return self.code_result

    def submit_secret(self, provider: str, secret: str) -> AuthResult:
        self.secrets.append(secret)
        assert provider == self.start_session.provider
        assert self.secret_result is not None
        return self.secret_result

    def revoke(self, provider: str) -> None:
        self.revoked += 1
        assert provider == self.start_session.provider


def _response(
    *,
    json_data: dict[str, object],
    status_code: int = 200,
    is_success: bool | None = None,
):
    from unittest.mock import MagicMock

    response = MagicMock()
    response.status_code = status_code
    response.is_success = status_code < 400 if is_success is None else is_success
    response.json.return_value = json_data
    response.text = "response-text"
    response.raise_for_status.return_value = None
    return response


def _service_with_provider_adapters(
    secret_provider: SecretProvider | None = None,
) -> AuthService:
    provider = secret_provider or MemorySecretProvider()
    return AuthService(
        credential_store=CredentialStore(provider),
        backends=build_provider_auth_backends(secret_provider=provider),
    )


def test_auth_service_start_and_get_status_delegate_in_progress_state() -> None:
    backend = FakeAuthBackend(
        start_session=AuthSession(
            provider="copilot",
            flow_kind=AuthFlowKind.DEVICE,
            status=AuthSessionStatus.IN_PROGRESS,
            verification_url="https://github.com/login/device",
            user_code="ABCD-EFGH",
            display_message="Enter this code in your browser.",
        ),
        status=AuthStatus(
            provider="copilot",
            status=AuthSessionStatus.IN_PROGRESS,
            flow_kind=AuthFlowKind.DEVICE,
            verification_url="https://github.com/login/device",
            user_code="ABCD-EFGH",
            display_message="Enter this code in your browser.",
        ),
    )
    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={"copilot": backend},
    )

    session = service.start("copilot")
    status = service.get_status("copilot")

    assert session.status == AuthSessionStatus.IN_PROGRESS
    assert session.flow_kind == AuthFlowKind.DEVICE
    assert status.status == AuthSessionStatus.IN_PROGRESS
    assert status.flow_kind == AuthFlowKind.DEVICE
    assert backend.started == 1
    assert backend.status_checks == 1


def test_auth_service_submit_code_persists_credential_and_reports_authenticated() -> None:
    backend = FakeAuthBackend(
        start_session=AuthSession(
            provider="claude",
            flow_kind=AuthFlowKind.PKCE_CODE,
            status=AuthSessionStatus.IN_PROGRESS,
            verification_url="https://claude.ai/oauth/authorize",
            display_message="Finish login in the browser, then paste the code.",
        ),
        status=AuthStatus(
            provider="claude",
            status=AuthSessionStatus.IN_PROGRESS,
            flow_kind=AuthFlowKind.PKCE_CODE,
        ),
        code_result=AuthResult(
            status=AuthStatus(
                provider="claude",
                status=AuthSessionStatus.AUTHENTICATED,
                flow_kind=AuthFlowKind.PKCE_CODE,
                authenticated_at=datetime(2026, 3, 23, 13, 0, tzinfo=UTC),
            ),
            credential=ProviderCredential(
                provider="claude",
                credential_kind=CredentialKind.ACCESS_TOKEN,
                secret_value=SecretStr("claude-access-token"),
                refresh_token=SecretStr("claude-refresh-token"),
                metadata={"account": "default"},
            ),
        ),
    )
    provider = MemorySecretProvider()
    service = AuthService(
        credential_store=CredentialStore(provider),
        backends={"claude": backend},
    )

    status = service.submit_code("claude", "temporary-code")
    stored = service.credential_store.get("claude")

    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert backend.codes == ["temporary-code"]
    assert stored is not None
    assert stored.secret_value.get_secret_value() == "claude-access-token"
    assert stored.refresh_token is not None
    assert stored.refresh_token.get_secret_value() == "claude-refresh-token"


def test_auth_service_get_status_prefers_backend_in_progress_over_cached_authenticated() -> None:
    backend = FakeAuthBackend(
        start_session=AuthSession(
            provider="claude",
            flow_kind=AuthFlowKind.PKCE_CODE,
            status=AuthSessionStatus.IN_PROGRESS,
        ),
        status=AuthStatus(
            provider="claude",
            status=AuthSessionStatus.IN_PROGRESS,
            flow_kind=AuthFlowKind.PKCE_CODE,
            display_message="Continue browser login.",
        ),
        code_result=AuthResult(
            status=AuthStatus(
                provider="claude",
                status=AuthSessionStatus.AUTHENTICATED,
                flow_kind=AuthFlowKind.PKCE_CODE,
                authenticated_at=datetime(2026, 3, 23, 13, 0, tzinfo=UTC),
            ),
            credential=ProviderCredential(
                provider="claude",
                credential_kind=CredentialKind.ACCESS_TOKEN,
                secret_value=SecretStr("claude-access-token"),
            ),
        ),
    )
    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={"claude": backend},
    )
    service.submit_code("claude", "temporary-code")

    status = service.get_status("claude")

    assert status.status == AuthSessionStatus.IN_PROGRESS
    assert status.flow_kind == AuthFlowKind.PKCE_CODE
    assert status.display_message == "Continue browser login."
    assert backend.status_checks == 1


def test_auth_service_get_status_prefers_backend_failed_over_cached_authenticated() -> None:
    backend = FakeAuthBackend(
        start_session=AuthSession(
            provider="copilot",
            flow_kind=AuthFlowKind.DEVICE,
            status=AuthSessionStatus.IN_PROGRESS,
        ),
        status=AuthStatus(
            provider="copilot",
            status=AuthSessionStatus.FAILED,
            flow_kind=AuthFlowKind.DEVICE,
            last_error="device code expired",
        ),
        code_result=AuthResult(
            status=AuthStatus(
                provider="copilot",
                status=AuthSessionStatus.AUTHENTICATED,
                flow_kind=AuthFlowKind.DEVICE,
                authenticated_at=datetime(2026, 3, 23, 13, 0, tzinfo=UTC),
            ),
            credential=ProviderCredential(
                provider="copilot",
                credential_kind=CredentialKind.ACCESS_TOKEN,
                secret_value=SecretStr("copilot-access-token"),
            ),
        ),
    )
    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={"copilot": backend},
    )
    service.submit_code("copilot", "temporary-code")

    status = service.get_status("copilot")

    assert status.status == AuthSessionStatus.FAILED
    assert status.flow_kind == AuthFlowKind.DEVICE
    assert status.last_error == "device code expired"
    assert backend.status_checks == 1


def test_auth_service_get_status_keeps_authenticated_when_backend_does_not_contradict() -> None:
    backend = FakeAuthBackend(
        start_session=AuthSession(
            provider="qwen",
            flow_kind=AuthFlowKind.API_KEY,
            status=AuthSessionStatus.UNAUTHENTICATED,
        ),
        status=AuthStatus(
            provider="qwen",
            status=AuthSessionStatus.UNAUTHENTICATED,
            flow_kind=AuthFlowKind.API_KEY,
        ),
        secret_result=AuthResult(
            status=AuthStatus(
                provider="qwen",
                status=AuthSessionStatus.AUTHENTICATED,
                flow_kind=AuthFlowKind.API_KEY,
                authenticated_at=datetime(2026, 3, 23, 14, 0, tzinfo=UTC),
            ),
            credential=ProviderCredential(
                provider="qwen",
                credential_kind=CredentialKind.API_KEY,
                secret_value=SecretStr("qwen-api-key"),
            ),
        ),
    )
    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={"qwen": backend},
    )
    service.submit_secret("qwen", "qwen-api-key")

    status = service.get_status("qwen")

    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert status.flow_kind == AuthFlowKind.API_KEY
    assert status.authenticated_at == datetime(2026, 3, 23, 14, 0, tzinfo=UTC)
    assert backend.status_checks == 1


def test_auth_service_get_status_prefers_backend_in_progress_over_stale_credential() -> None:
    backend = FakeAuthBackend(
        start_session=AuthSession(
            provider="claude",
            flow_kind=AuthFlowKind.PKCE_CODE,
            status=AuthSessionStatus.IN_PROGRESS,
        ),
        status=AuthStatus(
            provider="claude",
            status=AuthSessionStatus.IN_PROGRESS,
            flow_kind=AuthFlowKind.PKCE_CODE,
            display_message="Continue browser login.",
        ),
    )
    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={"claude": backend},
    )
    service.credential_store.set(
        "claude",
        ProviderCredential(
            provider="claude",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr("stale-token"),
        ),
    )

    status = service.get_status("claude")

    assert status.status == AuthSessionStatus.IN_PROGRESS
    assert status.flow_kind == AuthFlowKind.PKCE_CODE
    assert status.display_message == "Continue browser login."
    assert backend.status_checks == 1


def test_auth_service_get_status_prefers_backend_failed_over_stale_credential() -> None:
    backend = FakeAuthBackend(
        start_session=AuthSession(
            provider="copilot",
            flow_kind=AuthFlowKind.DEVICE,
            status=AuthSessionStatus.IN_PROGRESS,
        ),
        status=AuthStatus(
            provider="copilot",
            status=AuthSessionStatus.FAILED,
            flow_kind=AuthFlowKind.DEVICE,
            last_error="device code expired",
        ),
    )
    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={"copilot": backend},
    )
    service.credential_store.set(
        "copilot",
        ProviderCredential(
            provider="copilot",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr("stale-token"),
        ),
    )

    status = service.get_status("copilot")

    assert status.status == AuthSessionStatus.FAILED
    assert status.flow_kind == AuthFlowKind.DEVICE
    assert status.last_error == "device code expired"
    assert backend.status_checks == 1


def test_auth_service_get_status_keeps_returned_and_cached_state_consistent() -> None:
    backend = FakeAuthBackend(
        start_session=AuthSession(
            provider="claude",
            flow_kind=AuthFlowKind.PKCE_CODE,
            status=AuthSessionStatus.IN_PROGRESS,
        ),
        status=AuthStatus(
            provider="claude",
            status=AuthSessionStatus.UNAUTHENTICATED,
            flow_kind=AuthFlowKind.PKCE_CODE,
        ),
    )
    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={"claude": backend},
    )
    service.start("claude")

    first_status = service.get_status("claude")
    second_status = service.get_status("claude")

    assert first_status.status == AuthSessionStatus.UNAUTHENTICATED
    assert second_status.status == AuthSessionStatus.UNAUTHENTICATED
    assert service._status_by_provider["claude"].status == AuthSessionStatus.UNAUTHENTICATED
    assert backend.status_checks == 2


def test_auth_service_submit_secret_persists_api_key_and_revoke_clears_it() -> None:
    backend = FakeAuthBackend(
        start_session=AuthSession(
            provider="gemini",
            flow_kind=AuthFlowKind.API_KEY,
            status=AuthSessionStatus.UNAUTHENTICATED,
            display_message="Paste your API key.",
        ),
        status=AuthStatus(
            provider="gemini",
            status=AuthSessionStatus.UNAUTHENTICATED,
            flow_kind=AuthFlowKind.API_KEY,
        ),
        secret_result=AuthResult(
            status=AuthStatus(
                provider="gemini",
                status=AuthSessionStatus.AUTHENTICATED,
                flow_kind=AuthFlowKind.API_KEY,
                authenticated_at=datetime(2026, 3, 23, 14, 0, tzinfo=UTC),
            ),
            credential=ProviderCredential(
                provider="gemini",
                credential_kind=CredentialKind.API_KEY,
                secret_value=SecretStr("gemini-api-key"),
            ),
        ),
    )
    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={"gemini": backend},
    )

    authenticated = service.submit_secret("gemini", "gemini-api-key")
    service.revoke("gemini")
    revoked = service.get_status("gemini")

    assert authenticated.status == AuthSessionStatus.AUTHENTICATED
    assert backend.secrets == ["gemini-api-key"]
    assert backend.revoked == 1
    assert revoked.status == AuthSessionStatus.UNAUTHENTICATED
    assert revoked.flow_kind == AuthFlowKind.API_KEY


def test_auth_service_does_not_fallback_to_environment_credentials(monkeypatch) -> None:
    monkeypatch.setenv("BREQY_SECRET_AGENTS_CREDENTIALS_GEMINI", "plain-env-secret")

    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={},
    )

    status = service.get_status("gemini")

    assert status.status == AuthSessionStatus.UNAUTHENTICATED
    assert status.flow_kind is None


def test_auth_service_requires_registered_backend_for_interactive_actions() -> None:
    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={},
    )

    with pytest.raises(ValueError, match="provider"):
        service.start("unknown")
    with pytest.raises(ValueError, match="provider"):
        service.submit_code("unknown", "code")
    with pytest.raises(ValueError, match="provider"):
        service.submit_secret("unknown", "secret")


def test_provider_auth_adapters_map_copilot_device_flow_to_breqy_session_and_status(monkeypatch) -> None:
    service = _service_with_provider_adapters()
    responses = [
        _response(
            json_data={
                "device_code": "copilot-device-code",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://github.com/login/device",
                "expires_in": "900",
                "interval": "5",
            }
        ),
        _response(json_data={"access_token": "copilot-access-token"}),
    ]
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: responses.pop(0))

    session = service.start("copilot")
    status = service.get_status("copilot")
    stored = service.credential_store.get("copilot")

    assert session.provider == "copilot"
    assert session.flow_kind == AuthFlowKind.DEVICE
    assert session.status == AuthSessionStatus.IN_PROGRESS
    assert session.verification_url == "https://github.com/login/device"
    assert session.user_code == "ABCD-EFGH"
    assert status.provider == "copilot"
    assert status.flow_kind == AuthFlowKind.DEVICE
    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert stored is not None
    assert stored.credential_kind == CredentialKind.ACCESS_TOKEN
    assert stored.secret_value.get_secret_value() == "copilot-access-token"


def test_provider_auth_adapters_map_codex_device_flow_and_token_exchange(monkeypatch) -> None:
    service = _service_with_provider_adapters()
    responses = [
        _response(
            json_data={
                "device_auth_id": "codex-device-auth-id",
                "user_code": "QRST-5678",
                "expires_in": 900,
                "interval": 5,
            }
        ),
        _response(
            json_data={
                "authorization_code": "codex-auth-code",
                "code_verifier": "codex-verifier",
            }
        ),
        _response(json_data={"access_token": "codex-access-token"}),
    ]
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: responses.pop(0))

    session = service.start("codex")
    status = service.get_status("codex")
    stored = service.credential_store.get("codex")

    assert session.provider == "codex"
    assert session.flow_kind == AuthFlowKind.DEVICE
    assert session.status == AuthSessionStatus.IN_PROGRESS
    assert session.verification_url == "https://auth.openai.com/codex/device"
    assert session.user_code == "QRST-5678"
    assert status.provider == "codex"
    assert status.flow_kind == AuthFlowKind.DEVICE
    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert stored is not None
    assert stored.credential_kind == CredentialKind.ACCESS_TOKEN
    assert stored.secret_value.get_secret_value() == "codex-access-token"


def test_provider_auth_adapters_map_claude_pkce_start_and_code_exchange(monkeypatch) -> None:
    service = _service_with_provider_adapters()
    monkeypatch.setattr("os.urandom", lambda _size: b"a" * 32)
    monkeypatch.setattr("secrets.token_urlsafe", lambda _size: "pkce-state")
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: _response(json_data={"access_token": "claude-access-token"}),
    )

    session = service.start("claude")
    status = service.submit_code("claude", "temporary-auth-code")
    stored = service.credential_store.get("claude")

    assert session.provider == "claude"
    assert session.flow_kind == AuthFlowKind.PKCE_CODE
    assert session.status == AuthSessionStatus.IN_PROGRESS
    assert session.verification_url.startswith("https://claude.ai/oauth/authorize?")
    assert session.display_message
    assert status.provider == "claude"
    assert status.flow_kind == AuthFlowKind.PKCE_CODE
    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert stored is not None
    assert stored.credential_kind == CredentialKind.ACCESS_TOKEN
    assert stored.secret_value.get_secret_value() == "claude-access-token"


def test_provider_auth_adapters_map_gemini_api_key_flow(monkeypatch) -> None:
    service = _service_with_provider_adapters()

    session = service.start("gemini")
    status = service.submit_secret("gemini", "gemini-api-key")
    stored = service.credential_store.get("gemini")

    assert session.provider == "gemini"
    assert session.flow_kind == AuthFlowKind.API_KEY
    assert session.status == AuthSessionStatus.UNAUTHENTICATED
    assert "aistudio.google.com/apikey" in session.display_message
    assert status.provider == "gemini"
    assert status.flow_kind == AuthFlowKind.API_KEY
    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert stored is not None
    assert stored.credential_kind == CredentialKind.API_KEY
    assert stored.secret_value.get_secret_value() == "gemini-api-key"


def test_provider_auth_adapters_map_qwen_api_key_flow(monkeypatch) -> None:
    service = _service_with_provider_adapters()

    session = service.start("qwen")
    status = service.submit_secret("qwen", "qwen-api-key")
    stored = service.credential_store.get("qwen")

    assert session.provider == "qwen"
    assert session.flow_kind == AuthFlowKind.API_KEY
    assert session.status == AuthSessionStatus.UNAUTHENTICATED
    assert "bailian.console.alibabacloud.com" in session.display_message
    assert status.provider == "qwen"
    assert status.flow_kind == AuthFlowKind.API_KEY
    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert stored is not None
    assert stored.credential_kind == CredentialKind.API_KEY
    assert stored.secret_value.get_secret_value() == "qwen-api-key"


def test_direct_backend_revoke_clears_breqy_credential_and_status_for_copilot(monkeypatch) -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    backend = build_provider_auth_backends(secret_provider=secret_provider)["copilot"]
    responses = [
        _response(
            json_data={
                "device_code": "copilot-device-code",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://github.com/login/device",
                "expires_in": "900",
                "interval": "5",
            }
        ),
        _response(json_data={"access_token": "copilot-access-token"}),
    ]
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: responses.pop(0))

    backend.start("copilot")
    authenticated = backend.get_status("copilot")
    backend.revoke("copilot")
    revoked = backend.get_status("copilot")

    assert authenticated.status == AuthSessionStatus.AUTHENTICATED
    assert credential_store.get("copilot") is None
    assert revoked.status == AuthSessionStatus.UNAUTHENTICATED
    assert revoked.flow_kind == AuthFlowKind.DEVICE


def test_direct_backend_revoke_clears_breqy_credential_and_status_for_claude(monkeypatch) -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    backend = build_provider_auth_backends(secret_provider=secret_provider)["claude"]
    monkeypatch.setattr("os.urandom", lambda _size: b"a" * 32)
    monkeypatch.setattr("secrets.token_urlsafe", lambda _size: "pkce-state")
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: _response(json_data={"access_token": "claude-access-token"}),
    )

    backend.start("claude")
    authenticated = backend.submit_code("claude", "temporary-auth-code").status
    backend.revoke("claude")
    revoked = backend.get_status("claude")

    assert authenticated.status == AuthSessionStatus.AUTHENTICATED
    assert credential_store.get("claude") is None
    assert revoked.status == AuthSessionStatus.UNAUTHENTICATED
    assert revoked.flow_kind == AuthFlowKind.PKCE_CODE


def test_direct_backend_revoke_clears_breqy_credential_and_status_for_gemini() -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    backend = build_provider_auth_backends(secret_provider=secret_provider)["gemini"]

    authenticated = backend.submit_secret("gemini", "gemini-api-key").status
    backend.revoke("gemini")
    revoked = backend.get_status("gemini")

    assert authenticated.status == AuthSessionStatus.AUTHENTICATED
    assert credential_store.get("gemini") is None
    assert revoked.status == AuthSessionStatus.UNAUTHENTICATED
    assert revoked.flow_kind == AuthFlowKind.API_KEY


def test_direct_backend_start_keeps_copilot_in_progress_despite_stale_credential(monkeypatch) -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    backend = build_provider_auth_backends(secret_provider=secret_provider)["copilot"]
    credential_store.set(
        "copilot",
        ProviderCredential(
            provider="copilot",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr("stale-copilot-token"),
        ),
    )
    responses = [
        _response(
            json_data={
                "device_code": "copilot-device-code",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://github.com/login/device",
                "expires_in": "900",
                "interval": "5",
            }
        ),
        _response(json_data={"error": "authorization_pending"}),
    ]
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: responses.pop(0))

    session = backend.start("copilot")
    status = backend.get_status("copilot")

    assert session.status == AuthSessionStatus.IN_PROGRESS
    assert credential_store.get("copilot") is None
    assert status.status == AuthSessionStatus.IN_PROGRESS
    assert status.flow_kind == AuthFlowKind.DEVICE
    assert status.user_code == "ABCD-EFGH"


def test_direct_backend_start_keeps_claude_in_progress_despite_stale_credential(monkeypatch) -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    backend = build_provider_auth_backends(secret_provider=secret_provider)["claude"]
    credential_store.set(
        "claude",
        ProviderCredential(
            provider="claude",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr("stale-claude-token"),
        ),
    )
    monkeypatch.setattr("os.urandom", lambda _size: b"a" * 32)
    monkeypatch.setattr("secrets.token_urlsafe", lambda _size: "pkce-state")

    session = backend.start("claude")
    status = backend.get_status("claude")

    assert session.status == AuthSessionStatus.IN_PROGRESS
    assert credential_store.get("claude") is None
    assert status.status == AuthSessionStatus.IN_PROGRESS
    assert status.flow_kind == AuthFlowKind.PKCE_CODE
    assert status.verification_url.startswith("https://claude.ai/oauth/authorize?")


def test_direct_backend_start_clears_stale_gemini_credential_and_stays_unauthenticated() -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    backend = build_provider_auth_backends(secret_provider=secret_provider)["gemini"]
    credential_store.set(
        "gemini",
        ProviderCredential(
            provider="gemini",
            credential_kind=CredentialKind.API_KEY,
            secret_value=SecretStr("stale-gemini-key"),
        ),
    )

    session = backend.start("gemini")
    status = backend.get_status("gemini")

    assert session.status == AuthSessionStatus.UNAUTHENTICATED
    assert credential_store.get("gemini") is None
    assert status.status == AuthSessionStatus.UNAUTHENTICATED
    assert status.flow_kind == AuthFlowKind.API_KEY
    assert "aistudio.google.com/apikey" in status.display_message


def test_provider_auth_backends_reject_provider_mismatch() -> None:
    backends = build_provider_auth_backends(secret_provider=MemorySecretProvider())

    with pytest.raises(ValueError, match="provider mismatch"):
        backends["copilot"].start("claude")


def test_device_backend_reports_failed_status_when_poll_raises(monkeypatch) -> None:
    backend = build_provider_auth_backends(secret_provider=MemorySecretProvider())["copilot"]
    responses = [
        _response(
            json_data={
                "device_code": "copilot-device-code",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://github.com/login/device",
                "expires_in": "900",
                "interval": "5",
            }
        )
    ]

    def fake_post(*args, **kwargs):
        if responses:
            return responses.pop(0)
        raise RuntimeError("poll failed")

    monkeypatch.setattr("httpx.post", fake_post)

    backend.start("copilot")
    status = backend.get_status("copilot")

    assert status.status == AuthSessionStatus.FAILED
    assert status.last_error == "poll failed"


def test_device_backend_submit_methods_raise_for_unsupported_inputs() -> None:
    backend = build_provider_auth_backends(secret_provider=MemorySecretProvider())["copilot"]

    with pytest.raises(ValueError, match="does not accept code submission"):
        backend.submit_code("copilot", "code")
    with pytest.raises(ValueError, match="does not accept secret submission"):
        backend.submit_secret("copilot", "secret")


def test_device_backend_marks_authenticated_when_stored_credential_exists() -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    backend = build_provider_auth_backends(secret_provider=secret_provider)["copilot"]
    credential_store.set(
        "copilot",
        ProviderCredential(
            provider="copilot",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr("stored-token"),
        ),
    )

    status = backend.get_status("copilot")

    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert status.flow_kind == AuthFlowKind.DEVICE


def test_pkce_backend_marks_authenticated_when_stored_credential_exists() -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    backend = build_provider_auth_backends(secret_provider=secret_provider)["claude"]
    credential_store.set(
        "claude",
        ProviderCredential(
            provider="claude",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr("stored-token"),
        ),
    )

    status = backend.get_status("claude")

    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert status.flow_kind == AuthFlowKind.PKCE_CODE


def test_pkce_backend_submit_code_returns_failed_status_when_provider_returns_no_token(monkeypatch) -> None:
    backend = build_provider_auth_backends(secret_provider=MemorySecretProvider())["claude"]
    assert isinstance(backend, _PkceCodeAuthAdapter)
    monkeypatch.setattr(backend._auth_provider, "exchange_code", lambda code: None)
    monkeypatch.setattr(backend._auth_provider, "get_token", lambda: None)

    result = backend.submit_code("claude", "temporary-auth-code")

    assert result.status.status == AuthSessionStatus.FAILED
    assert result.credential is None


def test_pkce_backend_submit_secret_raises_for_unsupported_input() -> None:
    backend = build_provider_auth_backends(secret_provider=MemorySecretProvider())["claude"]

    with pytest.raises(ValueError, match="does not accept secret submission"):
        backend.submit_secret("claude", "secret")


def test_api_key_backend_marks_authenticated_when_stored_credential_exists() -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    backend = build_provider_auth_backends(secret_provider=secret_provider)["gemini"]
    credential_store.set(
        "gemini",
        ProviderCredential(
            provider="gemini",
            credential_kind=CredentialKind.API_KEY,
            secret_value=SecretStr("stored-key"),
        ),
    )

    status = backend.get_status("gemini")

    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert status.flow_kind == AuthFlowKind.API_KEY


def test_api_key_backend_submit_code_raises_for_unsupported_input() -> None:
    backend = build_provider_auth_backends(secret_provider=MemorySecretProvider())["gemini"]

    with pytest.raises(ValueError, match="does not accept code submission"):
        backend.submit_code("gemini", "code")


def test_auth_service_get_status_uses_stored_credential_without_backend() -> None:
    provider = MemorySecretProvider()
    service = AuthService(
        credential_store=CredentialStore(provider),
        backends={},
    )
    service.credential_store.set(
        "copilot",
        ProviderCredential(
            provider="copilot",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr("stored-token"),
        ),
    )

    status = service.get_status("copilot")

    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert status.provider == "copilot"


def test_auth_service_get_status_uses_cached_state_without_backend_or_stored_credential() -> None:
    service = AuthService(
        credential_store=CredentialStore(MemorySecretProvider()),
        backends={},
    )
    service._status_by_provider["copilot"] = AuthStatus(
        provider="copilot",
        status=AuthSessionStatus.IN_PROGRESS,
        flow_kind=AuthFlowKind.DEVICE,
    )

    status = service.get_status("copilot")

    assert status.status == AuthSessionStatus.IN_PROGRESS
    assert status.flow_kind == AuthFlowKind.DEVICE


def test_device_backend_get_status_keeps_authenticated_state_when_credential_remains() -> None:
    secret_provider = MemorySecretProvider()
    backend = build_provider_auth_backends(secret_provider=secret_provider)["copilot"]
    cast_backend = cast(object, backend)
    setattr(cast_backend, "_status", AuthStatus(
        provider="copilot",
        status=AuthSessionStatus.AUTHENTICATED,
        flow_kind=AuthFlowKind.DEVICE,
    ))
    CredentialStore(secret_provider).set(
        "copilot",
        ProviderCredential(
            provider="copilot",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr("stored-token"),
        ),
    )

    status = backend.get_status("copilot")

    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert status.flow_kind == AuthFlowKind.DEVICE


def test_pkce_backend_get_status_keeps_authenticated_state_when_credential_remains() -> None:
    secret_provider = MemorySecretProvider()
    backend = build_provider_auth_backends(secret_provider=secret_provider)["claude"]
    cast_backend = cast(object, backend)
    setattr(cast_backend, "_status", AuthStatus(
        provider="claude",
        status=AuthSessionStatus.AUTHENTICATED,
        flow_kind=AuthFlowKind.PKCE_CODE,
    ))
    CredentialStore(secret_provider).set(
        "claude",
        ProviderCredential(
            provider="claude",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr("stored-token"),
        ),
    )

    status = backend.get_status("claude")

    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert status.flow_kind == AuthFlowKind.PKCE_CODE


def test_api_key_backend_get_status_keeps_authenticated_state_when_credential_remains() -> None:
    secret_provider = MemorySecretProvider()
    backend = build_provider_auth_backends(secret_provider=secret_provider)["gemini"]
    cast_backend = cast(object, backend)
    setattr(cast_backend, "_status", AuthStatus(
        provider="gemini",
        status=AuthSessionStatus.AUTHENTICATED,
        flow_kind=AuthFlowKind.API_KEY,
    ))
    CredentialStore(secret_provider).set(
        "gemini",
        ProviderCredential(
            provider="gemini",
            credential_kind=CredentialKind.API_KEY,
            secret_value=SecretStr("stored-key"),
        ),
    )

    status = backend.get_status("gemini")

    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert status.flow_kind == AuthFlowKind.API_KEY
