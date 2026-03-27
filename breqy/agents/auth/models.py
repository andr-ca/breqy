"""Typed auth contracts for provider-specific backends."""
from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from breqy.agents.models import AuthSession, AuthStatus, ProviderCredential


class AuthResult(BaseModel):
    """Auth submission result, optionally including a credential to persist."""

    status: AuthStatus
    credential: ProviderCredential | None = None


class AuthBackend(ABC):
    """Provider-specific auth backend contract."""

    @abstractmethod
    def start(self, provider: str) -> AuthSession: ...

    @abstractmethod
    def get_status(self, provider: str) -> AuthStatus: ...

    @abstractmethod
    def submit_code(self, provider: str, code: str) -> AuthResult: ...

    @abstractmethod
    def submit_secret(self, provider: str, secret: str) -> AuthResult: ...

    @abstractmethod
    def revoke(self, provider: str) -> None: ...
