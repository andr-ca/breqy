# tests/unit/orchestrator/auth/test_codex_auth.py
from unittest.mock import patch
from system.orchestrator.auth.codex_auth import CodexAuth
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.auth.base import AuthFlowType


def test_provider_name():
    with patch("keyring.get_password", return_value=None):
        auth = CodexAuth(credential_store=CredentialStore())
        assert auth.provider_name == "codex"


def test_flow_type_is_api_key():
    with patch("keyring.get_password", return_value=None):
        auth = CodexAuth(credential_store=CredentialStore())
        assert auth.flow_type == AuthFlowType.API_KEY


def test_is_authenticated_false_when_no_token():
    with patch("keyring.get_password", return_value=None):
        auth = CodexAuth(credential_store=CredentialStore())
        assert auth.is_authenticated() is False


def test_is_authenticated_true_when_token_present():
    with patch("keyring.get_password", return_value="sk-oai_token"):
        auth = CodexAuth(credential_store=CredentialStore())
        assert auth.is_authenticated() is True


def test_set_key_stores_in_keyring():
    with patch("keyring.set_password") as mock_set:
        auth = CodexAuth(credential_store=CredentialStore())
        auth.set_key("sk-mykey")
        mock_set.assert_called_once_with("breqy", "codex", "sk-mykey")


def test_revoke_deletes_token():
    with patch("keyring.delete_password") as mock_del:
        auth = CodexAuth(credential_store=CredentialStore())
        auth.revoke()
        mock_del.assert_called_once_with("breqy", "codex")
