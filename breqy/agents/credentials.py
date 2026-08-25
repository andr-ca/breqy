"""Provider credential storage over the secret backend."""
from __future__ import annotations

import json

import structlog
from pydantic import ValidationError

from breqy.agents.models import ProviderCredential
from breqy.secrets.provider import SecretProvider

logger = structlog.get_logger(__name__)


class CredentialStore:
    """Typed provider credential storage backed by SecretProvider."""

    def __init__(self, secret_provider: SecretProvider) -> None:
        self._secret_provider = secret_provider

    def get(self, provider: str) -> ProviderCredential | None:
        payload = self._secret_provider.get(self._secret_key(provider))
        if not payload or not payload.strip():
            return None
        try:
            return ProviderCredential.model_validate(json.loads(payload))
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "Ignoring unreadable credential in keyring",
                provider=provider,
                error=str(exc),
            )
            return None

    def set(self, provider: str, credential: ProviderCredential) -> None:
        if credential.provider != provider:
            message = (
                "credential provider mismatch: "
                f"expected {provider!r}, got {credential.provider!r}"
            )
            raise ValueError(message)

        self._secret_provider.set(
            self._secret_key(provider),
            json.dumps(self._serialize(credential), sort_keys=True),
        )

    def delete(self, provider: str) -> None:
        self._secret_provider.delete(self._secret_key(provider))

    def _secret_key(self, provider: str) -> str:
        return provider

    def _serialize(self, credential: ProviderCredential) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider": credential.provider,
            "credential_kind": credential.credential_kind,
            "secret_value": credential.secret_value.get_secret_value(),
            "refresh_token": None,
            "expires_at": None,
            "metadata": credential.metadata,
        }
        if credential.refresh_token is not None:
            payload["refresh_token"] = credential.refresh_token.get_secret_value()
        if credential.expires_at is not None:
            payload["expires_at"] = credential.expires_at.isoformat()
        return payload
