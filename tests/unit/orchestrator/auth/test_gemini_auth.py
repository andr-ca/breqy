# tests/unit/orchestrator/auth/test_gemini_auth.py
from unittest.mock import patch
from system.orchestrator.auth.gemini_auth import GeminiAuth
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.auth.base import AuthFlowType


def test_provider_name():
    with patch("keyring.get_password", return_value=None):
        auth = GeminiAuth(credential_store=CredentialStore())
        assert auth.provider_name == "gemini"


def test_flow_type_is_api_key():
    with patch("keyring.get_password", return_value=None):
        auth = GeminiAuth(credential_store=CredentialStore())
        assert auth.flow_type == AuthFlowType.API_KEY


def test_is_authenticated_false_when_no_token():
    with patch("keyring.get_password", return_value=None):
        auth = GeminiAuth(credential_store=CredentialStore())
        assert auth.is_authenticated() is False


def test_is_authenticated_true_when_token_present():
    with patch("keyring.get_password", return_value="AIza_token"):
        auth = GeminiAuth(credential_store=CredentialStore())
        assert auth.is_authenticated() is True


def test_get_token_returns_stored_token():
    with patch("keyring.get_password", return_value="AIza_token"):
        auth = GeminiAuth(credential_store=CredentialStore())
        assert auth.get_token() == "AIza_token"


def test_set_key_stores_in_keyring():
    with patch("keyring.set_password") as mock_set:
        auth = GeminiAuth(credential_store=CredentialStore())
        auth.set_key("AIza_mykey")
        mock_set.assert_called_once_with("breqy", "gemini", "AIza_mykey")


def test_revoke_deletes_token():
    with patch("keyring.delete_password") as mock_del:
        auth = GeminiAuth(credential_store=CredentialStore())
        auth.revoke()
        mock_del.assert_called_once_with("breqy", "gemini")


def test_key_url_points_to_google_ai_studio():
    with patch("keyring.get_password", return_value=None):
        auth = GeminiAuth(credential_store=CredentialStore())
        assert auth.key_url == "https://aistudio.google.com/apikey"
