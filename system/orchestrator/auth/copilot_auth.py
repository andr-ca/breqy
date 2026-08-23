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
    """GitHub Copilot authentication via RFC 8628 device authorization grant."""

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store

    @property
    def provider_name(self) -> str:
        return "copilot"

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def request_device_code(self) -> DeviceCodeResponse:
        """Request a device code from GitHub."""
        resp = httpx.post(
            _DEVICE_CODE_URL,
            headers={"Accept": "application/json"},
            data={"client_id": _CLIENT_ID, "scope": _SCOPES},
        )
        resp.raise_for_status()
        data = resp.json()
        return DeviceCodeResponse(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            expires_in=int(data.get("expires_in", 900)),
            interval=int(data.get("interval", 5)),
        )

    def poll_for_token(self, device_code: str) -> str | None:
        """Single poll attempt. Returns token string if authorized, None if still pending."""
        resp = httpx.post(
            _TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": _CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if token:
            self._store.set(self.provider_name, token)
            return token
        return None
