"""SecretProvider interface with keyring and env fallback implementations."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod


class SecretProvider(ABC):
    """Abstract secret storage interface."""

    @abstractmethod
    def get(self, key: str) -> str | None: ...

    @abstractmethod
    def set(self, key: str, value: str) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class EnvSecretProvider(SecretProvider):
    """Read secrets from environment variables. Fallback for dev/testing."""

    def get(self, key: str) -> str | None:
        return os.environ.get(f"BREQY_SECRET_{key.upper()}")

    def set(self, key: str, value: str) -> None:
        os.environ[f"BREQY_SECRET_{key.upper()}"] = value

    def delete(self, key: str) -> None:
        os.environ.pop(f"BREQY_SECRET_{key.upper()}", None)


class KeyringSecretProvider(SecretProvider):
    """Use system keyring for secret storage.

    Secrets are stored under the 'breqy' service namespace.
    Import of keyring is deferred to avoid hard dependency at module load.
    """

    SERVICE_NAME = "breqy"

    def get(self, key: str) -> str | None:
        import keyring  # noqa: PLC0415
        return keyring.get_password(self.SERVICE_NAME, key)

    def set(self, key: str, value: str) -> None:
        import keyring  # noqa: PLC0415
        keyring.set_password(self.SERVICE_NAME, key, value)

    def delete(self, key: str) -> None:
        import keyring  # noqa: PLC0415
        try:
            keyring.delete_password(self.SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass
