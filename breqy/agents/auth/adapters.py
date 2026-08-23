"""Breqy-owned auth adapters over provider-specific auth implementations."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import SecretStr

from breqy.agents.auth.models import AuthBackend, AuthResult
from breqy.agents.credentials import CredentialStore
from breqy.agents.models import AuthSession, AuthStatus, ProviderCredential
from breqy.domain.enums import AuthFlowKind, AuthSessionStatus, CredentialKind
from breqy.secrets.provider import SecretProvider
from system.orchestrator.auth.claude_auth import ClaudeAuth
from system.orchestrator.auth.codex_auth import CodexAuth
from system.orchestrator.auth.copilot_auth import GitHubCopilotAuth
from system.orchestrator.auth.gemini_auth import GeminiAuth
from system.orchestrator.auth.qwen_auth import QwenAuth


class _ShimSecretProvider(SecretProvider):
    """Ephemeral secret backend for reused orchestrator auth providers."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value

    def delete(self, key: str) -> None:
        self._values.pop(key, None)


class _BaseProviderAuthAdapter(AuthBackend):
    def __init__(
        self,
        *,
        provider: str,
        credential_store: CredentialStore,
    ) -> None:
        self._provider = provider
        self._credential_store = credential_store
        self._status = AuthStatus(
            provider=provider,
            status=AuthSessionStatus.UNAUTHENTICATED,
        )

    def _ensure_provider(self, provider: str) -> None:
        if provider != self._provider:
            message = f"provider mismatch: expected {self._provider!r}, got {provider!r}"
            raise ValueError(message)

    def _authenticated_status(self, flow_kind: AuthFlowKind) -> AuthStatus:
        status = AuthStatus(
            provider=self._provider,
            status=AuthSessionStatus.AUTHENTICATED,
            flow_kind=flow_kind,
            authenticated_at=datetime.now(UTC),
        )
        self._status = status
        return status

    def _failed_status(self, flow_kind: AuthFlowKind, error: Exception) -> AuthStatus:
        status = AuthStatus(
            provider=self._provider,
            status=AuthSessionStatus.FAILED,
            flow_kind=flow_kind,
            last_error=str(error),
        )
        self._status = status
        return status


class _DeviceFlowAuthAdapter(_BaseProviderAuthAdapter):
    def __init__(
        self,
        *,
        provider: str,
        credential_store: CredentialStore,
        auth_provider: GitHubCopilotAuth | CodexAuth,
    ) -> None:
        super().__init__(provider=provider, credential_store=credential_store)
        self._auth_provider = auth_provider
        self._pending_device_code: str | None = None

    def start(self, provider: str) -> AuthSession:
        self._ensure_provider(provider)
        self._credential_store.delete(self._provider)
        device_code = self._auth_provider.request_device_code()
        self._pending_device_code = device_code.device_code
        self._status = AuthStatus(
            provider=self._provider,
            status=AuthSessionStatus.IN_PROGRESS,
            flow_kind=AuthFlowKind.DEVICE,
            verification_url=device_code.verification_uri,
            user_code=device_code.user_code,
            display_message="Open the verification URL and enter the device code.",
        )
        return AuthSession(
            provider=self._provider,
            flow_kind=AuthFlowKind.DEVICE,
            status=AuthSessionStatus.IN_PROGRESS,
            verification_url=device_code.verification_uri,
            user_code=device_code.user_code,
            display_message=self._status.display_message,
        )

    def get_status(self, provider: str) -> AuthStatus:
        self._ensure_provider(provider)
        if self._pending_device_code is not None:
            try:
                token = self._auth_provider.poll_for_token(self._pending_device_code)
            except (OSError, RuntimeError, ValueError) as error:
                return self._failed_status(AuthFlowKind.DEVICE, error)
            if token is not None:
                self._pending_device_code = None
                self._credential_store.set(
                    self._provider,
                    ProviderCredential(
                        provider=self._provider,
                        credential_kind=CredentialKind.ACCESS_TOKEN,
                        secret_value=SecretStr(token),
                    ),
                )
                return self._authenticated_status(AuthFlowKind.DEVICE)
            return self._status
        stored = self._credential_store.get(self._provider)
        if stored is not None:
            if self._status.status != AuthSessionStatus.AUTHENTICATED:
                return self._authenticated_status(AuthFlowKind.DEVICE)
            return self._status
        return self._status

    def submit_code(self, provider: str, code: str) -> AuthResult:
        self._ensure_provider(provider)
        raise ValueError(f"provider {provider!r} does not accept code submission")

    def submit_secret(self, provider: str, secret: str) -> AuthResult:
        self._ensure_provider(provider)
        raise ValueError(f"provider {provider!r} does not accept secret submission")

    def revoke(self, provider: str) -> None:
        self._ensure_provider(provider)
        self._pending_device_code = None
        self._credential_store.delete(self._provider)
        self._auth_provider.revoke()
        self._status = AuthStatus(
            provider=self._provider,
            status=AuthSessionStatus.UNAUTHENTICATED,
            flow_kind=AuthFlowKind.DEVICE,
        )


