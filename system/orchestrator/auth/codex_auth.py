# system/orchestrator/auth/codex_auth.py
from __future__ import annotations
from system.orchestrator.auth.base import ApiKeyProvider
from system.orchestrator.auth.credential_store import CredentialStore


class CodexAuth(ApiKeyProvider):
    """OpenAI Codex authentication via API key.

    Obtain a key at https://platform.openai.com/api-keys — no OAuth required.
    The key is stored under the 'codex' namespace in the OS keyring.
    """

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store

    @property
    def provider_name(self) -> str:
        return "codex"

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def set_key(self, api_key: str) -> None:
        """Store the API key in the credential store."""
        self._store.set(self.provider_name, api_key)
