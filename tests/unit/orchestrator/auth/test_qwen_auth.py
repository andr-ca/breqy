# tests/unit/orchestrator/auth/test_qwen_auth.py
from unittest.mock import patch
from system.orchestrator.auth.qwen_auth import QwenAuth
from system.orchestrator.auth.credential_store import CredentialStore


def test_set_key_stores_in_keyring():
    with patch("keyring.set_password") as mock_set:
        store = CredentialStore()
        auth = QwenAuth(credential_store=store)
        auth.set_key("sk-test-key")
        mock_set.assert_called_once_with("breqy", "qwen", "sk-test-key")


def test_is_authenticated_after_set_key():
    with patch("keyring.get_password", return_value="sk-test-key"):
        store = CredentialStore()
        auth = QwenAuth(credential_store=store)
        assert auth.is_authenticated() is True


def test_is_authenticated_false_when_no_key():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = QwenAuth(credential_store=store)
        assert auth.is_authenticated() is False


def test_revoke_deletes_from_keyring():
    with patch("keyring.delete_password") as mock_del:
        store = CredentialStore()
        auth = QwenAuth(credential_store=store)
        auth.revoke()
        mock_del.assert_called_once_with("breqy", "qwen")


def test_key_url_points_to_international_model_studio():
    with patch("keyring.get_password", return_value=None):
        auth = QwenAuth(credential_store=CredentialStore())
        assert auth.key_url == "https://bailian.console.alibabacloud.com/"