class _PkceCodeAuthAdapter(_BaseProviderAuthAdapter):
    def __init__(
        self,
        *,
        provider: str,
        credential_store: CredentialStore,
        auth_provider: ClaudeAuth,
    ) -> None:
        super().__init__(provider=provider, credential_store=credential_store)
        self._auth_provider = auth_provider

    def start(self, provider: str) -> AuthSession:
        self._ensure_provider(provider)
        self._credential_store.delete(self._provider)
        verification_url = self._auth_provider.get_auth_url()
        self._status = AuthStatus(
            provider=self._provider,
            status=AuthSessionStatus.IN_PROGRESS,
            flow_kind=AuthFlowKind.PKCE_CODE,
            verification_url=verification_url,
            display_message="Finish browser login, then paste the returned authorization code.",
        )
        return AuthSession(
            provider=self._provider,
            flow_kind=AuthFlowKind.PKCE_CODE,
            status=AuthSessionStatus.IN_PROGRESS,
            verification_url=verification_url,
            display_message=self._status.display_message,
        )

    def get_status(self, provider: str) -> AuthStatus:
        self._ensure_provider(provider)
        if self._status.status == AuthSessionStatus.IN_PROGRESS:
            return self._status
        stored = self._credential_store.get(self._provider)
        if stored is not None:
            if self._status.status != AuthSessionStatus.AUTHENTICATED:
                return self._authenticated_status(AuthFlowKind.PKCE_CODE)
            return self._status
        return self._status

    def submit_code(self, provider: str, code: str) -> AuthResult:
        self._ensure_provider(provider)
        try:
            self._auth_provider.exchange_code(code)
            token = self._auth_provider.get_token()
            if token is None:
                raise RuntimeError("provider did not return an access token")
        except (OSError, RuntimeError, ValueError) as error:
            return AuthResult(status=self._failed_status(AuthFlowKind.PKCE_CODE, error))
        credential = ProviderCredential(
            provider=self._provider,
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr(token),
        )
        status = self._authenticated_status(AuthFlowKind.PKCE_CODE)
        self._credential_store.set(self._provider, credential)
        return AuthResult(status=status, credential=credential)

    def submit_secret(self, provider: str, secret: str) -> AuthResult:
        self._ensure_provider(provider)
        raise ValueError(f"provider {provider!r} does not accept secret submission")

    def revoke(self, provider: str) -> None:
        self._ensure_provider(provider)
        self._credential_store.delete(self._provider)
        self._auth_provider.revoke()
        self._status = AuthStatus(
            provider=self._provider,
            status=AuthSessionStatus.UNAUTHENTICATED,
            flow_kind=AuthFlowKind.PKCE_CODE,
        )


