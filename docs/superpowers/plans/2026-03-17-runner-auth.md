# Runner Authentication System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-provider OAuth device flow, PKCE, and API-key authentication to all 5 orchestrator runners, with an interactive TUI auth panel and `breqy-orchestrator auth` CLI subcommand.

**Architecture:** `AuthProvider` ABC with three flow-type subclasses (`DeviceFlowProvider`, `PkceProvider`, `ApiKeyProvider`); `CredentialStore` wraps OS keyring under `breqy/<provider>` namespace; all five runners accept an injected `CredentialStore` and read tokens at runtime; `Router` passes the store to runner constructors. `AuthPanel` Textual widget drives interactive auth (status table → flow-specific UI → success); reachable from main TUI via `A` keybind and from `breqy-orchestrator auth` CLI subcommand (no orchestrator loop).

**Tech Stack:** Python 3.12+, `httpx` (HTTP for OAuth endpoints), `keyring` (OS credential store), `textual` (TUI panel), Pydantic v2, pytest, ruff.

---

## File Map

```
NEW:
  system/orchestrator/auth/__init__.py          — ALL_PROVIDERS registry export
  system/orchestrator/auth/base.py              — AuthProvider ABC, DeviceFlowProvider,
                                                  PkceProvider, ApiKeyProvider; DeviceCodeResponse; AuthFlowType
  system/orchestrator/auth/credential_store.py  — CredentialStore wrapping keyring
  system/orchestrator/auth/copilot_auth.py      — GitHubCopilotAuth (RFC 8628 device flow)
  system/orchestrator/auth/gemini_auth.py       — GeminiAuth (RFC 8628 device flow)
  system/orchestrator/auth/codex_auth.py        — CodexAuth (OpenAI custom device flow + PKCE exchange)
  system/orchestrator/auth/claude_auth.py       — ClaudeAuth (PKCE Authorization Code, URL + paste)
  system/orchestrator/auth/qwen_auth.py         — QwenAuth (API key — no OAuth)
  system/orchestrator/tui/panels/auth_panel.py  — AuthPanel Textual widget
  system/orchestrator/tui/auth_app.py           — AuthApp standalone Textual app
  tests/unit/orchestrator/auth/__init__.py
  tests/unit/orchestrator/auth/test_credential_store.py
  tests/unit/orchestrator/auth/test_copilot_auth.py
  tests/unit/orchestrator/auth/test_gemini_auth.py
  tests/unit/orchestrator/auth/test_codex_auth.py
  tests/unit/orchestrator/auth/test_claude_auth.py
  tests/unit/orchestrator/auth/test_qwen_auth.py
  tests/unit/orchestrator/test_auth_panel.py
  tests/unit/orchestrator/runners/test_runner_injection.py

MODIFIED:
  pyproject.toml                                — add httpx>=0.27, keyring>=25 to dependencies
  system/orchestrator/runners/claude_runner.py  — optional CredentialStore constructor injection
  system/orchestrator/runners/codex_runner.py
  system/orchestrator/runners/gemini_runner.py
  system/orchestrator/runners/copilot_runner.py
  system/orchestrator/runners/qwen_runner.py
  system/orchestrator/router.py                 — accept + pass CredentialStore to runner constructors
  system/orchestrator/orchestrator.py           — accept + pass CredentialStore to Router
  system/orchestrator/main.py                   — add auth subcommand; build CredentialStore + providers
  system/orchestrator/tui/app.py                — add A keybind to show/hide AuthPanel
```

---

## Task 1: Add dependencies + AuthProvider ABC + CredentialStore

**Files:**
- Modify: `pyproject.toml`
- Create: `system/orchestrator/auth/__init__.py`
- Create: `system/orchestrator/auth/base.py`
- Create: `system/orchestrator/auth/credential_store.py`
- Create: `tests/unit/orchestrator/auth/__init__.py`
- Create: `tests/unit/orchestrator/auth/test_credential_store.py`

- [ ] **Step 1: Write failing tests**

Note on patching: `CredentialStore` calls `keyring.*` via the module reference. Patch at
`"keyring.set_password"` / `"keyring.get_password"` / `"keyring.delete_password"` (the top-level
keyring namespace). Keep each patch active for the **entire** test including the assertion.

```python
# tests/unit/orchestrator/auth/test_credential_store.py
from unittest.mock import patch
import keyring.errors
from system.orchestrator.auth.credential_store import CredentialStore


def test_set_calls_keyring():
    with patch("keyring.set_password") as mock_set:
        CredentialStore().set("copilot", "tok123")
        mock_set.assert_called_once_with("breqy", "copilot", "tok123")


def test_get_returns_token():
    with patch("keyring.get_password", return_value="tok123"):
        assert CredentialStore().get("copilot") == "tok123"


def test_get_returns_none_when_missing():
    with patch("keyring.get_password", return_value=None):
        assert CredentialStore().get("copilot") is None


def test_delete_calls_keyring():
    with patch("keyring.delete_password") as mock_del:
        CredentialStore().delete("copilot")
        mock_del.assert_called_once_with("breqy", "copilot")


def test_delete_swallows_missing():
    with patch("keyring.delete_password", side_effect=keyring.errors.PasswordDeleteError("no")):
        CredentialStore().delete("copilot")   # must not raise
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/auth/test_credential_store.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Add `httpx` and `keyring` to `pyproject.toml`**

Add to `[project]` dependencies:
```toml
"httpx>=0.27.0",
"keyring>=25.0.0",
```

Run `uv sync` to install.

- [ ] **Step 4: Implement `base.py`**

```python
# system/orchestrator/auth/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class AuthFlowType(str, Enum):
    DEVICE_FLOW = "device_flow"
    PKCE = "pkce"
    API_KEY = "api_key"


@dataclass
class DeviceCodeResponse:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class AuthProvider(ABC):
    provider_name: str
    flow_type: AuthFlowType

    @abstractmethod
    def is_authenticated(self) -> bool: ...

    @abstractmethod
    def get_token(self) -> str | None: ...

    @abstractmethod
    def revoke(self) -> None: ...


class DeviceFlowProvider(AuthProvider):
    flow_type = AuthFlowType.DEVICE_FLOW

    @abstractmethod
    def request_device_code(self) -> DeviceCodeResponse: ...

    @abstractmethod
    def poll_for_token(self, device_code: str) -> str | None:
        """Single poll attempt. Returns token string if authorized, None if still pending."""
        ...


class PkceProvider(AuthProvider):
    flow_type = AuthFlowType.PKCE

    @abstractmethod
    def get_auth_url(self) -> str:
        """Generate PKCE challenge, store verifier, return authorization URL."""
        ...

    @abstractmethod
    def exchange_code(self, auth_code: str) -> None:
        """Exchange authorization code for token; store in CredentialStore."""
        ...


