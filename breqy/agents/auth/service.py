"""Breqy-native auth service orchestration."""
from __future__ import annotations

from collections.abc import Mapping

from breqy.agents.auth.models import AuthBackend, AuthResult
from breqy.agents.credentials import CredentialStore
from breqy.agents.models import AuthSession, AuthStatus
from breqy.domain.enums import AuthSessionStatus


class AuthService:
    """Coordinates provider auth state and secret-backed credentials."""

    def __init__(
        self,
        *,
        credential_store: CredentialStore,
        backends: Mapping[str, AuthBackend],
    ) -> None:
        self.credential_store = credential_store
        self._backends = dict(backends)
        self._status_by_provider: dict[str, AuthStatus] = {}

    def start(self, provider: str) -> AuthSession:
        backend = self._require_backend(provider)
        session = backend.start(provider)
        self._status_by_provider[provider] = AuthStatus(
            provider=session.provider,
            status=session.status,
            flow_kind=session.flow_kind,
            verification_url=session.verification_url,
            user_code=session.user_code,
            display_message=session.display_message,
            last_error=session.last_error,
        )
        return session

    def get_status(self, provider: str) -> AuthStatus:
        stored = self.credential_store.get(provider)
        cached = self._status_by_provider.get(provider)
        resolved: AuthStatus | None = None
        backend_status: AuthStatus | None = None

        backend = self._backends.get(provider)
        if backend is not None:
            backend_status = backend.get_status(provider)
            if backend_status.status != AuthSessionStatus.UNAUTHENTICATED:
                resolved = backend_status

        if resolved is None and stored is not None:
            if cached is not None and cached.status == AuthSessionStatus.AUTHENTICATED:
                resolved = cached
            else:
                resolved = AuthStatus(provider=provider, status=AuthSessionStatus.AUTHENTICATED)

        if resolved is None and backend_status is not None:
            resolved = backend_status

        if resolved is None and cached is not None:
            resolved = cached

        if resolved is None:
            resolved = AuthStatus(provider=provider, status=AuthSessionStatus.UNAUTHENTICATED)

        self._status_by_provider[provider] = resolved
        return resolved

    def submit_code(self, provider: str, code: str) -> AuthStatus:
        return self._complete_submission(provider, self._require_backend(provider).submit_code(provider, code))

    def submit_secret(self, provider: str, secret: str) -> AuthStatus:
        backend = self._require_backend(provider)
        return self._complete_submission(provider, backend.submit_secret(provider, secret))

    def revoke(self, provider: str) -> None:
        flow_kind = self._status_by_provider.get(provider, AuthStatus(
            provider=provider,
            status=AuthSessionStatus.UNAUTHENTICATED,
        )).flow_kind
        self.credential_store.delete(provider)
        backend = self._backends.get(provider)
        if backend is not None:
            backend.revoke(provider)
        self._status_by_provider[provider] = AuthStatus(
            provider=provider,
            status=AuthSessionStatus.UNAUTHENTICATED,
            flow_kind=flow_kind,
        )

    def _complete_submission(self, provider: str, result: AuthResult) -> AuthStatus:
        if result.credential is not None:
            self.credential_store.set(provider, result.credential)
        self._status_by_provider[provider] = result.status
        return result.status

    def _require_backend(self, provider: str) -> AuthBackend:
        backend = self._backends.get(provider)
        if backend is None:
            raise ValueError(f"unknown auth provider: {provider}")
        return backend
