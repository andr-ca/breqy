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

        with patch("breqy.agents.providers.copilot_auth.httpx.post", return_value=mock_response) as mock_post:
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
        assert body["client_id"] == "Ov23li8tweQw6odWQebz"
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