class ApiKeyProvider(AuthProvider):
    flow_type = AuthFlowType.API_KEY

    @abstractmethod
    def set_key(self, api_key: str) -> None: ...
```

- [ ] **Step 5: Implement `credential_store.py`**

```python
# system/orchestrator/auth/credential_store.py
from __future__ import annotations
import keyring
import keyring.errors

_SERVICE = "breqy"


class CredentialStore:
    def get(self, provider: str) -> str | None:
        return keyring.get_password(_SERVICE, provider)

    def set(self, provider: str, token: str) -> None:
        keyring.set_password(_SERVICE, provider, token)

    def delete(self, provider: str) -> None:
        try:
            keyring.delete_password(_SERVICE, provider)
        except keyring.errors.PasswordDeleteError:
            pass
```

- [ ] **Step 6: Create empty `__init__.py`**

```python
# system/orchestrator/auth/__init__.py
```

- [ ] **Step 7: Run — verify passes**

```bash
pytest tests/unit/orchestrator/auth/test_credential_store.py -v
```
Expected: 5 PASSED

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml system/orchestrator/auth/ tests/unit/orchestrator/auth/
git commit -m "feat(auth): add AuthProvider ABC, CredentialStore, httpx+keyring deps

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: GitHubCopilotAuth (RFC 8628 device flow)

**Files:**
- Create: `system/orchestrator/auth/copilot_auth.py`
- Create: `tests/unit/orchestrator/auth/test_copilot_auth.py`

Endpoints (from GitHub Copilot language server source):
- Device code: `POST https://github.com/login/device/code`
- Token poll: `POST https://github.com/login/oauth/access_token`
- Client ID: `Iv1.b507a08c87ecfe98`
- Scopes: `repo workflow`

- [ ] **Step 1: Write failing tests**

Keep all `keyring.*` patches active for the **full test body** including assertions, not just construction.

```python
# tests/unit/orchestrator/auth/test_copilot_auth.py
from unittest.mock import patch, MagicMock
from system.orchestrator.auth.copilot_auth import GitHubCopilotAuth
from system.orchestrator.auth.credential_store import CredentialStore


def test_request_device_code():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "device_code": "dev_abc",
        "user_code": "ABCD-1234",
        "verification_uri": "https://github.com/login/device",
        "expires_in": 900,
        "interval": 5,
    }
    with patch("httpx.post", return_value=mock_resp), \
         patch("keyring.get_password", return_value=None):
        auth = GitHubCopilotAuth(credential_store=CredentialStore())
        resp = auth.request_device_code()
        assert resp.user_code == "ABCD-1234"
        assert resp.device_code == "dev_abc"
        assert resp.interval == 5


def test_poll_for_token_returns_token():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "ghu_TOKEN", "token_type": "bearer"}
    with patch("httpx.post", return_value=mock_resp), \
         patch("keyring.get_password", return_value=None), \
         patch("keyring.set_password") as mock_set:
        auth = GitHubCopilotAuth(credential_store=CredentialStore())
        token = auth.poll_for_token("dev_abc")
        assert token == "ghu_TOKEN"
        mock_set.assert_called_once_with("breqy", "copilot", "ghu_TOKEN")


def test_poll_for_token_returns_none_when_pending():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"error": "authorization_pending"}
    with patch("httpx.post", return_value=mock_resp), \
         patch("keyring.get_password", return_value=None):
        auth = GitHubCopilotAuth(credential_store=CredentialStore())
        assert auth.poll_for_token("dev_abc") is None


def test_is_authenticated_true_when_token_present():
    with patch("keyring.get_password", return_value="ghu_TOKEN"):
        assert GitHubCopilotAuth(credential_store=CredentialStore()).is_authenticated() is True


def test_is_authenticated_false_when_no_token():
    with patch("keyring.get_password", return_value=None):
        assert GitHubCopilotAuth(credential_store=CredentialStore()).is_authenticated() is False
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/auth/test_copilot_auth.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement `copilot_auth.py`**

```python
# system/orchestrator/auth/copilot_auth.py
from __future__ import annotations
import httpx
from system.orchestrator.auth.base import DeviceCodeResponse, DeviceFlowProvider
from system.orchestrator.auth.credential_store import CredentialStore

_CLIENT_ID = "Iv1.b507a08c87ecfe98"
_DEVICE_CODE_URL = "https://github.com/login/device/code"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_SCOPES = "repo workflow"


