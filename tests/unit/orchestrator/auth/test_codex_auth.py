# tests/unit/orchestrator/auth/test_codex_auth.py
from unittest.mock import patch, MagicMock
from system.orchestrator.auth.codex_auth import CodexAuth
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.auth.base import AuthFlowType


def test_provider_name():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = CodexAuth(credential_store=store)
        assert auth.provider_name == "codex"


def test_flow_type():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = CodexAuth(credential_store=store)
        assert auth.flow_type == AuthFlowType.DEVICE_FLOW


def test_is_authenticated_false_when_no_token():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = CodexAuth(credential_store=store)
        assert auth.is_authenticated() is False


def test_is_authenticated_true_when_token_present():
    with patch("keyring.get_password", return_value="oai_token"):
        store = CredentialStore()
        auth = CodexAuth(credential_store=store)
        assert auth.is_authenticated() is True


def test_revoke_deletes_token():
    with patch("keyring.delete_password") as mock_del:
        store = CredentialStore()
        auth = CodexAuth(credential_store=store)
        auth.revoke()
        mock_del.assert_called_once_with("breqy", "codex")


def test_request_device_code_calls_openai_api():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "device_code": "dev_codex",
        "user_code": "QRST-5678",
        "verification_uri": "https://auth.openai.com/activate",
        "expires_in": 900,
        "interval": 5,
    }
    with patch("httpx.post", return_value=mock_response) as mock_post:
        with patch("keyring.get_password", return_value=None):
            store = CredentialStore()
            auth = CodexAuth(credential_store=store)
            result = auth.request_device_code()
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            assert "deviceauth/usercode" in call_url
            assert result.device_code == "dev_codex"
            assert result.user_code == "QRST-5678"


def test_poll_for_token_returns_none_when_pending():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"error": "authorization_pending"}
    with patch("httpx.post", return_value=mock_response):
        with patch("keyring.get_password", return_value=None):
            store = CredentialStore()
            auth = CodexAuth(credential_store=store)
            result = auth.poll_for_token("dev_codex")
            assert result is None


def test_poll_for_token_does_pkce_exchange_on_approval():
    """When poll returns a code, CodexAuth does PKCE exchange and stores the token."""
    poll_response = MagicMock()
    poll_response.raise_for_status.return_value = None
    poll_response.json.return_value = {"code": "auth_code_abc"}

    exchange_response = MagicMock()
    exchange_response.raise_for_status.return_value = None
    exchange_response.json.return_value = {"access_token": "oai_final_token"}

    with patch("httpx.post", side_effect=[poll_response, exchange_response]):
        with patch("keyring.set_password") as mock_set:
            store = CredentialStore()
            auth = CodexAuth(credential_store=store)
            # pre-generate device code to ensure verifier is stored
            auth._code_verifier = "test_verifier_123"
            result = auth.poll_for_token("dev_codex")
            assert result == "oai_final_token"
            mock_set.assert_called_once_with("breqy", "codex", "oai_final_token")