class _ApiKeyAuthAdapter(_BaseProviderAuthAdapter):
    def __init__(
        self,
        *,
        provider: str,
        credential_store: CredentialStore,
        auth_provider: GeminiAuth | QwenAuth,
        key_url: str,
    ) -> None:
        super().__init__(provider=provider, credential_store=credential_store)
        self._auth_provider = auth_provider
        self._key_url = key_url

    def start(self, provider: str) -> AuthSession:
        self._ensure_provider(provider)
        self._credential_store.delete(self._provider)
        self._status = AuthStatus(
            provider=self._provider,
            status=AuthSessionStatus.UNAUTHENTICATED,
            flow_kind=AuthFlowKind.API_KEY,
            display_message=f"Paste your API key. Get one at {self._key_url}",
        )
        return AuthSession(
            provider=self._provider,
            flow_kind=AuthFlowKind.API_KEY,
            status=AuthSessionStatus.UNAUTHENTICATED,
            display_message=self._status.display_message,
        )

    def get_status(self, provider: str) -> AuthStatus:
        self._ensure_provider(provider)
        stored = self._credential_store.get(self._provider)
        if stored is not None:
            if self._status.status != AuthSessionStatus.AUTHENTICATED:
                return self._authenticated_status(AuthFlowKind.API_KEY)
            return self._status
        return AuthStatus(
            provider=self._provider,
            status=AuthSessionStatus.UNAUTHENTICATED,
            flow_kind=AuthFlowKind.API_KEY,
            display_message=f"Paste your API key. Get one at {self._key_url}",
        )

    def submit_code(self, provider: str, code: str) -> AuthResult:
        self._ensure_provider(provider)
        raise ValueError(f"provider {provider!r} does not accept code submission")

    def submit_secret(self, provider: str, secret: str) -> AuthResult:
        self._ensure_provider(provider)
        self._auth_provider.set_key(secret)
        credential = ProviderCredential(
            provider=self._provider,
            credential_kind=CredentialKind.API_KEY,
            secret_value=SecretStr(secret),
        )
        status = self._authenticated_status(AuthFlowKind.API_KEY)
        self._credential_store.set(self._provider, credential)
        return AuthResult(status=status, credential=credential)

    def revoke(self, provider: str) -> None:
        self._ensure_provider(provider)
        self._credential_store.delete(self._provider)
        self._auth_provider.revoke()
        self._status = AuthStatus(
            provider=self._provider,
            status=AuthSessionStatus.UNAUTHENTICATED,
            flow_kind=AuthFlowKind.API_KEY,
            display_message=f"Paste your API key. Get one at {self._key_url}",
        )


def build_provider_auth_backends(*, secret_provider: SecretProvider) -> dict[str, AuthBackend]:
    """Build Breqy-native auth backends for the supported providers."""
    credential_store = CredentialStore(secret_provider)

    copilot_provider = GitHubCopilotAuth(cast(object, _ShimSecretProvider()))  # type: ignore[arg-type]
    codex_provider = CodexAuth(cast(object, _ShimSecretProvider()))  # type: ignore[arg-type]
    claude_provider = ClaudeAuth(cast(object, _ShimSecretProvider()))  # type: ignore[arg-type]
    gemini_provider = GeminiAuth(cast(object, _ShimSecretProvider()))  # type: ignore[arg-type]
    qwen_provider = QwenAuth(cast(object, _ShimSecretProvider()))  # type: ignore[arg-type]

    return {
        "copilot": _DeviceFlowAuthAdapter(
            provider="copilot",
            credential_store=credential_store,
            auth_provider=copilot_provider,
        ),
        "codex": _DeviceFlowAuthAdapter(
            provider="codex",
            credential_store=credential_store,
            auth_provider=codex_provider,
        ),
        "claude": _PkceCodeAuthAdapter(
            provider="claude",
            credential_store=credential_store,
            auth_provider=claude_provider,
        ),
        "gemini": _ApiKeyAuthAdapter(
            provider="gemini",
            credential_store=credential_store,
            auth_provider=gemini_provider,
            key_url=str(GeminiAuth.key_url or ""),
        ),
        "qwen": _ApiKeyAuthAdapter(
            provider="qwen",
            credential_store=credential_store,
            auth_provider=qwen_provider,
            key_url=str(QwenAuth.key_url or ""),
        ),
    }