class GitHubCopilotAuth(DeviceFlowProvider):
    provider_name = "copilot"

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def request_device_code(self) -> DeviceCodeResponse:
        resp = httpx.post(
            _DEVICE_CODE_URL,
            data={"client_id": _CLIENT_ID, "scope": _SCOPES},
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        d = resp.json()
        return DeviceCodeResponse(
            device_code=d["device_code"],
            user_code=d["user_code"],
            verification_uri=d["verification_uri"],
            expires_in=d["expires_in"],
            interval=d["interval"],
        )

    def poll_for_token(self, device_code: str) -> str | None:
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "client_id": _CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        d = resp.json()
        if "access_token" in d:
            self._store.set(self.provider_name, d["access_token"])
            return d["access_token"]
        return None  # authorization_pending or slow_down
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/auth/test_copilot_auth.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/auth/copilot_auth.py tests/unit/orchestrator/auth/test_copilot_auth.py
git commit -m "feat(auth): add GitHubCopilotAuth (RFC 8628 device flow)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: GeminiAuth (RFC 8628 device flow)

**Files:**
- Create: `system/orchestrator/auth/gemini_auth.py`
- Create: `tests/unit/orchestrator/auth/test_gemini_auth.py`

Endpoints (from google-gemini/gemini-cli source):
- Device code: `POST https://oauth2.googleapis.com/device/code`
- Token poll: `POST https://oauth2.googleapis.com/token`
- Client ID: `681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com`
- Client secret: `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` (public — Google "installed app" pattern)
- Scopes: `https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/auth/test_gemini_auth.py
from unittest.mock import patch, MagicMock
from system.orchestrator.auth.gemini_auth import GeminiAuth
from system.orchestrator.auth.credential_store import CredentialStore


def test_request_device_code():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "device_code": "dev_goo",
        "user_code": "XXXX-YYYY",
        "verification_uri": "https://www.google.com/device",
        "expires_in": 1800,
        "interval": 5,
    }
    with patch("httpx.post", return_value=mock_resp), \
         patch("keyring.get_password", return_value=None):
        resp = GeminiAuth(credential_store=CredentialStore()).request_device_code()
        assert resp.user_code == "XXXX-YYYY"
        assert resp.interval == 5


def test_poll_stores_access_token():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "ya29.TOKEN"}
    with patch("httpx.post", return_value=mock_resp), \
         patch("keyring.get_password", return_value=None), \
         patch("keyring.set_password") as mock_set:
        token = GeminiAuth(credential_store=CredentialStore()).poll_for_token("dev_goo")
        assert token == "ya29.TOKEN"
        mock_set.assert_called_once_with("breqy", "gemini", "ya29.TOKEN")


def test_poll_returns_none_when_pending():
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"error": "authorization_pending"}
    with patch("httpx.post", return_value=mock_resp), \
         patch("keyring.get_password", return_value=None):
        assert GeminiAuth(credential_store=CredentialStore()).poll_for_token("dev_goo") is None
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/auth/test_gemini_auth.py -v
```

- [ ] **Step 3: Implement `gemini_auth.py`**

```python
# system/orchestrator/auth/gemini_auth.py
from __future__ import annotations
import httpx
from system.orchestrator.auth.base import DeviceCodeResponse, DeviceFlowProvider
from system.orchestrator.auth.credential_store import CredentialStore

_CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
# Public "installed application" client secret — committing this is intentional and correct
# per Google OAuth2 guidelines for installed apps. This is NOT a server-side secret.
# Source: google-gemini/gemini-cli (apache-2.0). Not subject to Breqy's secrets policy.
_CLIENT_SECRET = "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"
_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPES = " ".join([
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
])


class GeminiAuth(DeviceFlowProvider):
    provider_name = "gemini"

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def request_device_code(self) -> DeviceCodeResponse:
        resp = httpx.post(
            _DEVICE_CODE_URL,
            data={"client_id": _CLIENT_ID, "scope": _SCOPES},
            timeout=10.0,
        )
        resp.raise_for_status()
        d = resp.json()
        return DeviceCodeResponse(
            device_code=d["device_code"],
            user_code=d["user_code"],
            verification_uri=d["verification_uri"],
            expires_in=d["expires_in"],
            interval=d.get("interval", 5),
        )

    def poll_for_token(self, device_code: str) -> str | None:
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None  # authorization_pending
        d = resp.json()
        if "access_token" in d:
            self._store.set(self.provider_name, d["access_token"])
            return d["access_token"]
        return None
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/auth/test_gemini_auth.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/auth/gemini_auth.py tests/unit/orchestrator/auth/test_gemini_auth.py
git commit -m "feat(auth): add GeminiAuth (RFC 8628 device flow)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: CodexAuth (OpenAI custom device flow)

**Files:**
- Create: `system/orchestrator/auth/codex_auth.py`
- Create: `tests/unit/orchestrator/auth/test_codex_auth.py`

Endpoints (from openai/codex source `codex-rs/login/src/device_code_auth.rs`):
- Device code: `POST https://auth.openai.com/api/accounts/deviceauth/usercode`
  - Body: `{"client_id": "<id>"}` → response: `{"device_auth_id": "...", "user_code": "..."}`
  - Verification URL: `https://auth.openai.com/codex/device`
- Token poll: `POST https://auth.openai.com/api/accounts/deviceauth/token`
  - Body: `{"client_id": "<id>", "device_auth_id": "..."}` → response: `{"code": "..."}` when ready
- PKCE exchange: `POST https://auth.openai.com/oauth/token`
  - Body: `{"client_id": ..., "code": ..., "code_verifier": ..., "grant_type": "authorization_code"}`
- Client ID: `app_EMoamEEZ73f0CkXaXp7hrann`
- Scopes: `openid profile email offline_access`

Note: CodexAuth internally generates a PKCE verifier when `request_device_code()` is called and stores it as `self._code_verifier` for use in `poll_for_token()` when the authorization code is received.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/auth/test_codex_auth.py
from unittest.mock import patch, MagicMock, call
from system.orchestrator.auth.codex_auth import CodexAuth
from system.orchestrator.auth.credential_store import CredentialStore


def test_request_device_code():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "device_auth_id": "auth_id_abc",
        "user_code": "CODE-XYZ",
    }
    with patch("httpx.post", return_value=mock_resp), \
         patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = CodexAuth(credential_store=store)
        resp = auth.request_device_code()
        assert resp.device_code == "auth_id_abc"
        assert resp.user_code == "CODE-XYZ"
        assert resp.verification_uri == "https://auth.openai.com/codex/device"
        assert auth._code_verifier is not None   # PKCE verifier generated


def test_poll_returns_none_when_pending():
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"error": "authorization_pending"}
    with patch("httpx.post", return_value=mock_resp), \
         patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = CodexAuth(credential_store=store)
        auth._code_verifier = "test_verifier"
        assert auth.poll_for_token("auth_id_abc") is None


def test_poll_exchanges_code_and_stores_token():
    # First call: device auth returns code; second: PKCE exchange returns access_token
    poll_resp = MagicMock()
    poll_resp.status_code = 200
    poll_resp.json.return_value = {"code": "pkce_code_123"}

    exchange_resp = MagicMock()
    exchange_resp.json.return_value = {"access_token": "codex_TOKEN"}

    with patch("httpx.post", side_effect=[poll_resp, exchange_resp]), \
         patch("keyring.get_password", return_value=None), \
         patch("keyring.set_password") as mock_set:
        store = CredentialStore()
        auth = CodexAuth(credential_store=store)
        auth._code_verifier = "test_verifier"
        token = auth.poll_for_token("auth_id_abc")
        assert token == "codex_TOKEN"
        mock_set.assert_called_once_with("breqy", "codex", "codex_TOKEN")
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/auth/test_codex_auth.py -v
```

- [ ] **Step 3: Implement `codex_auth.py`**

```python
# system/orchestrator/auth/codex_auth.py
from __future__ import annotations
import hashlib
import base64
import secrets
import httpx
from system.orchestrator.auth.base import DeviceCodeResponse, DeviceFlowProvider
from system.orchestrator.auth.credential_store import CredentialStore

_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_USERCODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
_TOKEN_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
_EXCHANGE_URL = "https://auth.openai.com/oauth/token"
_VERIFICATION_URI = "https://auth.openai.com/codex/device"


