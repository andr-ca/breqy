# system/orchestrator/auth/credential_store.py
from __future__ import annotations
import keyring
import keyring.errors

_SERVICE = "breqy"


class CredentialStore:
    """Thin wrapper around the OS keyring under the 'breqy' service namespace."""

    def get(self, provider: str) -> str | None:
        return keyring.get_password(_SERVICE, provider)

    def set(self, provider: str, token: str) -> None:
        keyring.set_password(_SERVICE, provider, token)

    def delete(self, provider: str) -> None:
        try:
            keyring.delete_password(_SERVICE, provider)
        except keyring.errors.PasswordDeleteError:
            pass
