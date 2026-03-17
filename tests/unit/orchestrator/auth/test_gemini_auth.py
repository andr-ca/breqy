# tests/unit/orchestrator/auth/test_gemini_auth.py
from unittest.mock import patch, MagicMock
from system.orchestrator.auth.gemini_auth import GeminiAuth
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.auth.base import AuthFlowType


def test_provider_name():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = GeminiAuth(credential_store=store)
        assert auth.provider_name == "gemini"


def test_flow_type():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = GeminiAuth(credential_store=store)
        assert auth.flow_type == AuthFlowType.DEVICE_FLOW


def test_is_authenticated_false_when_no_token():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = GeminiAuth(credential_store=store)
        assert auth.is_authenticated() is False


def test_is_authenticated_true_when_token_present():
    with patch("keyring.get_password", return_value="ya29_token"):
        store = CredentialStore()
        auth = GeminiAuth(credential_store=store)
        assert auth.is_authenticated() is True


def test_get_token_returns_stored_token():
    with patch("keyring.get_password", return_value="ya29_token"):
        store = CredentialStore()
        auth = GeminiAuth(credential_store=store)
        assert auth.get_token() == "ya29_token"


def test_revoke_deletes_token():
    with patch("keyring.delete_password") as mock_del:
        store = CredentialStore()
        auth = GeminiAuth(credential_store=store)
        auth.revoke()
        mock_del.assert_called_once_with("breqy", "gemini")


def test_request_device_code_calls_google_api():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "device_code": "dev_gemini",
        "user_code": "WXYZ-9876",
        "verification_url": "https://www.google.com/device",
        "expires_in": 1800,
        "interval": 5,
    }
    with patch("httpx.post", return_value=mock_response) as mock_post:
        with patch("keyring.get_password", return_value=None):
            store = CredentialStore()
            auth = GeminiAuth(credential_store=store)
            result = auth.request_device_code()
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            assert "oauth2.googleapis.com/device/code" in call_url
            assert result.device_code == "dev_gemini"
            assert result.user_code == "WXYZ-9876"


def test_poll_for_token_returns_token_on_success():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"access_token": "ya29_realtoken"}
    with patch("httpx.post", return_value=mock_response):
        with patch("keyring.set_password") as mock_set:
            store = CredentialStore()
            auth = GeminiAuth(credential_store=store)
            result = auth.poll_for_token("dev_gemini")
            assert result == "ya29_realtoken"
            mock_set.assert_called_once_with("breqy", "gemini", "ya29_realtoken")


def test_poll_for_token_returns_none_when_pending():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"error": "authorization_pending"}
    with patch("httpx.post", return_value=mock_response):
        with patch("keyring.get_password", return_value=None):
            store = CredentialStore()
            auth = GeminiAuth(credential_store=store)
            result = auth.poll_for_token("dev_gemini")
            assert result is None