def _pkce_pair() -> tuple[str, str]:
    """Return (verifier, challenge) pair."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


class CodexAuth(DeviceFlowProvider):
    provider_name = "codex"

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store
        self._code_verifier: str | None = None

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def request_device_code(self) -> DeviceCodeResponse:
        self._code_verifier, _ = _pkce_pair()
        resp = httpx.post(
            _USERCODE_URL,
            json={"client_id": _CLIENT_ID},
            timeout=10.0,
        )
        resp.raise_for_status()
        d = resp.json()
        return DeviceCodeResponse(
            device_code=d["device_auth_id"],
            user_code=d["user_code"],
            verification_uri=_VERIFICATION_URI,
            expires_in=d.get("expires_in", 900),
            interval=d.get("interval", 5),
        )

    def poll_for_token(self, device_code: str) -> str | None:
        resp = httpx.post(
            _TOKEN_URL,
            json={"client_id": _CLIENT_ID, "device_auth_id": device_code},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None  # still pending
        d = resp.json()
        if "code" not in d:
            return None
        return self._exchange_pkce(d["code"])

    def _exchange_pkce(self, code: str) -> str:
        resp = httpx.post(
            _EXCHANGE_URL,
            json={
                "client_id": _CLIENT_ID,
                "code": code,
                "code_verifier": self._code_verifier,
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self._store.set(self.provider_name, token)
        return token
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/auth/test_codex_auth.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/auth/codex_auth.py tests/unit/orchestrator/auth/test_codex_auth.py
git commit -m "feat(auth): add CodexAuth (OpenAI custom device flow + PKCE exchange)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: ClaudeAuth (PKCE Authorization Code)

**Files:**
- Create: `system/orchestrator/auth/claude_auth.py`
- Create: `tests/unit/orchestrator/auth/test_claude_auth.py`

Endpoints (from @anthropic-ai/claude-code v2.1.77):
- Auth URL: `https://claude.ai/oauth/authorize`
- Token: `POST https://platform.claude.com/v1/oauth/token`
- Client ID: `9d1c250a-e61b-44d9-88ed-5944d1962f5e`
- Redirect URI: `https://platform.claude.com/oauth/code/callback`
- Scopes: `user:profile user:inference user:sessions:claude_code`

Flow: `get_auth_url()` builds URL with PKCE challenge → user opens URL in browser → approves → pastes authorization code back → `exchange_code(auth_code)` trades code + verifier for token.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/auth/test_claude_auth.py
from unittest.mock import patch, MagicMock
from system.orchestrator.auth.claude_auth import ClaudeAuth
from system.orchestrator.auth.credential_store import CredentialStore


def test_get_auth_url_contains_client_id():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        url = auth.get_auth_url()
        assert "9d1c250a-e61b-44d9-88ed-5944d1962f5e" in url
        assert "claude.ai/oauth/authorize" in url
        assert "code_challenge=" in url
        assert auth._code_verifier is not None


def test_get_auth_url_changes_per_call():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        url1 = auth.get_auth_url()
        verifier1 = auth._code_verifier
        url2 = auth.get_auth_url()
        assert verifier1 != auth._code_verifier   # new PKCE verifier per call


def test_exchange_code_stores_token():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "claude_TOKEN"}
    with patch("httpx.post", return_value=mock_resp), \
         patch("keyring.get_password", return_value=None), \
         patch("keyring.set_password") as mock_set:
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        auth._code_verifier = "test_verifier"
        auth.exchange_code("auth_code_123")
        mock_set.assert_called_once_with("breqy", "claude", "claude_TOKEN")


def test_exchange_raises_without_get_auth_url():
    import pytest
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = ClaudeAuth(credential_store=store)
        with pytest.raises(RuntimeError, match="get_auth_url"):
            auth.exchange_code("some_code")
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/auth/test_claude_auth.py -v
```

- [ ] **Step 3: Implement `claude_auth.py`**

```python
# system/orchestrator/auth/claude_auth.py
from __future__ import annotations
import base64
import hashlib
import secrets
import urllib.parse
import httpx
from system.orchestrator.auth.base import PkceProvider
from system.orchestrator.auth.credential_store import CredentialStore

_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_AUTH_URL = "https://claude.ai/oauth/authorize"
_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
_REDIRECT_URI = "https://platform.claude.com/oauth/code/callback"
_SCOPES = "user:profile user:inference user:sessions:claude_code"


class ClaudeAuth(PkceProvider):
    provider_name = "claude"

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store
        self._code_verifier: str | None = None

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def get_auth_url(self) -> str:
        self._code_verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(self._code_verifier.encode()).digest()
        ).rstrip(b"=").decode()
        params = {
            "client_id": _CLIENT_ID,
            "response_type": "code",
            "scope": _SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "redirect_uri": _REDIRECT_URI,
        }
        return f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, auth_code: str) -> None:
        if self._code_verifier is None:
            raise RuntimeError("Call get_auth_url() before exchange_code()")
        resp = httpx.post(
            _TOKEN_URL,
            json={
                "client_id": _CLIENT_ID,
                "code": auth_code.strip(),
                "code_verifier": self._code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": _REDIRECT_URI,
            },
            headers={"anthropic-version": "2023-06-01"},
            timeout=10.0,
        )
        resp.raise_for_status()
        self._store.set(self.provider_name, resp.json()["access_token"])
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/auth/test_claude_auth.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/auth/claude_auth.py tests/unit/orchestrator/auth/test_claude_auth.py
git commit -m "feat(auth): add ClaudeAuth (PKCE Authorization Code, URL + paste)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: QwenAuth (API key)

**Files:**
- Create: `system/orchestrator/auth/qwen_auth.py`
- Create: `tests/unit/orchestrator/auth/test_qwen_auth.py`

Qwen/DashScope has no OAuth. The user pastes an API key; we store it in keyring.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/auth/test_qwen_auth.py
from unittest.mock import patch
from system.orchestrator.auth.qwen_auth import QwenAuth
from system.orchestrator.auth.credential_store import CredentialStore


def test_set_key_stores_in_keyring():
    with patch("keyring.get_password", return_value=None), \
         patch("keyring.set_password") as mock_set:
        store = CredentialStore()
        auth = QwenAuth(credential_store=store)
        auth.set_key("sk-test-key")
        mock_set.assert_called_once_with("breqy", "qwen", "sk-test-key")


def test_is_authenticated_after_set_key():
    with patch("keyring.get_password", return_value="sk-test-key"):
        store = CredentialStore()
        auth = QwenAuth(credential_store=store)
        assert auth.is_authenticated() is True


def test_is_authenticated_false_when_no_key():
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        auth = QwenAuth(credential_store=store)
        assert auth.is_authenticated() is False


def test_revoke_deletes_from_keyring():
    with patch("keyring.get_password", return_value=None), \
         patch("keyring.delete_password") as mock_del:
        store = CredentialStore()
        auth = QwenAuth(credential_store=store)
        auth.revoke()
        mock_del.assert_called_once_with("breqy", "qwen")
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/auth/test_qwen_auth.py -v
```

- [ ] **Step 3: Implement `qwen_auth.py`**

```python
# system/orchestrator/auth/qwen_auth.py
from __future__ import annotations
from system.orchestrator.auth.base import ApiKeyProvider
from system.orchestrator.auth.credential_store import CredentialStore


class QwenAuth(ApiKeyProvider):
    provider_name = "qwen"

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def set_key(self, api_key: str) -> None:
        self._store.set(self.provider_name, api_key)
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/auth/test_qwen_auth.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Populate `auth/__init__.py` with registry**

```python
# system/orchestrator/auth/__init__.py
from __future__ import annotations
from system.orchestrator.auth.base import AuthFlowType, AuthProvider, DeviceCodeResponse
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.auth.copilot_auth import GitHubCopilotAuth
from system.orchestrator.auth.gemini_auth import GeminiAuth
from system.orchestrator.auth.codex_auth import CodexAuth
from system.orchestrator.auth.claude_auth import ClaudeAuth
from system.orchestrator.auth.qwen_auth import QwenAuth

# Maps provider_name → class; used by main.py and AuthPanel to build provider instances
ALL_PROVIDER_CLASSES: dict[str, type[AuthProvider]] = {
    "claude": ClaudeAuth,
    "codex": CodexAuth,
    "gemini": GeminiAuth,
    "copilot": GitHubCopilotAuth,
    "qwen": QwenAuth,
}

__all__ = [
    "AuthFlowType", "AuthProvider", "DeviceCodeResponse", "CredentialStore",
    "GitHubCopilotAuth", "GeminiAuth", "CodexAuth", "ClaudeAuth", "QwenAuth",
    "ALL_PROVIDER_CLASSES",
]
```

- [ ] **Step 6: Run full auth suite**

```bash
pytest tests/unit/orchestrator/auth/ -v
```
Expected: all PASSED

- [ ] **Step 7: Commit**

```bash
git add system/orchestrator/auth/qwen_auth.py system/orchestrator/auth/__init__.py \
  tests/unit/orchestrator/auth/test_qwen_auth.py
git commit -m "feat(auth): add QwenAuth (API key) and ALL_PROVIDER_CLASSES registry

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Runner injection + Router update

**Files:**
- Modify: `system/orchestrator/runners/claude_runner.py`
- Modify: `system/orchestrator/runners/codex_runner.py`
- Modify: `system/orchestrator/runners/gemini_runner.py`
- Modify: `system/orchestrator/runners/copilot_runner.py`
- Modify: `system/orchestrator/runners/qwen_runner.py`
- Modify: `system/orchestrator/router.py`
- Modify: `system/orchestrator/orchestrator.py`

Each runner maps to a provider name and an env-var key:

| Runner | provider_name | env var injected |
|---|---|---|
| ClaudeRunner | `claude` | `ANTHROPIC_API_KEY` |
| CodexRunner | `codex` | `OPENAI_API_KEY` |
| GeminiRunner | `gemini` | `GOOGLE_API_KEY` |
| CopilotRunner | `copilot` | `GITHUB_COPILOT_TOKEN` |
| QwenRunner | `qwen` | `DASHSCOPE_API_KEY` |

- [ ] **Step 1: Write failing tests**

`ClaudeRunner` iterates `for line in proc.stdout:`, so the mock stdout must be an iterator,
not a plain string. The other four runners call `proc.stdout.read()`.

```python
# tests/unit/orchestrator/runners/test_runner_injection.py
from unittest.mock import patch, MagicMock
from pathlib import Path
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.schemas.run_result import RunContext


def _ctx():
    return RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))


def _mock_proc_iterating(output="done\n"):
    """Mock for ClaudeRunner (iterates proc.stdout line by line)."""
    proc = MagicMock()
    proc.stdout = iter([output])
    proc.returncode = 0
    proc.wait.return_value = 0
    return proc


def _mock_proc_read(output="done"):
    """Mock for other runners (calls proc.stdout.read())."""
    proc = MagicMock()
    proc.stdout.read.return_value = output
    proc.returncode = 0
    proc.wait.return_value = 0
    return proc


def test_claude_runner_injects_token():
    from system.orchestrator.runners.claude_runner import ClaudeRunner
    with patch("keyring.get_password", return_value="ant_TOKEN"), \
         patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _mock_proc_iterating()
        runner = ClaudeRunner(credential_store=CredentialStore())
        runner.run("hello", _ctx())
        env = mock_popen.call_args.kwargs["env"]
        assert env["ANTHROPIC_API_KEY"] == "ant_TOKEN"


def test_codex_runner_injects_token():
    from system.orchestrator.runners.codex_runner import CodexRunner
    with patch("keyring.get_password", return_value="oai_TOKEN"), \
         patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _mock_proc_read()
        runner = CodexRunner(credential_store=CredentialStore())
        runner.run("hello", _ctx())
        env = mock_popen.call_args.kwargs["env"]
        assert env["OPENAI_API_KEY"] == "oai_TOKEN"


def test_runner_without_store_still_works():
    """No CredentialStore — backward compatible, reads token from OS env."""
    from system.orchestrator.runners.claude_runner import ClaudeRunner
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _mock_proc_iterating()
        ClaudeRunner().run("hello", _ctx())  # must not raise


def test_router_passes_store_to_runner():
    from system.orchestrator.router import Router
    from system.orchestrator.config import OrchestratorConfig, GitHubConfig
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        cfg = OrchestratorConfig(
            github=GitHubConfig(repo="o/r"),
            agent_defaults={"doer": "claude"},
        )
        router = Router(config=cfg, credential_store=store)
        runner, _ = router.resolve("feature", "backend", "doer")
        assert runner._store is store
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/runners/test_runner_injection.py -v
```

- [ ] **Step 3: Update all five runners**

`ClaudeRunner` has a `_env()` helper — update it to inject the token. The other four runners
build env inline in `run()`. Show the full updated file for `ClaudeRunner`; apply the same
constructor + `_PROVIDER_NAME`/`_ENV_KEY` pattern to the other four.

```python
# system/orchestrator/runners/claude_runner.py  — full replacement
from __future__ import annotations
import subprocess
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult
from system.orchestrator.session_manager import is_rate_limit_output

_PROVIDER_NAME = "claude"
_ENV_KEY = "ANTHROPIC_API_KEY"


class ClaudeRunner(AgentRunner):
    def __init__(self, credential_store=None) -> None:
        self._store = credential_store

    def run(self, prompt: str, context: RunContext) -> RunResult:
        cmd = [
            "claude", "-p", prompt,
            "--output-format", "stream-json",
            "--permission-mode", "acceptEdits",
        ]
        if context.session_id:
            cmd += ["--resume", context.session_id]

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=self._env(context),
        )
        output_lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            output_lines.append(line)
        proc.wait()
        output = "".join(output_lines)

        if is_rate_limit_output(output):
            return RunResult(status="rate_limited", output=output, exit_code=proc.returncode)
        if proc.returncode != 0:
            return RunResult(status="failed", output=output, exit_code=proc.returncode)
        return RunResult(status="completed", output=output, exit_code=0)

    def _env(self, context: RunContext) -> dict[str, str]:
        import os
        env = os.environ.copy()
        env.update(context.extra_env)
        # Token from keyring overrides env var if present
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        return env
```

For the other four runners (which call `proc.stdout.read()` not iterate), add the constructor
and inject into the existing env dict in `run()`:

```python
# Pattern for CodexRunner / GeminiRunner / CopilotRunner / QwenRunner
_PROVIDER_NAME = "..."   # "codex" / "gemini" / "copilot" / "qwen"
_ENV_KEY = "..."         # "OPENAI_API_KEY" / "GOOGLE_API_KEY" / "GITHUB_COPILOT_TOKEN" / "DASHSCOPE_API_KEY"

class XxxRunner(AgentRunner):
    def __init__(self, credential_store=None) -> None:
        self._store = credential_store

    def run(self, prompt: str, context: RunContext) -> RunResult:
        env = {**os.environ, **context.extra_env}
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        proc = subprocess.Popen(
            [...existing cmd...],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
        raw = proc.stdout
        output: str = raw.read() if hasattr(raw, "read") else (raw or "")
        proc.wait()
        status = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
```

Provider/env-var mapping:
- `CodexRunner`: `_PROVIDER_NAME = "codex"`, `_ENV_KEY = "OPENAI_API_KEY"`
- `GeminiRunner`: `_PROVIDER_NAME = "gemini"`, `_ENV_KEY = "GOOGLE_API_KEY"`
- `CopilotRunner`: `_PROVIDER_NAME = "copilot"`, `_ENV_KEY = "GITHUB_COPILOT_TOKEN"`
- `QwenRunner`: `_PROVIDER_NAME = "qwen"`, `_ENV_KEY = "DASHSCOPE_API_KEY"`

- [ ] **Step 4: Update `Router` to accept and pass `CredentialStore`**

```python
# system/orchestrator/router.py  (only changed lines shown)
from system.orchestrator.auth.credential_store import CredentialStore   # new import

class Router:
    def __init__(self, config: OrchestratorConfig, credential_store: CredentialStore | None = None) -> None:
        self._config = config
        self._store = credential_store

    def resolve(self, task_type: str, component: str, role: str) -> tuple[AgentRunner, AgentAdapter]:
        # ... existing routing logic unchanged ...
        runner_cls = _RUNNERS.get(agent_type, ClaudeRunner)
        adapter_cls = _ADAPTERS[role]
        return runner_cls(credential_store=self._store), adapter_cls()   # pass store
```

- [ ] **Step 5: Update `OrchestratorLoop` to accept and pass `CredentialStore`**

```python
# system/orchestrator/orchestrator.py  (only changed lines)
from system.orchestrator.auth.credential_store import CredentialStore   # new import

class OrchestratorLoop:
    def __init__(
        self,
        config: OrchestratorConfig,
        state_machine: ConcreteStateMachine,
        artifact_store: ArtifactStore,
        event_log: EventLog,
        event_queue: queue.Queue,
        credential_store: CredentialStore | None = None,   # new optional param
    ) -> None:
        # ... existing assignments ...
        self._router = Router(config=config, credential_store=credential_store)  # pass through
```

- [ ] **Step 6: Run — verify passes**

```bash
pytest tests/unit/orchestrator/runners/test_runner_injection.py -v
pytest tests/unit/orchestrator/ -v --tb=short
```
Expected: all PASSED (no regressions in existing runner tests)

- [ ] **Step 7: Commit**

```bash
git add system/orchestrator/runners/ system/orchestrator/router.py \
  system/orchestrator/orchestrator.py \
  tests/unit/orchestrator/runners/test_runner_injection.py
git commit -m "feat(auth): inject CredentialStore into runners via Router

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: AuthPanel TUI widget

**Files:**
- Create: `system/orchestrator/tui/panels/auth_panel.py`
- Create: `tests/unit/orchestrator/test_auth_panel.py`

`AuthPanel` is a Textual `Widget` that displays all provider statuses and drives each auth flow inline. It uses a `ContentSwitcher` to swap between: status table view, device-flow view (URL + code + poll indicator), PKCE view (URL + code input), and API-key view (masked input).

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/orchestrator/test_auth_panel.py
from unittest.mock import MagicMock, patch
import pytest
from system.orchestrator.tui.panels.auth_panel import AuthPanel
from system.orchestrator.auth.base import AuthFlowType


def _make_device_provider(authenticated=False):
    p = MagicMock()
    p.flow_type = AuthFlowType.DEVICE_FLOW
    p.provider_name = "copilot"
    p.is_authenticated.return_value = authenticated
    return p


def _make_pkce_provider(authenticated=False):
    p = MagicMock()
    p.flow_type = AuthFlowType.PKCE
    p.provider_name = "claude"
    p.is_authenticated.return_value = authenticated
    return p


def _make_key_provider(authenticated=False):
    p = MagicMock()
    p.flow_type = AuthFlowType.API_KEY
    p.provider_name = "qwen"
    p.is_authenticated.return_value = authenticated
    return p


def test_auth_panel_instantiates():
    providers = {
        "copilot": _make_device_provider(),
        "claude": _make_pkce_provider(),
        "qwen": _make_key_provider(),
    }
    panel = AuthPanel(providers=providers)
    assert panel is not None


def test_auth_panel_status_summary():
    providers = {
        "copilot": _make_device_provider(authenticated=True),
        "claude": _make_pkce_provider(authenticated=False),
    }
    panel = AuthPanel(providers=providers)
    summary = panel.get_status_summary()
    assert summary["copilot"] is True
    assert summary["claude"] is False
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/unit/orchestrator/test_auth_panel.py -v
```

- [ ] **Step 3: Implement `auth_panel.py`**

```python
# system/orchestrator/tui/panels/auth_panel.py
from __future__ import annotations
import threading
import time
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static, Input, Button, ContentSwitcher
from textual.containers import Vertical, Horizontal
from system.orchestrator.auth.base import AuthFlowType, AuthProvider, DeviceCodeResponse


class AuthPanel(Widget):
    """Interactive authentication panel for all runner providers."""

    def __init__(self, providers: dict[str, AuthProvider], **kwargs) -> None:
        super().__init__(**kwargs)
        self._providers = providers
        self._active_provider: str | None = None
        self._active_device_code: str | None = None
        self._poll_thread: threading.Thread | None = None

    def get_status_summary(self) -> dict[str, bool]:
        return {name: p.is_authenticated() for name, p in self._providers.items()}

    def compose(self) -> ComposeResult:
        with ContentSwitcher(initial="status", id="auth-switcher"):
            with Vertical(id="status"):
                yield Static("[b]Runner Authentication[/b]", id="auth-title")
                table = DataTable(id="auth-table", cursor_type="row")
                yield table
                yield Static("↑↓ select runner · Enter to authenticate", id="auth-hint")

            with Vertical(id="device-flow"):
                yield Static("[b]Device Flow[/b]", id="df-title")
                yield Static("", id="df-url")
                yield Static("", id="df-code")
                yield Static("Waiting for authorization…", id="df-status")
                yield Button("Cancel", id="df-cancel", variant="error")

            with Vertical(id="pkce-flow"):
                yield Static("[b]PKCE Authorization[/b]", id="pkce-title")
                yield Static("", id="pkce-url")
                yield Static("Paste the authorization code:", id="pkce-hint")
                yield Input(placeholder="Paste code here", id="pkce-input")
                with Horizontal():
                    yield Button("Submit", id="pkce-submit", variant="primary")
                    yield Button("Cancel", id="pkce-cancel", variant="error")

            with Vertical(id="api-key-flow"):
                yield Static("[b]API Key[/b]", id="key-title")
                yield Input(placeholder="Paste API key", password=True, id="key-input")
                with Horizontal():
                    yield Button("Save", id="key-submit", variant="primary")
                    yield Button("Cancel", id="key-cancel", variant="error")

    def on_mount(self) -> None:
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#auth-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Runner", "Flow", "Status")
        for name, provider in self._providers.items():
            status = "✓ authenticated" if provider.is_authenticated() else "✗ not authenticated"
            table.add_row(name, provider.flow_type.value, status, key=name)

    def _show_view(self, view_id: str) -> None:
        self.query_one("#auth-switcher", ContentSwitcher).current = view_id

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        provider_name = str(event.row_key.value)
        self._start_auth(provider_name)

    def _start_auth(self, provider_name: str) -> None:
        provider = self._providers.get(provider_name)
        if provider is None:
            return
        self._active_provider = provider_name

        if provider.flow_type == AuthFlowType.DEVICE_FLOW:
            device_resp = provider.request_device_code()
            self._active_device_code = device_resp.device_code
            # OSC8 hyperlink for clickable URL
            url_markup = f"[link={device_resp.verification_uri}]{device_resp.verification_uri}[/link]"
            self.query_one("#df-url", Static).update(f"Open: {url_markup}")
            self.query_one("#df-code", Static).update(
                f"Enter code: [b]{device_resp.user_code}[/b]"
            )
            self.query_one("#df-status", Static).update("Waiting for authorization…")
            self._show_view("device-flow")
            self._start_device_poll(provider, device_resp)

        elif provider.flow_type == AuthFlowType.PKCE:
            url = provider.get_auth_url()
            url_markup = f"[link={url}]{url}[/link]"
            self.query_one("#pkce-url", Static).update(f"Open: {url_markup}")
            self.query_one("#pkce-input", Input).value = ""
            self._show_view("pkce-flow")

        elif provider.flow_type == AuthFlowType.API_KEY:
            self.query_one("#key-input", Input).value = ""
            self._show_view("api-key-flow")

    def _start_device_poll(self, provider, device_resp: DeviceCodeResponse) -> None:
        def _poll():
            interval = max(device_resp.interval, 5)
            deadline = time.time() + device_resp.expires_in
            while time.time() < deadline:
                time.sleep(interval)
                token = provider.poll_for_token(device_resp.device_code)
                if token:
                    self.call_from_thread(self._on_auth_success)
                    return
            self.call_from_thread(self._on_device_expired)

        self._poll_thread = threading.Thread(target=_poll, daemon=True)
        self._poll_thread.start()

    def _on_auth_success(self) -> None:
        self._show_view("status")
        self._refresh_table()

    def _on_device_expired(self) -> None:
        self.query_one("#df-status", Static).update("[red]Expired — try again[/red]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        if btn_id in ("df-cancel", "pkce-cancel", "key-cancel"):
            self._show_view("status")

        elif btn_id == "pkce-submit":
            code = self.query_one("#pkce-input", Input).value.strip()
            if code and self._active_provider:
                provider = self._providers[self._active_provider]
                provider.exchange_code(code)
                self._on_auth_success()

        elif btn_id == "key-submit":
            key = self.query_one("#key-input", Input).value.strip()
            if key and self._active_provider:
                provider = self._providers[self._active_provider]
                provider.set_key(key)
                self._on_auth_success()
```

- [ ] **Step 4: Run — verify passes**

```bash
pytest tests/unit/orchestrator/test_auth_panel.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/tui/panels/auth_panel.py tests/unit/orchestrator/test_auth_panel.py
git commit -m "feat(auth): add AuthPanel TUI widget (device flow, PKCE, API key)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9: AuthApp standalone + `main.py` auth subcommand

**Files:**
- Create: `system/orchestrator/tui/auth_app.py`
- Modify: `system/orchestrator/main.py`

- [ ] **Step 1: Implement `auth_app.py`**

No separate test — covered by existing panel tests and import smoke test.

```python
# system/orchestrator/tui/auth_app.py
from __future__ import annotations
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from system.orchestrator.auth.base import AuthProvider
from system.orchestrator.tui.panels.auth_panel import AuthPanel


class AuthApp(App):
    """Standalone auth app — runs without the orchestrator loop."""

    CSS = """
    AuthPanel { height: 100%; border: solid green; }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, providers: dict[str, AuthProvider]) -> None:
        super().__init__()
        self._providers = providers

    def compose(self) -> ComposeResult:
        yield Header()
        yield AuthPanel(providers=self._providers, id="auth-panel")
        yield Footer()
