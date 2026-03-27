"""Typed runtime models for agent execution and authentication."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, SecretStr

from breqy.domain.enums import AuthFlowKind, AuthSessionStatus, CredentialKind


class ProviderCredential(BaseModel):
    provider: str
    credential_kind: CredentialKind
    secret_value: SecretStr
    refresh_token: SecretStr | None = None
    expires_at: datetime | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class AuthSession(BaseModel):
    provider: str
    flow_kind: AuthFlowKind
    status: AuthSessionStatus
    verification_url: str = ""
    user_code: str = ""
    display_message: str = ""
    last_error: str = ""


class AuthStatus(BaseModel):
    provider: str
    status: AuthSessionStatus
    flow_kind: AuthFlowKind | None = None
    verification_url: str = ""
    user_code: str = ""
    display_message: str = ""
    last_error: str = ""
    authenticated_at: datetime | None = None
