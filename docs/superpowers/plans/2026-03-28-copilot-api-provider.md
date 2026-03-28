# GitHub Copilot API Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken subprocess-based `gh copilot suggest` provider with a direct HTTP API client that authenticates via GitHub OAuth device flow and streams OpenAI-compatible chat completions from `api.githubcopilot.com`.

**Architecture:** Three focused modules — `copilot_auth.py` (device flow + token storage), `copilot_client.py` (SSE streaming HTTP client), `copilot.py` (ModelProvider glue) — wired into the existing `build_model_providers()` factory. All use `httpx` (already a dependency) and `CredentialStore` (already exists).

**Tech Stack:** Python 3.12, httpx, pydantic, structlog, pytest with unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-28-copilot-api-provider-design.md`

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `breqy/agents/providers/copilot_auth.py` | `CopilotAuthenticator`, `DeviceFlowInfo`, `CopilotAuthError` — device flow + credential store |
| `breqy/agents/providers/copilot_client.py` | `CopilotApiClient`, `CopilotApiError` — streaming HTTP + SSE parsing |
| `breqy/agents/providers/copilot.py` | `CopilotProvider(ModelProvider)` — auth + client + ProviderEvent mapping |
| `tests/unit/agents/providers/__init__.py` | Package init for new test directory |
| `tests/unit/agents/providers/test_copilot_auth.py` | Auth unit tests (10 tests) |
| `tests/unit/agents/providers/test_copilot_client.py` | API client unit tests (8 tests) |
| `tests/unit/agents/providers/test_copilot.py` | Provider unit tests (8 tests) |

### Modified files

| File | Change |
|---|---|
| `breqy/agents/providers/adapters.py` | Replace copilot branch in factory, remove dead copilot subprocess code |
| `breqy/agents/providers/__init__.py` | Export new copilot types |

---

### Task 1: CopilotAuthenticator — Models and Token Storage

**Files:**
- Create: `breqy/agents/providers/copilot_auth.py`
- Create: `tests/unit/agents/providers/__init__.py`
- Create: `tests/unit/agents/providers/test_copilot_auth.py`

- [ ] **Step 1: Write failing tests for models and token storage**

```python
# tests/unit/agents/providers/test_copilot_auth.py
"""Tests for GitHub Copilot OAuth device flow authenticator."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

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


class TestClearToken:
    def test_clear_token(self) -> None:
        from breqy.agents.providers.copilot_auth import CopilotAuthenticator

        store = _make_credential_store()
        _store_token(store, "gho_toremove")
        auth = CopilotAuthenticator(store)
        assert auth.get_token() == "gho_toremove"
        auth.clear_token()
        assert auth.get_token() is None
```

Also create the test package init:

```python
# tests/unit/agents/providers/__init__.py
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/agents/providers/test_copilot_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'breqy.agents.providers.copilot_auth'`

- [ ] **Step 3: Write minimal implementation**

```python
# breqy/agents/providers/copilot_auth.py
"""GitHub Copilot OAuth device flow authenticator."""
from __future__ import annotations

import structlog
from pydantic import BaseModel, SecretStr

from breqy.agents.credentials import CredentialStore
from breqy.agents.models import ProviderCredential
from breqy.domain.enums import CredentialKind

logger = structlog.get_logger(__name__)


class CopilotAuthError(Exception):
    """Raised when device flow fails (expired, denied, network error)."""


class DeviceFlowInfo(BaseModel):
    """Response from GitHub device flow initiation."""

    user_code: str
    verification_uri: str
    device_code: str
    interval: int
    expires_in: int


class CopilotAuthenticator:
    """Manages GitHub OAuth device flow and token persistence for Copilot."""

    GITHUB_CLIENT_ID: str = "Ov23li8tweQw6odWQebz"
    DEVICE_CODE_URL: str = "https://github.com/login/device/code"
    ACCESS_TOKEN_URL: str = "https://github.com/login/oauth/access_token"
    OAUTH_SCOPE: str = "read:user"
    POLLING_SAFETY_MARGIN_S: float = 3.0

    def __init__(self, credential_store: CredentialStore) -> None:
        self._credential_store = credential_store

    def get_token(self) -> str | None:
        """Retrieve stored OAuth token, or None if not authenticated."""
        credential = self._credential_store.get("copilot")
        if credential is None:
            return None
        return credential.secret_value.get_secret_value()

    def clear_token(self) -> None:
        """Remove stored token (used on 401 to force re-auth)."""
        self._credential_store.delete("copilot")
        logger.info("copilot_token_cleared")

    def _store_token(self, access_token: str) -> None:
        """Persist OAuth token to credential store."""
        self._credential_store.set(
            "copilot",
            ProviderCredential(
                provider="copilot",
                credential_kind=CredentialKind.ACCESS_TOKEN,
                secret_value=SecretStr(access_token),
                metadata={"auth_flow": "device"},
            ),
        )
        logger.info("copilot_token_stored")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/providers/test_copilot_auth.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add breqy/agents/providers/copilot_auth.py tests/unit/agents/providers/__init__.py tests/unit/agents/providers/test_copilot_auth.py
git commit -m "feat(copilot): add CopilotAuthenticator with token storage and models"
```

---

### Task 2: CopilotAuthenticator — Device Flow (start + poll)

**Files:**
- Modify: `breqy/agents/providers/copilot_auth.py`
- Modify: `tests/unit/agents/providers/test_copilot_auth.py`

- [ ] **Step 1: Write failing tests for device flow**

Add to `test_copilot_auth.py`:

```python
import httpx
from unittest.mock import patch, MagicMock


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/agents/providers/test_copilot_auth.py -v -k "TestStartDeviceFlow or TestPollForToken"`
Expected: FAIL — `AttributeError: CopilotAuthenticator has no attribute 'start_device_flow'` (or similar)

- [ ] **Step 3: Implement device flow methods**

Add to `copilot_auth.py`:

```python
import time
import httpx

# Add these methods to CopilotAuthenticator:

    def start_device_flow(self) -> DeviceFlowInfo:
        """Initiate GitHub OAuth device flow."""
        try:
            response = httpx.post(
                self.DEVICE_CODE_URL,
                json={
                    "client_id": self.GITHUB_CLIENT_ID,
                    "scope": self.OAUTH_SCOPE,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise CopilotAuthError(
                f"Failed to initiate device flow: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise CopilotAuthError(
                f"Failed to initiate device flow: {exc}"
            ) from exc

        data = response.json()
        info = DeviceFlowInfo(
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            device_code=data["device_code"],
            interval=data["interval"],
            expires_in=data.get("expires_in", 900),
        )
        logger.info(
            "copilot_device_flow_started",
            user_code=info.user_code,
            verification_uri=info.verification_uri,
        )
        return info

    def poll_for_token(self, device_code: str, interval: int) -> str:
        """Poll GitHub until user authorizes. Returns OAuth access token."""
        current_interval = interval

        while True:
            response = httpx.post(
                self.ACCESS_TOKEN_URL,
                json={
                    "client_id": self.GITHUB_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            data = response.json()

            access_token = data.get("access_token")
            if access_token:
                self._store_token(access_token)
                logger.info("copilot_device_flow_authorized")
                return access_token

            error = data.get("error")
            if error == "authorization_pending":
                logger.debug("copilot_device_flow_pending")
                time.sleep(current_interval + self.POLLING_SAFETY_MARGIN_S)
                continue

            if error == "slow_down":
                server_interval = data.get("interval")
                if isinstance(server_interval, int) and server_interval > 0:
                    current_interval = server_interval
                else:
                    current_interval = current_interval + 5
                logger.debug("copilot_device_flow_slow_down", new_interval=current_interval)
                time.sleep(current_interval + self.POLLING_SAFETY_MARGIN_S)
                continue

            if error == "expired_token":
                raise CopilotAuthError("Device code expired — please restart authentication")

            if error == "access_denied":
                raise CopilotAuthError("User denied authorization")

            if error:
                raise CopilotAuthError(f"Device flow error: {error}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/providers/test_copilot_auth.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add breqy/agents/providers/copilot_auth.py tests/unit/agents/providers/test_copilot_auth.py
git commit -m "feat(copilot): implement OAuth device flow (start + poll)"
```

---

### Task 3: CopilotApiClient — SSE Parsing and Streaming

**Files:**
- Create: `breqy/agents/providers/copilot_client.py`
- Create: `tests/unit/agents/providers/test_copilot_client.py`

- [ ] **Step 1: Write failing tests for API client**

```python
# tests/unit/agents/providers/test_copilot_client.py
"""Tests for GitHub Copilot streaming API client."""
from __future__ import annotations

import json
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest


def _make_sse_lines(*data_values: str | dict) -> list[str]:
    """Build SSE text lines from data payloads."""
    lines: list[str] = []
    for value in data_values:
        if isinstance(value, dict):
            lines.append(f"data: {json.dumps(value)}")
        else:
            lines.append(f"data: {value}")
        lines.append("")  # blank line = event boundary
    return lines


def _mock_streaming_response(
    lines: list[str], status_code: int = 200
) -> MagicMock:
    """Create a mock httpx streaming response with iter_lines."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"content-type": "text/event-stream"}
    response.iter_lines.return_value = iter(lines)
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