```

- [ ] **Step 2: Update `main.py` to support `auth` subcommand**

Keep `--config` and `--no-tui` on the top-level parser so that the existing invocation
`breqy-orchestrator --config X` continues to work without a subcommand. Move the body
of the current `main()` loop logic into `_run_orchestrator()`.

```python
# system/orchestrator/main.py  — updated main() function
def main() -> None:
    parser = argparse.ArgumentParser(description="Breqy Orchestrator")
    # Top-level flags preserved for backward compatibility
    parser.add_argument("--config", default="system/orchestrator/orchestrator.yaml",
                        help="Path to orchestrator.yaml")
    parser.add_argument("--no-tui", action="store_true", help="Run without TUI")

    sub = parser.add_subparsers(dest="command")

    run_cmd = sub.add_parser("run", help="Start the orchestrator loop")
    run_cmd.add_argument("--config", default="system/orchestrator/orchestrator.yaml")
    run_cmd.add_argument("--no-tui", action="store_true")

    auth_cmd = sub.add_parser("auth", help="Manage runner authentication")
    auth_cmd.add_argument("provider", nargs="?",
                          choices=["claude", "codex", "gemini", "copilot", "qwen"],
                          help="Authenticate a specific provider (omit for all)")

    args = parser.parse_args()

    if args.command == "auth":
        _run_auth(args.provider)
        return

    # Default: run the orchestrator loop (command == "run" or no subcommand)
    _run_orchestrator(Path(args.config), args.no_tui)


