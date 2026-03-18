# tests/unit/orchestrator/auth/test_codex_auth.py
from unittest.mock import patch, MagicMock
from system.orchestrator.auth.codex_auth import CodexAuth
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.auth.base import AuthFlowType


def test_provider_name():
    with patch("keyring.get_password", return_value=None):
        auth = CodexAuth(credential_store=CredentialStore())
        assert auth.provider_name == "codex"


def test_flow_type_is_device_flow():
    with patch("keyring.get_password", return_value=None):
        auth = CodexAuth(credential_store=CredentialStore())
        assert auth.flow_type == AuthFlowType.DEVICE_FLOW


def test_is_authenticated_false_when_no_token():
    with patch("keyring.get_password", return_value=None):
        auth = CodexAuth(credential_store=CredentialStore())
        assert auth.is_authenticated() is False


def test_is_authenticated_true_when_token_present():
    with patch("keyring.get_password", return_value="oai_token"):
        auth = CodexAuth(credential_store=CredentialStore())
        assert auth.is_authenticated() is True


def test_revoke_deletes_token():
    with patch("keyring.delete_password") as mock_del:
        auth = CodexAuth(credential_store=CredentialStore())
        auth.revoke()
        mock_del.assert_called_once_with("breqy", "codex")


def test_request_device_code_posts_to_usercode_endpoint():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "device_auth_id": "dauth_abc123",
        "user_code": "QRST-5678",
        "expires_in": 900,
        "interval": 5,
    }
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        with patch("keyring.get_password", return_value=None):
            auth = CodexAuth(credential_store=CredentialStore())
            result = auth.request_device_code()
            call_url = mock_post.call_args[0][0]
            assert "deviceauth/usercode" in call_url
            assert result.device_code == "dauth_abc123"
            assert result.user_code == "QRST-5678"
            assert result.verification_uri == "https://auth.openai.com/codex/device"


def test_poll_returns_none_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    with patch("httpx.post", return_value=mock_resp):
        with patch("keyring.get_password", return_value=None):
            auth = CodexAuth(credential_store=CredentialStore())
            auth._user_code = "QRST-5678"
            result = auth.poll_for_token("dauth_abc123")
            assert result is None


def test_request_device_code_coerces_string_interval_and_parses_expires_at():
    """API returns interval as string and expires_at instead of expires_in — must survive."""
    import datetime, math
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    # Real API shape: interval is a string, expires_at is an ISO timestamp
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=840)
    mock_resp.json.return_value = {
        "device_auth_id": "dauth_xyz",
        "user_code": "ABCD-1234",
        "interval": "5",  # string, not int
        "expires_at": future.isoformat(),
    }
    with patch("httpx.post", return_value=mock_resp):
        with patch("keyring.get_password", return_value=None):
            auth = CodexAuth(credential_store=CredentialStore())
            result = auth.request_device_code()
            assert result.interval == 5  # must be int
            assert isinstance(result.interval, int)
            assert result.expires_in > 0  # must be derived from expires_at
            assert math.isclose(result.expires_in, 840, abs_tol=5)


def test_poll_exchanges_code_on_200_and_stores_token():
    """When poll returns 200 with authorization_code+code_verifier, exchanges and stores token."""
    poll_resp = MagicMock()
    poll_resp.status_code = 200
    poll_resp.json.return_value = {
        "authorization_code": "auth_code_xyz",
        "code_verifier": "server_verifier_abc",
    }
    exchange_resp = MagicMock()
    exchange_resp.raise_for_status.return_value = None
    exchange_resp.json.return_value = {"access_token": "oai_final_token"}

    with patch("httpx.post", side_effect=[poll_resp, exchange_resp]):
        with patch("keyring.set_password") as mock_set:
            auth = CodexAuth(credential_store=CredentialStore())
            auth._user_code = "QRST-5678"
            result = auth.poll_for_token("dauth_abc123")
            assert result == "oai_final_token"
            mock_set.assert_called_once_with("breqy", "codex", "oai_final_token")
