# tests/unit/orchestrator/auth/test_claude_auth.py
from unittest.mock import patch, MagicMock
from system.orchestrator.auth.claude_auth import ClaudeAuth
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.auth.base import AuthFlowType


def test_provider_name():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        assert auth.provider_name == "claude"


def test_flow_type():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        assert auth.flow_type == AuthFlowType.PKCE


def test_is_authenticated_false_when_no_token():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        assert auth.is_authenticated() is False


def test_is_authenticated_true_when_token_present():
    with patch("keyring.get_password", return_value="ant_token"):
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        assert auth.is_authenticated() is True


def test_get_auth_url_contains_client_id():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        url = auth.get_auth_url()
        assert "claude.ai/oauth/authorize" in url
        assert "9d1c250a-e61b-44d9-88ed-5944d1962f5e" in url
        assert "code_challenge" in url
        assert "S256" in url


def test_get_auth_url_stores_verifier():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        assert auth._code_verifier is None
        auth.get_auth_url()
        assert auth._code_verifier is not None
        assert len(auth._code_verifier) > 0


def test_exchange_code_stores_token():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"access_token": "ant_real_token"}
    with patch("httpx.post", return_value=mock_response):
        with patch("keyring.set_password") as mock_set:
            store = CredentialStore()
            auth = ClaudeAuth(credential_store=store)
            auth._code_verifier = "test_verifier_abc"
            auth.exchange_code("auth_code_xyz")
            mock_set.assert_called_once_with("breqy", "claude", "ant_real_token")


def test_exchange_code_calls_token_endpoint():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"access_token": "ant_real_token"}
    with patch("httpx.post", return_value=mock_response) as mock_post:
        with patch("keyring.set_password"):
            store = CredentialStore()
            auth = ClaudeAuth(credential_store=store)
            auth._code_verifier = "test_verifier_abc"
            auth.exchange_code("auth_code_xyz")
            call_url = mock_post.call_args[0][0]
            assert "api.anthropic.com/oauth/token" in call_url


def test_revoke_deletes_token():
    with patch("keyring.delete_password") as mock_del:
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        auth.revoke()
        mock_del.assert_called_once_with("breqy", "claude")