def _run_auth(provider_filter: str | None = None) -> None:
    from system.orchestrator.auth import ALL_PROVIDER_CLASSES
    from system.orchestrator.auth.credential_store import CredentialStore
    from system.orchestrator.tui.auth_app import AuthApp

    store = CredentialStore()
    if provider_filter:
        cls = ALL_PROVIDER_CLASSES.get(provider_filter)
        if cls is None:
            print(f"Unknown provider: {provider_filter}")
            return
        providers = {provider_filter: cls(credential_store=store)}
    else:
        providers = {name: cls(credential_store=store)
                     for name, cls in ALL_PROVIDER_CLASSES.items()}

    app = AuthApp(providers=providers)
    app.run()


def _run_orchestrator(cfg_path: Path, no_tui: bool) -> None:
    """Extracted from original main() — orchestrator loop startup."""
    loop, eq, cfg = _build_loop(cfg_path)
    # ... rest of existing loop startup code (task loading, threads, signal handling) ...
```

Note: Move the body of the existing `main()` (everything after argparse) into `_run_orchestrator()`. Keep `_build_loop()` as-is.

- [ ] **Step 3: Add AuthApp smoke test**

Add to `tests/unit/orchestrator/test_auth_panel.py`:

```python
def test_auth_app_instantiates():
    from system.orchestrator.tui.auth_app import AuthApp
    with patch("keyring.get_password", return_value=None):
        from system.orchestrator.auth import ALL_PROVIDER_CLASSES
        from system.orchestrator.auth.credential_store import CredentialStore
        store = CredentialStore()
        providers = {name: cls(credential_store=store)
                     for name, cls in ALL_PROVIDER_CLASSES.items()}
        app = AuthApp(providers=providers)
        assert app is not None
