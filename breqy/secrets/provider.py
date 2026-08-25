"""SecretProvider interface with keyring and env fallback implementations."""
from __future__ import annotations

import os
import stat
from abc import ABC, abstractmethod
from pathlib import Path


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
        import keyring
        return keyring.get_password(self.SERVICE_NAME, key)

    def set(self, key: str, value: str) -> None:
        import keyring
        keyring.set_password(self.SERVICE_NAME, key, value)

    def delete(self, key: str) -> None:
        import keyring
        try:
            keyring.delete_password(self.SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass


class FileSecretProvider(SecretProvider):
    """File-based secret storage. Fallback when keyring is unavailable.

    Each secret is stored as a separate file under ``base_dir``
    (default ``~/.breqy/secrets``). Files are created with owner-only
    permissions (0600).
    """

    _DEFAULT_DIR_NAME = ".breqy/secrets"

    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path.home() / self._DEFAULT_DIR_NAME
        self._base_dir = base_dir

    def get(self, key: str) -> str | None:
        path = self._base_dir / key
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def set(self, key: str, value: str) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        path = self._base_dir / key
        path.write_text(value, encoding="utf-8")
        # Restrict to owner-only read/write
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def delete(self, key: str) -> None:
        path = self._base_dir / key
        try:
            path.unlink()
        except FileNotFoundError:
            pass
