"""GitHub Copilot OAuth device flow authenticator."""
from __future__ import annotations

import structlog
from pydantic import BaseModel, SecretStr

from breqy.agents.credentials import CredentialStore
from breqy.agents.models import ProviderCredential
from breqy.domain.enums import CredentialKind

logger = structlog.get_logger(__name__)


class CopilotAuthError(Exception):
    """Raised when device flow fails (expired, denied, network error)."""


class DeviceFlowInfo(BaseModel):
    """Response from GitHub device flow initiation."""

    user_code: str
    verification_uri: str
    device_code: str
    interval: int
    expires_in: int


class CopilotAuthenticator:
    """Manages GitHub OAuth device flow and token persistence for Copilot."""

    GITHUB_CLIENT_ID: str = "Ov23li8tweQw6odWQebz"
    DEVICE_CODE_URL: str = "https://github.com/login/device/code"
    ACCESS_TOKEN_URL: str = "https://github.com/login/oauth/access_token"
    OAUTH_SCOPE: str = "read:user"
    POLLING_SAFETY_MARGIN_S: float = 3.0

    def __init__(self, credential_store: CredentialStore) -> None:
        self._credential_store = credential_store

    def get_token(self) -> str | None:
        """Retrieve stored OAuth token, or None if not authenticated."""
        credential = self._credential_store.get("copilot")
        if credential is None:
            return None
        return credential.secret_value.get_secret_value()

    def clear_token(self) -> None:
        """Remove stored token (used on 401 to force re-auth)."""
        self._credential_store.delete("copilot")
        logger.info("copilot_token_cleared")

    def _store_token(self, access_token: str) -> None:
        """Persist OAuth token to credential store."""
        self._credential_store.set(
            "copilot",
            ProviderCredential(
                provider="copilot",
                credential_kind=CredentialKind.ACCESS_TOKEN,
                secret_value=SecretStr(access_token),
                metadata={"auth_flow": "device"},
            ),
        )
        logger.info("copilot_token_stored")