```

Run: `pytest tests/unit/orchestrator/test_auth_panel.py -v` — Expected: all PASSED.

- [ ] **Step 4: Verify import smoke test**

```bash
python -c "from system.orchestrator.main import main; print('ok')"
breqy-orchestrator auth --help
breqy-orchestrator --help     # must still show --config and --no-tui at top level
```
Expected: all print without error.

- [ ] **Step 5: Commit**

```bash
git add system/orchestrator/tui/auth_app.py system/orchestrator/main.py \
  tests/unit/orchestrator/test_auth_panel.py
git commit -m "feat(auth): add AuthApp standalone + breqy-orchestrator auth subcommand

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Integrate AuthPanel into OrchestratorApp (keybind A)

**Files:**
- Modify: `system/orchestrator/tui/app.py`

Add `AuthPanel` as a hidden overlay inside `OrchestratorApp`. Pressing `A` toggles it.

- [ ] **Step 1: Update `app.py`**

Read the current `app.py` before editing.

`AuthPanel` must be yielded **directly in `App.compose()`** — not inside the inner `Vertical`
container — so that it can cover the full screen when visible. Textual CSS `layer` positioning
achieves the overlay effect.

Add:
1. New imports: `AuthPanel`, `ALL_PROVIDER_CLASSES`, `CredentialStore`
2. Accept `credential_store: CredentialStore | None = None` in `OrchestratorApp.__init__`
3. Build `providers` dict from `ALL_PROVIDER_CLASSES`
4. `BINDINGS = [("a", "toggle_auth", "Auth")]`
5. Yield `AuthPanel` as the **last item in `App.compose()`**, at the top-level (sibling of `Header`, `Vertical`, `Footer`) — initially `display: none`
6. Implement `action_toggle_auth()` to toggle visibility

