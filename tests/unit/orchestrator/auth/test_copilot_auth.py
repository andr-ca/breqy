# tests/unit/orchestrator/auth/test_copilot_auth.py
from unittest.mock import patch, MagicMock
from system.orchestrator.auth.copilot_auth import GitHubCopilotAuth
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.auth.base import AuthFlowType


def _store_empty():
    with patch("keyring.get_password", return_value=None):
        return CredentialStore()


def test_provider_name():
    store = _store_empty()
    auth = GitHubCopilotAuth(credential_store=store)
    assert auth.provider_name == "copilot"


def test_flow_type():
    store = _store_empty()
    auth = GitHubCopilotAuth(credential_store=store)
    assert auth.flow_type == AuthFlowType.DEVICE_FLOW


def test_is_authenticated_false_when_no_token():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = GitHubCopilotAuth(credential_store=store)
        assert auth.is_authenticated() is False


def test_is_authenticated_true_when_token_present():
    with patch("keyring.get_password", return_value="ghu_token"):
        store = CredentialStore()
        auth = GitHubCopilotAuth(credential_store=store)
        assert auth.is_authenticated() is True


def test_get_token_returns_stored_token():
    with patch("keyring.get_password", return_value="ghu_token"):
        store = CredentialStore()
        auth = GitHubCopilotAuth(credential_store=store)
        assert auth.get_token() == "ghu_token"


def test_revoke_deletes_token():
    with patch("keyring.delete_password") as mock_del:
        store = CredentialStore()
        auth = GitHubCopilotAuth(credential_store=store)
        auth.revoke()
        mock_del.assert_called_once_with("breqy", "copilot")


def test_request_device_code_calls_github_api():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "device_code": "dev123",
        "user_code": "ABCD-1234",
        "verification_uri": "https://github.com/login/device",
        "expires_in": 900,
        "interval": 5,
    }
    with patch("httpx.post", return_value=mock_response) as mock_post:
        with patch("keyring.get_password", return_value=None):
            store = CredentialStore()
            auth = GitHubCopilotAuth(credential_store=store)
            result = auth.request_device_code()
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            assert "github.com/login/device/code" in call_url
            assert result.device_code == "dev123"
            assert result.user_code == "ABCD-1234"


def test_poll_for_token_returns_token_on_success():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"access_token": "ghu_realtoken"}
    with patch("httpx.post", return_value=mock_response):
        with patch("keyring.get_password", return_value=None):
            with patch("keyring.set_password") as mock_set:
                store = CredentialStore()
                auth = GitHubCopilotAuth(credential_store=store)
                result = auth.poll_for_token("dev123")
                assert result == "ghu_realtoken"
                mock_set.assert_called_once_with("breqy", "copilot", "ghu_realtoken")


def test_poll_for_token_returns_none_when_pending():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"error": "authorization_pending"}
    with patch("httpx.post", return_value=mock_response):
        with patch("keyring.get_password", return_value=None):
            store = CredentialStore()
            auth = GitHubCopilotAuth(credential_store=store)
            result = auth.poll_for_token("dev123")
            assert result is None


def test_request_device_code_coerces_string_interval_and_expires_in():
    """GitHub API may return interval/expires_in as strings; both must be int."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "device_code": "dev123",
        "user_code": "ABCD-1234",
        "verification_uri": "https://github.com/login/device",
        "expires_in": "900",
        "interval": "5",
    }
    with patch("httpx.post", return_value=mock_response):
        with patch("keyring.get_password", return_value=None):
            store = CredentialStore()
            auth = GitHubCopilotAuth(credential_store=store)
            result = auth.request_device_code()
            assert isinstance(result.interval, int)
            assert result.interval == 5
            assert isinstance(result.expires_in, int)
            assert result.expires_in == 900