class TestStreamTextDeltas:
    def test_stream_text_deltas(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
            {"choices": [{"delta": {"content": " world"}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)

        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        text_chunks = [r for r in results if r.get("choices", [{}])[0].get("delta", {}).get("content")]
        assert len(text_chunks) == 2
        assert text_chunks[0]["choices"][0]["delta"]["content"] == "Hello"
        assert text_chunks[1]["choices"][0]["delta"]["content"] == " world"


class TestStreamToolCall:
    def test_stream_tool_call(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "read_file", "arguments": ""}}]}, "index": 0}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"path":'}}]}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "read file"}],
            )
        )

        tool_chunks = [
            r for r in results
            if r.get("choices", [{}])[0].get("delta", {}).get("tool_calls")
        ]
        assert len(tool_chunks) == 2


class TestStreamDoneTermination:
    def test_stream_done_termination(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        chunks = _make_sse_lines(
            {"choices": [{"delta": {"content": "hi"}, "index": 0}]},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        # [DONE] should not appear as a parsed result
        for r in results:
            assert isinstance(r, dict)


class TestStreamErrors:
    def test_stream_401_raises_api_error(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

        error_response = MagicMock()
        error_response.status_code = 401
        error_response.text = "Unauthorized"
        error_response.headers = {}

        mock_client = MagicMock()
        mock_client.stream.return_value.__enter__ = MagicMock(return_value=error_response)
        mock_client.stream.return_value.__exit__ = MagicMock(return_value=False)

        # The client should check status before iterating
        client = CopilotApiClient(http_client=mock_client)

        with pytest.raises(CopilotApiError) as exc_info:
            list(
                client.stream_chat(
                    token="gho_bad",
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "hi"}],
                )
            )
        assert exc_info.value.status_code == 401

    def test_stream_403_raises_api_error(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

        error_response = MagicMock()
        error_response.status_code = 403
        error_response.text = "Forbidden"
        error_response.headers = {}

        mock_client = MagicMock()
        mock_client.stream.return_value.__enter__ = MagicMock(return_value=error_response)
        mock_client.stream.return_value.__exit__ = MagicMock(return_value=False)

        client = CopilotApiClient(http_client=mock_client)

        with pytest.raises(CopilotApiError) as exc_info:
            list(
                client.stream_chat(
                    token="gho_test",
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "hi"}],
                )
            )
        assert exc_info.value.status_code == 403

    def test_stream_429_raises_api_error(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

        error_response = MagicMock()
        error_response.status_code = 429
        error_response.text = "Too Many Requests"
        error_response.headers = {"retry-after": "30"}

        mock_client = MagicMock()
        mock_client.stream.return_value.__enter__ = MagicMock(return_value=error_response)
        mock_client.stream.return_value.__exit__ = MagicMock(return_value=False)

        client = CopilotApiClient(http_client=mock_client)

        with pytest.raises(CopilotApiError) as exc_info:
            list(
                client.stream_chat(
                    token="gho_test",
                    model="gpt-4o",
                    messages=[{"role": "user", "content": "hi"}],
                )
            )
        assert exc_info.value.status_code == 429


class TestStreamEmpty:
    def test_stream_empty_response(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        mock_response = _mock_streaming_response(["data: [DONE]", ""])
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )
        assert results == []


class TestStreamPartialChunks:
    def test_stream_partial_chunks(self) -> None:
        from breqy.agents.providers.copilot_client import CopilotApiClient

        # Simulate data split across lines (httpx iter_lines handles line splitting)
        chunks = _make_sse_lines(
            {"choices": [{"delta": {"content": "part1"}, "index": 0}]},
            {"choices": [{"delta": {"content": "part2"}, "index": 0}]},
            "[DONE]",
        )
        mock_response = _mock_streaming_response(chunks)
        mock_client = MagicMock()
        mock_client.stream.return_value = mock_response

        client = CopilotApiClient(http_client=mock_client)
        results = list(
            client.stream_chat(
                token="gho_test",
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        text_chunks = [
            r["choices"][0]["delta"]["content"]
            for r in results
            if r.get("choices", [{}])[0].get("delta", {}).get("content")
        ]
        assert text_chunks == ["part1", "part2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/agents/providers/test_copilot_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'breqy.agents.providers.copilot_client'`

- [ ] **Step 3: Write implementation**

```python
# breqy/agents/providers/copilot_client.py
"""GitHub Copilot streaming chat completions API client."""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class CopilotApiError(Exception):
    """Raised on API-level errors (HTTP 4xx/5xx)."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Copilot API error {status_code}: {message}")


class CopilotApiClient:
    """Streaming HTTP client for GitHub Copilot chat completions."""

    BASE_URL: str = "https://api.githubcopilot.com"

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client or httpx.Client()

    def stream_chat(
        self,
        *,
        token: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream chat completions. Yields parsed SSE chunk dicts."""
        url = f"{self.BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "breqy/0.1.0",
            "Openai-Intent": "conversation-edits",
            "x-initiator": "user",
            "Accept": "text/event-stream",
        }
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        logger.debug(
            "copilot_api_request",
            model=model,
            message_count=len(messages),
            has_tools=bool(tools),
        )

        with self._http_client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code >= 400:
                error_text = ""
                try:
                    # Read the error body
                    for chunk in response.iter_text():
                        error_text += chunk
                except Exception:
                    error_text = f"HTTP {response.status_code}"
                logger.warning(
                    "copilot_api_error",
                    status_code=response.status_code,
                    error=error_text[:200],
                )
                raise CopilotApiError(response.status_code, error_text)

            yield from self._parse_sse(response)

    def _parse_sse(self, response: httpx.Response) -> Iterator[dict[str, Any]]:
        """Parse SSE stream from httpx response."""
        for line in response.iter_lines():
            if not line:
                continue

            if not line.startswith("data: "):
                continue

            data = line[6:]  # strip "data: " prefix

            if data == "[DONE]":
                logger.debug("copilot_sse_done")
                return

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("copilot_sse_parse_error", data=data[:100])
                continue

            yield chunk
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/providers/test_copilot_client.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add breqy/agents/providers/copilot_client.py tests/unit/agents/providers/test_copilot_client.py
git commit -m "feat(copilot): add CopilotApiClient with SSE streaming and error handling"
```

---

### Task 4: CopilotProvider — ModelProvider Implementation

**Files:**
- Create: `breqy/agents/providers/copilot.py`
- Create: `tests/unit/agents/providers/test_copilot.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/agents/providers/test_copilot.py
"""Tests for CopilotProvider ModelProvider implementation."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from breqy.agents.providers.base import (
    ModelProvider,
    ProviderEvent,
    ProviderRequest,
    ToolCallDelta,
    ToolDefinition,
)


def _make_request(prompt: str = "hello", **kwargs) -> ProviderRequest:
    return ProviderRequest(
        prompt=prompt,
        work_dir=Path("/tmp/test"),
        **kwargs,
    )


class TestProviderProperties:
    def test_provider_id(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        assert provider.provider_id == "copilot"

    def test_model_id(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="claude-sonnet-4-20250514",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        assert provider.model_id == "claude-sonnet-4-20250514"

    def test_supports_tool_calls(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        assert provider.supports_tool_calls is True

    def test_is_model_provider(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        assert isinstance(provider, ModelProvider)


class TestMessageConversion:
    def test_prompt_to_messages(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        messages = provider._build_messages(_make_request("what is 2+2?"))
        assert messages == [{"role": "user", "content": "what is 2+2?"}]

    def test_prompt_with_persona(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        request = _make_request("hello", extra_env={"BREQY_PERSONA": "You are helpful."})
        messages = provider._build_messages(request)
        assert messages == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
        ]


class TestToolConversion:
    def test_tool_definition_to_openai(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        provider = CopilotProvider(
            model_id="gpt-4o",
            authenticator=MagicMock(),
            client=MagicMock(),
        )
        tools = [
            ToolDefinition(
                name="read_file",
                description="Read file contents",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            )
        ]
        openai_tools = provider._convert_tools(tools)
        assert openai_tools == [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file contents",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                },
            }
        ]


class TestStreamTextEvents:
    def test_stream_text_events(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_token.return_value = "gho_test"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter([
            {"choices": [{"delta": {"content": "Hello"}, "index": 0}]},
            {"choices": [{"delta": {"content": " there"}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
        ])

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        text_events = [e for e in events if e.kind == "text"]
        assert len(text_events) == 2
        assert text_events[0].text == "Hello"
        assert text_events[1].text == " there"

        complete_events = [e for e in events if e.kind == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0].metadata is not None
        assert complete_events[0].metadata.exit_code == 0
        assert complete_events[0].metadata.provider_id == "copilot"


class TestStreamToolCallEvents:
    def test_stream_tool_call_events(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        mock_auth = MagicMock()
        mock_auth.get_token.return_value = "gho_test"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter([
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "read_file", "arguments": ""}}]}, "index": 0}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"path": "/tmp"}'}}]}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
        ])

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("read /tmp")))

        tool_events = [e for e in events if e.kind == "tool_call"]
        assert len(tool_events) == 2
        assert tool_events[0].tool_call is not None
        assert tool_events[0].tool_call.call_id == "call_1"
        assert tool_events[0].tool_call.tool_name == "read_file"
        assert tool_events[1].tool_call is not None
        assert tool_events[1].tool_call.arguments_chunk == '{"path": "/tmp"}'


class TestAuthRetry:
    def test_auth_retry_on_401(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_client import CopilotApiError

        mock_auth = MagicMock()
        mock_auth.get_token.side_effect = ["gho_old", "gho_new"]

        mock_client = MagicMock()
        # First call raises 401, second succeeds
        mock_client.stream_chat.side_effect = [
            CopilotApiError(401, "Unauthorized"),
            iter([
                {"choices": [{"delta": {"content": "ok"}, "index": 0}]},
                {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
            ]),
        ]

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        # Should have cleared token and retried
        mock_auth.clear_token.assert_called_once()
        text_events = [e for e in events if e.kind == "text"]
        assert len(text_events) == 1
        assert text_events[0].text == "ok"

    def test_no_token_triggers_device_flow(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider
        from breqy.agents.providers.copilot_auth import DeviceFlowInfo

        mock_auth = MagicMock()
        # First call returns None (no token), then returns token after device flow
        mock_auth.get_token.side_effect = [None, "gho_new"]
        mock_auth.start_device_flow.return_value = DeviceFlowInfo(
            user_code="ABCD-EFGH",
            verification_uri="https://github.com/login/device",
            device_code="dc_123",
            interval=5,
            expires_in=900,
        )
        mock_auth.poll_for_token.return_value = "gho_new"

        mock_client = MagicMock()
        mock_client.stream_chat.return_value = iter([
            {"choices": [{"delta": {"content": "hi"}, "index": 0}]},
            {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]},
        ])

        provider = CopilotProvider(model_id="gpt-4o", authenticator=mock_auth, client=mock_client)
        events = list(provider.stream(_make_request("hi")))

        mock_auth.start_device_flow.assert_called_once()
        mock_auth.poll_for_token.assert_called_once_with("dc_123", interval=5)
        assert any(e.kind == "text" for e in events)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/agents/providers/test_copilot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'breqy.agents.providers.copilot'`

- [ ] **Step 3: Write implementation**

```python
# breqy/agents/providers/copilot.py
"""GitHub Copilot ModelProvider implementation."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import structlog

from breqy.agents.providers.base import (
    CompletionMetadata,
    ModelProvider,
    ProviderEvent,
    ProviderRequest,
    ToolCallDelta,
    ToolDefinition,
)
from breqy.agents.providers.copilot_auth import CopilotAuthenticator, CopilotAuthError
from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

logger = structlog.get_logger(__name__)


class CopilotProvider(ModelProvider):
    """Direct HTTP provider for GitHub Copilot chat completions API."""

    def __init__(
        self,
        *,
        model_id: str,
        authenticator: CopilotAuthenticator,
        client: CopilotApiClient,
    ) -> None:
        self._model_id = model_id
        self._authenticator = authenticator
        self._client = client

    @property
    def provider_id(self) -> str:
        return "copilot"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def supports_tool_calls(self) -> bool:
        return True

    def stream(self, request: ProviderRequest) -> Iterator[ProviderEvent]:
        token = self._ensure_token()
        messages = self._build_messages(request)
        tools = self._convert_tools(request.tools) if request.tools else None

        try:
            yield from self._do_stream(token, messages, tools)
        except CopilotApiError as exc:
            if exc.status_code == 401:
                logger.info("copilot_token_expired_retrying")
                self._authenticator.clear_token()
                token = self._ensure_token()
                yield from self._do_stream(token, messages, tools)
            else:
                yield ProviderEvent(
                    kind="complete",
                    metadata=CompletionMetadata(
                        provider_id=self.provider_id,
                        model_id=self.model_id,
                        exit_code=1,
                    ),
                )
                raise

    def _ensure_token(self) -> str:
        """Get existing token or run device flow."""
        token = self._authenticator.get_token()
        if token is not None:
            return token

        logger.info("copilot_no_token_starting_device_flow")
        flow_info = self._authenticator.start_device_flow()
        logger.info(
            "copilot_device_flow_instructions",
            url=flow_info.verification_uri,
            code=flow_info.user_code,
        )
        return self._authenticator.poll_for_token(
            flow_info.device_code, interval=flow_info.interval
        )

    def _do_stream(
        self,
        token: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> Iterator[ProviderEvent]:
        """Stream from API and map chunks to ProviderEvent."""
        # Track active tool calls for argument streaming
        active_tool_calls: dict[int, ToolCallDelta] = {}

        for chunk in self._client.stream_chat(
            token=token,
            model=self._model_id,
            messages=messages,
            tools=tools,
        ):
            choices = chunk.get("choices", [])
            if not choices:
                continue

            choice = choices[0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")

            # Text content
            content = delta.get("content")
            if isinstance(content, str) and content:
                yield ProviderEvent(kind="text", text=content)

            # Tool calls
            tool_calls = delta.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    index = tc.get("index", 0)
                    call_id = tc.get("id")
                    function = tc.get("function", {})
                    tool_name = function.get("name")
                    arguments = function.get("arguments", "")

                    if call_id and tool_name:
                        # New tool call start
                        active_tool_calls[index] = ToolCallDelta(
                            call_id=call_id,
                            tool_name=tool_name,
                            arguments_chunk=arguments,
                        )
                        yield ProviderEvent(
                            kind="tool_call",
                            tool_call=active_tool_calls[index],
                        )
                    elif index in active_tool_calls and arguments:
                        # Argument streaming continuation
                        yield ProviderEvent(
                            kind="tool_call",
                            tool_call=ToolCallDelta(
                                call_id=active_tool_calls[index].call_id,
                                tool_name=active_tool_calls[index].tool_name,
                                arguments_chunk=arguments,
                            ),
                        )

            # Stream complete
            if finish_reason:
                yield ProviderEvent(
                    kind="complete",
                    metadata=CompletionMetadata(
                        provider_id=self.provider_id,
                        model_id=self.model_id,
                        exit_code=0,
                    ),
                )

    def _build_messages(self, request: ProviderRequest) -> list[dict[str, Any]]:
        """Convert ProviderRequest to OpenAI messages format."""
        messages: list[dict[str, Any]] = []
        persona = request.extra_env.get("BREQY_PERSONA")
        if persona:
            messages.append({"role": "system", "content": persona})
        messages.append({"role": "user", "content": request.prompt})
        return messages

    def _convert_tools(
        self, tools: list[ToolDefinition]
    ) -> list[dict[str, Any]]:
        """Convert Breqy ToolDefinition to OpenAI tool format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/agents/providers/test_copilot.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add breqy/agents/providers/copilot.py tests/unit/agents/providers/test_copilot.py
git commit -m "feat(copilot): add CopilotProvider with SSE-to-ProviderEvent mapping and auth retry"
```

---

### Task 5: Factory Integration — Wire into `build_model_providers()`

**Files:**
- Modify: `breqy/agents/providers/adapters.py`
- Modify: `tests/unit/agents/test_provider_adapters.py` (update existing tests)

- [ ] **Step 1: Write/update failing tests**

Add to `tests/unit/agents/test_provider_adapters.py`:

```python
class TestBuildCopilotProvider:
    def test_copilot_returns_copilot_provider(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        store = CredentialStore(MemorySecretProvider())
        providers = build_model_providers(
            credential_store=store,
            model_by_provider={"copilot": "gpt-4o"},
        )
        assert "copilot" in providers
        assert isinstance(providers["copilot"], CopilotProvider)
        assert providers["copilot"].provider_id == "copilot"
        assert providers["copilot"].model_id == "gpt-4o"
        assert providers["copilot"].supports_tool_calls is True
```

**Update existing tests that assumed old subprocess copilot:**

1. In `test_build_model_providers_exposes_supported_provider_and_model_identity` (line ~95):
   Change `assert providers["copilot"].supports_tool_calls is False` to `assert providers["copilot"].supports_tool_calls is True`

2. In the parametrized `test_chat_only_adapters_launch_expected_commands` (line ~472-474):
   Remove `("copilot", ["gh", "copilot", "suggest"])` from the parametrize list, leaving only `("qwen", ["qwen"])`. This test checks subprocess command prefixes, which no longer applies to copilot (now API-based).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/agents/test_provider_adapters.py::TestBuildCopilotProvider -v`
Expected: FAIL — `AssertionError: not isinstance(providers["copilot"], CopilotProvider)` (still returns old `_ChatOnlyRunnerProvider`)

- [ ] **Step 3: Modify adapters.py**

In `breqy/agents/providers/adapters.py`:

1. Remove `from system.orchestrator.runners.copilot_runner import CopilotRunner` (line 25)
2. Remove `"GITHUB_COPILOT_TOKEN"` from `_PROVIDER_AUTH_ENV_VARS` (line 33)
3. Remove `class _ConfiguredCopilotRunner` (lines 215-224)
4. Remove `make_copilot_runner` method from `_RunnerFactory` (lines 266-267)
5. Replace the copilot branch in `build_model_providers()` (lines 484-490):

```python
        elif provider_id == "copilot":
            from breqy.agents.providers.copilot import CopilotProvider
            from breqy.agents.providers.copilot_auth import CopilotAuthenticator
            from breqy.agents.providers.copilot_client import CopilotApiClient

            authenticator = CopilotAuthenticator(credential_store)
            client = CopilotApiClient()
            providers[provider_id] = CopilotProvider(
                model_id=model_id,
                authenticator=authenticator,
                client=client,
            )
```

- [ ] **Step 4: Run all provider adapter tests**

Run: `uv run pytest tests/unit/agents/test_provider_adapters.py -v`
Expected: all pass (update any old copilot-specific tests that assumed `_ChatOnlyRunnerProvider`)

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: all 1321+ tests pass, 0 failures

- [ ] **Step 6: Commit**

```bash
git add breqy/agents/providers/adapters.py tests/unit/agents/test_provider_adapters.py
git commit -m "refactor(copilot): replace subprocess runner with API-based CopilotProvider in factory"
```

---

### Task 6: Update Exports and Final Cleanup

**Files:**
- Modify: `breqy/agents/providers/__init__.py`

- [ ] **Step 1: Update exports**

Add the new copilot types to `__init__.py`:

```python
"""Public Breqy provider contracts and adapters."""
from breqy.agents.providers.adapters import build_model_providers
from breqy.agents.providers.base import (
    CompletionMetadata,
    ModelProvider,
    ProviderEvent,
    ProviderRequest,
    ToolCallDelta,
    ToolDefinition,
)
from breqy.agents.providers.copilot import CopilotProvider
from breqy.agents.providers.copilot_auth import (
    CopilotAuthenticator,
    CopilotAuthError,
    DeviceFlowInfo,
)
from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

__all__ = [
    "CompletionMetadata",
    "CopilotApiClient",
    "CopilotApiError",
    "CopilotAuthError",
    "CopilotAuthenticator",
    "CopilotProvider",
    "DeviceFlowInfo",
    "ModelProvider",
    "ProviderEvent",
    "ProviderRequest",
    "ToolCallDelta",
    "ToolDefinition",
    "build_model_providers",
]
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add breqy/agents/providers/__init__.py
git commit -m "refactor(copilot): export new Copilot API provider types from providers package"
```

---

## Task Dependency Graph

```
Task 1 (auth models + storage)
  └─► Task 2 (device flow)
        └─► Task 4 (CopilotProvider) ─► Task 5 (factory wiring) ─► Task 6 (exports)
Task 3 (API client + SSE) ──────────┘
```

Tasks 1→2 are sequential (device flow depends on models).
Task 3 is independent of Tasks 1-2 (can run in parallel).
Task 4 depends on Tasks 2 and 3.
Tasks 5 and 6 are sequential after Task 4.