```python
# Additions to system/orchestrator/tui/app.py

# New imports
from system.orchestrator.auth import ALL_PROVIDER_CLASSES
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.tui.panels.auth_panel import AuthPanel

# Updated CSS — overlay covers full screen via layer
CSS = """
    ...existing CSS...
    #auth-overlay {
        display: none;
        layer: overlay;
        height: 100%;
        width: 100%;
        border: double yellow;
        background: $surface;
    }
"""

# Updated __init__
def __init__(self, event_queue, tasks, credential_store=None):
    super().__init__()
    self._queue = event_queue
    self._tasks = tasks
    store = credential_store or CredentialStore()
    self._providers = {name: cls(credential_store=store)
                       for name, cls in ALL_PROVIDER_CLASSES.items()}

# In compose() — yield at App level AFTER Footer, not inside Vertical
def compose(self) -> ComposeResult:
    yield Header()
    with Vertical():
        with Horizontal(id="top"):
            yield PipelinePanel(id="pipeline")
            yield TaskPanel(tasks=self._tasks, id="task")
        yield AgentPanel(id="agent")
        yield LogPanel(id="log")
    yield Footer()
    yield AuthPanel(providers=self._providers, id="auth-overlay")  # top-level overlay

# New binding + action
BINDINGS = [("a", "toggle_auth", "Auth")]

def action_toggle_auth(self) -> None:
    panel = self.query_one("#auth-overlay", AuthPanel)
    panel.display = not panel.display
```

- [ ] **Step 2: Verify TUI app still instantiates**

```bash
pytest tests/unit/orchestrator/test_tui_app.py -v
```
Expected: 1 PASSED (no regression)

- [ ] **Step 3: Run full test suite + coverage**

```bash
pytest tests/ --cov=system/orchestrator --cov-report=term-missing --cov-fail-under=80
ruff check system/orchestrator/
```
Expected: all PASSED, ≥80% coverage, 0 ruff errors.

- [ ] **Step 4: Commit**

```bash
git add system/orchestrator/tui/app.py
git commit -m "feat(auth): integrate AuthPanel into OrchestratorApp (keybind A)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Final Verification

- [ ] `breqy-orchestrator auth` — opens AuthApp, all 5 providers listed
- [ ] `breqy-orchestrator auth copilot` — opens AuthApp with only Copilot
- [ ] `breqy-orchestrator run --config ...` — starts orchestrator loop as before
- [ ] Main TUI: press `A` — AuthPanel overlay appears/disappears
- [ ] `pytest tests/ --cov=system/orchestrator --cov-report=term-missing` — ≥80%
- [ ] `ruff check system/orchestrator/` — 0 errors
