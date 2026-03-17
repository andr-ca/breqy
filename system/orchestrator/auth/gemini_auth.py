# system/orchestrator/auth/gemini_auth.py
from __future__ import annotations
import httpx
from system.orchestrator.auth.base import DeviceCodeResponse, DeviceFlowProvider
from system.orchestrator.auth.credential_store import CredentialStore

# Public OAuth client credentials for Google Generative Language API
# These are public application identifiers, not user secrets
_CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
_CLIENT_SECRET = "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"
_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/generative-language"


class GeminiAuth(DeviceFlowProvider):
    """Google Gemini authentication via RFC 8628 device authorization grant."""

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store

    @property
    def provider_name(self) -> str:
        return "gemini"

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def request_device_code(self) -> DeviceCodeResponse:
        """Request a device code from Google."""
        resp = httpx.post(
            _DEVICE_CODE_URL,
            data={"client_id": _CLIENT_ID, "scope": _SCOPE},
        )
        resp.raise_for_status()
        data = resp.json()
        return DeviceCodeResponse(
            device_code=data["device_code"],
            user_code=data["user_code"],
            # Google uses "verification_url" instead of "verification_uri"
            verification_uri=data.get("verification_url", data.get("verification_uri", "")),
            expires_in=data["expires_in"],
            interval=data.get("interval", 5),
        )

    def poll_for_token(self, device_code: str) -> str | None:
        """Single poll attempt. Returns token string if authorized, None if still pending."""
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
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
