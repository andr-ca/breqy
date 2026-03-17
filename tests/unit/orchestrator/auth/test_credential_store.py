# tests/unit/orchestrator/auth/test_credential_store.py
from unittest.mock import patch
from system.orchestrator.auth.credential_store import CredentialStore


def test_get_returns_none_when_not_set():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        assert store.get("copilot") is None


def test_set_stores_token():
    with patch("keyring.get_password", return_value=None), \
         patch("keyring.set_password") as mock_set:
        store = CredentialStore()
        store.set("copilot", "ghu_token")
        mock_set.assert_called_once_with("breqy", "copilot", "ghu_token")


def test_get_returns_stored_token():
    with patch("keyring.get_password", return_value="ghu_token"):
        store = CredentialStore()
        assert store.get("copilot") == "ghu_token"


def test_delete_removes_token():
    with patch("keyring.get_password", return_value=None), \
         patch("keyring.delete_password") as mock_del:
        store = CredentialStore()
        store.delete("copilot")
        mock_del.assert_called_once_with("breqy", "copilot")


def test_delete_ignores_not_found():
    import keyring.errors
    with patch("keyring.get_password", return_value=None), \
         patch("keyring.delete_password", side_effect=keyring.errors.PasswordDeleteError):
        store = CredentialStore()
        store.delete("copilot")  # must not raise
