# system/orchestrator/auth/codex_auth.py
from __future__ import annotations
import base64
import hashlib
import os
import httpx
from system.orchestrator.auth.base import DeviceCodeResponse, DeviceFlowProvider
from system.orchestrator.auth.credential_store import CredentialStore

# Public OAuth app credentials for OpenAI Codex device flow
_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_USERCODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
_TOKEN_POLL_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
_EXCHANGE_URL = "https://auth.openai.com/oauth/token"


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate (code_verifier, code_challenge) for PKCE S256."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class CodexAuth(DeviceFlowProvider):
    """OpenAI Codex authentication via custom device flow with PKCE exchange."""

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store
        self._code_verifier: str | None = None

    @property
    def provider_name(self) -> str:
        return "codex"

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def request_device_code(self) -> DeviceCodeResponse:
        """Request a device code and store PKCE verifier for later exchange."""
        verifier, _challenge = _generate_pkce_pair()
        self._code_verifier = verifier
        resp = httpx.post(
            _USERCODE_URL,
            json={"client_id": _CLIENT_ID},
        )
        resp.raise_for_status()
        data = resp.json()
        return DeviceCodeResponse(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data.get("verification_uri", "https://platform.openai.com/"),
            expires_in=data.get("expires_in", 900),
            interval=data.get("interval", 5),
        )

    def poll_for_token(self, device_code: str) -> str | None:
        """Single poll attempt. Returns token string if authorized, None if still pending."""
        resp = httpx.post(
            _TOKEN_POLL_URL,
            json={"device_code": device_code, "client_id": _CLIENT_ID},
        )
        resp.raise_for_status()
        data = resp.json()

        # Approved: exchange the authorization code via PKCE
        if "code" in data:
            return self._exchange_code(data["code"])

        # Still pending or slow_down
        return None

    def _exchange_code(self, code: str) -> str | None:
        """Exchange authorization code for access token via PKCE."""
        resp = httpx.post(
            _EXCHANGE_URL,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": self._code_verifier or "",
                "client_id": _CLIENT_ID,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if token:
            self._store.set(self.provider_name, token)
            return token
        return None
