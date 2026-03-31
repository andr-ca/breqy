"""Tests for GitHub Copilot OAuth device flow authenticator."""

from __future__ import annotations

import httpx
from unittest.mock import patch, MagicMock

import pytest
from pydantic import SecretStr

from breqy.agents.credentials import CredentialStore
from breqy.agents.models import ProviderCredential
from breqy.domain.enums import CredentialKind
from breqy.secrets.provider import SecretProvider


class MemorySecretProvider(SecretProvider):
    """In-memory secret provider for unit tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def _make_credential_store() -> CredentialStore:
    return CredentialStore(MemorySecretProvider())


def _store_token(store: CredentialStore, token: str = "gho_test123") -> None:
    store.set(
        "copilot",
        ProviderCredential(
            provider="copilot",
            credential_kind=CredentialKind.ACCESS_TOKEN,
            secret_value=SecretStr(token),
            metadata={"auth_flow": "device"},
        ),
    )


class TestDeviceFlowInfo:
    def test_device_flow_info_fields(self) -> None:
        from breqy.agents.providers.copilot_auth import DeviceFlowInfo

        info = DeviceFlowInfo(
            user_code="ABCD-EFGH",
            verification_uri="https://github.com/login/device",
            device_code="device123",
            interval=5,
            expires_in=900,
        )
        assert info.user_code == "ABCD-EFGH"
        assert info.verification_uri == "https://github.com/login/device"
        assert info.device_code == "device123"
        assert info.interval == 5
        assert info.expires_in == 900


class TestCopilotAuthError:
    def test_copilot_auth_error_is_exception(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthError

        err = CopilotAuthError("token expired")
        assert isinstance(err, Exception)
        assert str(err) == "token expired"


class TestGetToken:
    def test_get_token_from_store(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        _store_token(store, "gho_mytoken")
        auth = CopilotAuthenticator(store)
        assert auth.get_token() == "gho_mytoken"

    def test_get_token_empty_store(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)
        assert auth.get_token() is None


class TestStoreToken:
    def test_store_token_persists_and_retrieves(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)
        assert auth.get_token() is None
        auth._store_token("gho_new_token")
        assert auth.get_token() == "gho_new_token"


class TestClearToken:
    def test_clear_token(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        _store_token(store, "gho_toremove")
        auth = CopilotAuthenticator(store)
        assert auth.get_token() == "gho_toremove"
        auth.clear_token()
        assert auth.get_token() is None


class TestStartDeviceFlow:
    def test_start_device_flow_success(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator, DeviceFlowInfo

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "device_code": "dc_abc123",
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }

        with patch(
            "breqy.agents.providers.copilot_auth.httpx.post", return_value=mock_response
        ) as mock_post:
            info = auth.start_device_flow()

        assert isinstance(info, DeviceFlowInfo)
        assert info.user_code == "ABCD-EFGH"
        assert info.device_code == "dc_abc123"
        assert info.verification_uri == "https://github.com/login/device"
        assert info.interval == 5
        assert info.expires_in == 900

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == "https://github.com/login/device/code"
        body = call_kwargs[1]["json"]
        assert body["client_id"] == "Iv1.b507a08c87ecfe98"
        assert body["scope"] == "read:user"

    def test_start_device_flow_http_error(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator, CopilotAuthError

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )

        with patch("breqy.agents.providers.copilot_auth.httpx.post", return_value=mock_response):
            with pytest.raises(CopilotAuthError, match="Failed to initiate device flow"):
                auth.start_device_flow()


class TestPollForToken:
    def test_poll_for_token_immediate_success(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "gho_success123"}

        with patch("breqy.agents.providers.copilot_auth.httpx.post", return_value=mock_response):
            with patch("breqy.agents.providers.copilot_auth.time.sleep") as mock_sleep:
                token = auth.poll_for_token("dc_abc", interval=5)

        assert token == "gho_success123"
        # Verify token was stored
        assert auth.get_token() == "gho_success123"
        # No sleep on immediate success — sleep only happens on pending/slow_down
        mock_sleep.assert_not_called()

    def test_poll_for_token_pending_then_success(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)

        pending_response = MagicMock()
        pending_response.status_code = 200
        pending_response.json.return_value = {"error": "authorization_pending"}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"access_token": "gho_delayed"}

        with patch(
            "breqy.agents.providers.copilot_auth.httpx.post",
            side_effect=[pending_response, success_response],
        ):
            with patch("breqy.agents.providers.copilot_auth.time.sleep") as mock_sleep:
                token = auth.poll_for_token("dc_abc", interval=5)

        assert token == "gho_delayed"
        # Should have slept once (interval + safety margin)
        mock_sleep.assert_called_once_with(5 + 3.0)

    def test_poll_for_token_slow_down(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)

        slow_response = MagicMock()
        slow_response.status_code = 200
        slow_response.json.return_value = {"error": "slow_down", "interval": 10}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"access_token": "gho_after_slow"}

        with patch(
            "breqy.agents.providers.copilot_auth.httpx.post",
            side_effect=[slow_response, success_response],
        ):
            with patch("breqy.agents.providers.copilot_auth.time.sleep") as mock_sleep:
                token = auth.poll_for_token("dc_abc", interval=5)

        assert token == "gho_after_slow"
        # First sleep should use server interval (10) + safety margin
        mock_sleep.assert_any_call(10 + 3.0)

    def test_poll_for_token_expired(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator, CopilotAuthError

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)

        expired_response = MagicMock()
        expired_response.status_code = 200
        expired_response.json.return_value = {"error": "expired_token"}

        with patch("breqy.agents.providers.copilot_auth.httpx.post", return_value=expired_response):
            with patch("breqy.agents.providers.copilot_auth.time.sleep"):
                with pytest.raises(CopilotAuthError, match="expired"):
                    auth.poll_for_token("dc_abc", interval=5)

    def test_poll_for_token_denied(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator, CopilotAuthError

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)

        denied_response = MagicMock()
        denied_response.status_code = 200
        denied_response.json.return_value = {"error": "access_denied"}

        with patch("breqy.agents.providers.copilot_auth.httpx.post", return_value=denied_response):
            with patch("breqy.agents.providers.copilot_auth.time.sleep"):
                with pytest.raises(CopilotAuthError, match="denied"):
                    auth.poll_for_token("dc_abc", interval=5)

    def test_poll_for_token_unknown_error(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator, CopilotAuthError

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)

        unknown_response = MagicMock()
        unknown_response.status_code = 200
        unknown_response.json.return_value = {"error": "some_new_error"}

        with patch("breqy.agents.providers.copilot_auth.httpx.post", return_value=unknown_response):
            with patch("breqy.agents.providers.copilot_auth.time.sleep"):
                with pytest.raises(CopilotAuthError, match="some_new_error"):
                    auth.poll_for_token("dc_abc", interval=5)

    def test_poll_for_token_network_error(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator, CopilotAuthError

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)

        with patch(
            "breqy.agents.providers.copilot_auth.httpx.post",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            with patch("breqy.agents.providers.copilot_auth.time.sleep"):
                with pytest.raises(CopilotAuthError, match="Network error"):
                    auth.poll_for_token("dc_abc", interval=5)


class TestStartDeviceFlowNetworkError:
    def test_start_device_flow_network_error(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator, CopilotAuthError

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)

        with patch(
            "breqy.agents.providers.copilot_auth.httpx.post",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            with pytest.raises(CopilotAuthError, match="Failed to initiate device flow"):
                auth.start_device_flow()


def _make_session_token(exp_offset_s: int = 1800) -> str:
    """Build a fake Copilot session token with exp set relative to now."""
    import time

    exp = int(time.time()) + exp_offset_s
    return f"tid=test123;exp={exp};sku=copilot_pro;st=dotcom;chat=1"


class TestGetCopilotToken:
    """Tests for the Copilot session token exchange (OAuth→session token)."""

    def test_exchanges_oauth_token_for_session_token(self) -> None:
        """get_copilot_token() should call /copilot_internal/v2/token and return session token."""
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        _store_token(store, "gho_oauth_abc")
        auth = CopilotAuthenticator(store)

        session_token = _make_session_token(exp_offset_s=1800)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "token": session_token,
            "expires_at": 1800,
        }

        with patch(
            "breqy.agents.providers.copilot_auth.httpx.get", return_value=mock_response
        ) as mock_get:
            result = auth.get_copilot_token()

        assert result == session_token
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "copilot_internal/v2/token" in call_args[0][0]
        assert "gho_oauth_abc" in call_args[1]["headers"]["Authorization"]

    def test_caches_session_token_on_second_call(self) -> None:
        """Second call should return cached token without another HTTP request."""
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        _store_token(store, "gho_oauth_abc")
        auth = CopilotAuthenticator(store)

        session_token = _make_session_token(exp_offset_s=1800)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": session_token}

        with patch(
            "breqy.agents.providers.copilot_auth.httpx.get", return_value=mock_response
        ) as mock_get:
            first = auth.get_copilot_token()
            second = auth.get_copilot_token()

        assert first == second == session_token
        # Only one HTTP call — second was served from cache
        assert mock_get.call_count == 1

    def test_refreshes_expired_session_token(self) -> None:
        """If cached session token is expired, a new one should be fetched."""
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        _store_token(store, "gho_oauth_abc")
        auth = CopilotAuthenticator(store)

        expired_token = _make_session_token(exp_offset_s=-60)  # Already expired
        fresh_token = _make_session_token(exp_offset_s=1800)

        expired_resp = MagicMock()
        expired_resp.status_code = 200
        expired_resp.json.return_value = {"token": expired_token}

        fresh_resp = MagicMock()
        fresh_resp.status_code = 200
        fresh_resp.json.return_value = {"token": fresh_token}

        with patch(
            "breqy.agents.providers.copilot_auth.httpx.get",
            side_effect=[expired_resp, fresh_resp],
        ) as mock_get:
            first = auth.get_copilot_token()
            # First call returns expired token (but it's still returned since just fetched)
            # Second call should detect it's expired and refetch
            second = auth.get_copilot_token()

        assert second == fresh_token
        assert mock_get.call_count == 2

    def test_returns_none_when_no_oauth_token(self) -> None:
        """If there is no stored OAuth token, get_copilot_token should return None."""
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        auth = CopilotAuthenticator(store)
        assert auth.get_copilot_token() is None

    def test_raises_on_http_error(self) -> None:
        """If the token exchange endpoint returns an error, raise CopilotAuthError."""
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator, CopilotAuthError

        store = _make_credential_store()
        _store_token(store, "gho_oauth_abc")
        auth = CopilotAuthenticator(store)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )

        with patch("breqy.agents.providers.copilot_auth.httpx.get", return_value=mock_response):
            with pytest.raises(CopilotAuthError, match="token exchange"):
                auth.get_copilot_token()

    def test_raises_on_network_error(self) -> None:
        """Network failures during token exchange should raise CopilotAuthError."""
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator, CopilotAuthError

        store = _make_credential_store()
        _store_token(store, "gho_oauth_abc")
        auth = CopilotAuthenticator(store)

        with patch(
            "breqy.agents.providers.copilot_auth.httpx.get",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            with pytest.raises(CopilotAuthError, match="token exchange"):
                auth.get_copilot_token()

    def test_sends_correct_headers(self) -> None:
        """Token exchange should send editor-version and user-agent headers."""
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        _store_token(store, "gho_test_token")
        auth = CopilotAuthenticator(store)

        session_token = _make_session_token(exp_offset_s=1800)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": session_token}

        with patch(
            "breqy.agents.providers.copilot_auth.httpx.get", return_value=mock_response
        ) as mock_get:
            auth.get_copilot_token()

        headers = mock_get.call_args[1]["headers"]
        assert headers["Authorization"] == "token gho_test_token"
        assert "editor-version" in {k.lower() for k in headers}
        assert "user-agent" in {k.lower() for k in headers}


class TestParseTokenExpiry:
    """Tests for parsing expiry from Copilot session token format."""

    def test_extracts_exp_from_token(self) -> None:
        from breqy.agents.providers.copilot_auth import _parse_token_expiry

        token = "tid=abc;exp=1700000000;sku=copilot_pro"
        assert _parse_token_expiry(token) == 1700000000

    def test_returns_zero_for_missing_exp(self) -> None:
        from breqy.agents.providers.copilot_auth import _parse_token_expiry

        token = "tid=abc;sku=copilot_pro"
        assert _parse_token_expiry(token) == 0

    def test_returns_zero_for_invalid_exp(self) -> None:
        from breqy.agents.providers.copilot_auth import _parse_token_expiry

        token = "tid=abc;exp=notanumber;sku=copilot_pro"
        assert _parse_token_expiry(token) == 0
